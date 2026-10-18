"""Devises, taux de change et conversions.

Conventions
-----------
Les taux sont stockés « per_eur », à la manière de la BCE :

    per_eur["USD"] = 1.08   signifie   1 EUR = 1,08 USD
    per_eur["EUR"] = 1.0

Convertir un montant exprimé en devise `C` vers la devise de référence `B` :

    montant / per_eur[C] * per_eur[B]

La devise de référence est le réglage `default_currency` (EUR par défaut).

Taux courants
-------------
Récupérés auprès de frankfurter.app (données de la BCE, sans clé d'API) et
corrigeables à la main depuis l'administration.

Taux historiques
----------------
Les prix d'achat sont convertis avec le taux du jour de l'achat (replié sur le
dernier jour ouvré connu). Le résultat en EUR est figé sur l'objet
(`purchase_eur_value`), donc indépendant de la devise de référence choisie ;
les taux utilisés sont mis en cache par (devise, date).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger("aviadb.currency")

DEFAULT_BASE_CURRENCY = "EUR"

# Libellés des devises proposées dans les listes déroulantes.
CURRENCIES: dict[str, str] = {
    "EUR": "Euro",
    "USD": "Dollar américain",
    "GBP": "Livre sterling",
    "CHF": "Franc suisse",
    "JPY": "Yen japonais",
    "CAD": "Dollar canadien",
    "AUD": "Dollar australien",
    "NZD": "Dollar néo-zélandais",
    "SEK": "Couronne suédoise",
    "NOK": "Couronne norvégienne",
    "DKK": "Couronne danoise",
    "PLN": "Zloty polonais",
    "CZK": "Couronne tchèque",
    "HUF": "Forint hongrois",
    "RON": "Leu roumain",
    "BGN": "Lev bulgare",
    "TRY": "Livre turque",
    "ZAR": "Rand sud-africain",
    "BRL": "Réal brésilien",
    "MXN": "Peso mexicain",
    "CNY": "Yuan chinois",
    "HKD": "Dollar de Hong Kong",
    "SGD": "Dollar de Singapour",
    "INR": "Roupie indienne",
    "KRW": "Won sud-coréen",
    "ILS": "Shekel israélien",
    "AED": "Dirham des Émirats",
    "MAD": "Dirham marocain",
    "TND": "Dinar tunisien",
    "DZD": "Dinar algérien",
    "XPF": "Franc Pacifique",
}

FRANKFURTER_URL = os.getenv("RATES_API_URL", "https://api.frankfurter.dev/v1")
HTTP_TIMEOUT = 6
USER_AGENT = "AviaDB/1.0 (+collection aviation)"


class RateFetchError(RuntimeError):
    """Échec de récupération d'un taux auprès du fournisseur."""


# --------------------------------------------------------------------------- #
# Réglages
# --------------------------------------------------------------------------- #
def get_setting(db: Session, key: str, default=None):
    row = db.get(models.Setting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return default


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(models.Setting, key)
    if row is None:
        db.add(models.Setting(key=key, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)


def get_base_currency(db: Session) -> str:
    currency = get_setting(db, "default_currency", DEFAULT_BASE_CURRENCY)
    return (currency or DEFAULT_BASE_CURRENCY).upper()


def set_base_currency(db: Session, currency: str) -> str:
    code = (currency or "").upper()
    if code not in CURRENCIES:
        raise ValueError(f"Devise inconnue : {currency}")
    set_setting(db, "default_currency", code)
    return code


def get_rates(db: Session) -> dict[str, float]:
    """Taux courants « per_eur », complétés de la devise de référence."""
    rates = dict(get_setting(db, "rates", {}) or {})
    rates.setdefault("EUR", 1.0)
    rates.setdefault(get_base_currency(db), 1.0)
    return {code: float(value) for code, value in rates.items() if value}


def get_rates_meta(db: Session) -> dict:
    """Métadonnées des taux, avec les clés attendues par `SettingsOut`."""
    return {
        "rates_updated_at": get_setting(db, "rates_updated_at"),
        "rates_source": get_setting(db, "rates_source"),
    }


def set_rates(db: Session, rates: dict[str, float], source: str) -> None:
    cleaned = {"EUR": 1.0}
    for code, value in (rates or {}).items():
        code = (code or "").upper()
        if code not in CURRENCIES:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            cleaned[code] = number
    set_setting(db, "rates", cleaned)
    set_setting(db, "rates_source", source)
    set_setting(db, "rates_updated_at", datetime.now(timezone.utc).isoformat())


# --------------------------------------------------------------------------- #
# Conversions
# --------------------------------------------------------------------------- #
def to_base(value: float, currency: str | None, base: str, rates: dict[str, float]) -> float:
    """Convertit `value` de `currency` vers `base` avec les taux courants."""
    if value is None:
        return 0.0
    source = (currency or base).upper()
    rate_source = rates.get(source)
    rate_base = rates.get(base)
    if not rate_source or not rate_base:
        return float(value)
    return float(value) / rate_source * rate_base


def to_eur(value: float, currency: str | None, rates: dict[str, float]) -> float:
    return to_base(value, currency, "EUR", rates)


# --------------------------------------------------------------------------- #
# Récupération des taux
# --------------------------------------------------------------------------- #
def _http_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        raise RateFetchError(str(exc)) from exc


def _normalise(payload: dict) -> dict[str, float]:
    """Convertit une réponse BCE (1 EUR = X) en table per_eur."""
    rates = {"EUR": 1.0}
    for code, value in (payload.get("rates") or {}).items():
        code = (code or "").upper()
        if code in CURRENCIES:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                rates[code] = number
    return rates


def fetch_current_rates() -> tuple[dict[str, float], str, str]:
    """Renvoie (taux per_eur, source, date du fournisseur)."""
    payload = _http_json(f"{FRANKFURTER_URL}/latest?base=EUR")
    provider_date = payload.get("date") or date.today().isoformat()
    return _normalise(payload), f"BCE (frankfurter.dev) — {provider_date}", provider_date


def fetch_historical_per_eur(currency: str, on_date: date) -> tuple[float | None, date | None]:
    """Taux `per_eur` de `currency` à `on_date`.

    L'API BCE renvoie le dernier jour ouvré connu (elle indique la date réellement
    utilisée dans le champ `date`), donc un seul appel suffit. On prévoit malgré
    tout quelques jours de repli pour les dates limites.
    """
    code = (currency or "").upper()
    if code == "EUR":
        return 1.0, on_date
    if code not in CURRENCIES:
        return None, None

    for offset in range(0, 6):
        candidate = on_date - timedelta(days=offset)
        if candidate > date.today():
            continue
        try:
            payload = _http_json(
                f"{FRANKFURTER_URL}/{candidate.isoformat()}?base=EUR&symbols={code}"
            )
        except RateFetchError as exc:
            logger.warning("Taux historique indisponible pour %s : %s", candidate, exc)
            return None, None

        rates = _normalise(payload)
        if code in rates:
            raw_date = payload.get("date")
            try:
                used_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                used_date = candidate
            return rates[code], used_date
    return None, None


def historical_per_eur(db: Session, currency: str | None, on_date: date | None) -> tuple[float, date | None]:
    """Taux `per_eur` à utiliser pour un achat, avec cache et repli.

    Renvoie (taux, date du taux) ; la date est None quand on est retombé sur le
    taux courant.
    """
    code = (currency or get_base_currency(db)).upper()

    if code == "EUR" or on_date is None:
        return get_rates(db).get(code, 1.0), None

    cache = dict(get_setting(db, "rate_cache", {}) or {})
    key = f"{code}:{on_date.isoformat()}"
    cached = cache.get(key)
    if isinstance(cached, dict) and cached.get("per_eur"):
        used = cached.get("date")
        return float(cached["per_eur"]), date.fromisoformat(used) if used else None

    rate, used_date = fetch_historical_per_eur(code, on_date)
    if rate is None:
        # Pas de taux historique : on se rabat sur le taux courant.
        return get_rates(db).get(code, 1.0), None

    cache[key] = {"per_eur": rate, "date": used_date.isoformat() if used_date else None}
    set_setting(db, "rate_cache", cache)
    return rate, used_date


def backfill_items(db: Session) -> int:
    """Renseigne devise et équivalent EUR des objets créés avant les devises.

    Idempotent : ne touche qu'aux objets dont la devise est vide.
    """
    base = get_base_currency(db)
    rates = get_rates(db)
    items = list(db.scalars(select(models.Item).where(models.Item.currency.is_(None))).all())
    for item in items:
        item.currency = base
        if item.purchase_price is not None and item.purchase_eur_value is None:
            item.purchase_eur_value = round(to_eur(item.purchase_price, base, rates), 4)
    if items:
        db.commit()
        logger.info("Devise renseignée pour %s objet(s) existant(s)", len(items))
    return len(items)
