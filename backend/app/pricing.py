"""Lecture assistée d'un prix sur une page de boutique.

Le résultat n'est **jamais** enregistré automatiquement : il est proposé à
l'utilisateur, qui valide ou corrige. Les sites étant hétérogènes, on essaie
plusieurs stratégies, de la plus fiable à la plus approximative :

1. **JSON-LD** (`<script type="application/ld+json">`, `price` / `priceCurrency`) ;
2. **Open Graph** et microdonnées (`og:price:amount`, `itemprop="price"`) ;
3. **Motif générique** autour d'un symbole monétaire, en dernier recours.

Sécurité : seules les URL `http(s)` publiques sont acceptées (les adresses
internes sont refusées, pour ne pas transformer cette route en sonde réseau), le
téléchargement est borné et le délai limité.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

logger = logging.getLogger("aviadb.pricing")

MAX_BYTES = int(os.getenv("PRICE_FETCH_MAX_BYTES", str(2 * 1024 * 1024)))
TIMEOUT = int(os.getenv("PRICE_FETCH_TIMEOUT", "8"))
USER_AGENT = "Mozilla/5.0 (compatible; AviaDB/1.0)"

# Symbole -> code ISO, pour la stratégie générique.
SYMBOL_TO_CURRENCY = {
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "chf": "CHF",
    "$": "USD",
    "usd": "USD",
}

JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I
)
INLINE_PRICE_RE = re.compile(
    r'"price"\s*:\s*"?([0-9]+(?:[.,][0-9]{1,2})?)"?'
    r'(?:\s*,\s*"priceCurrency"\s*:\s*"([A-Z]{3})")?',
    re.I,
)
META_PRICE_RES = (
    re.compile(
        r'<meta[^>]+(?:property|name)=["\'](?:og|product):price:amount["\'][^>]+content=["\']([^"\']+)',
        re.I,
    ),
    re.compile(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og|product):price:amount',
        re.I,
    ),
)
META_CURRENCY_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og|product):price:currency["\'][^>]+content=["\']([A-Za-z]{3})',
    re.I,
)
ITEMPROP_PRICE_RE = re.compile(
    r'itemprop=["\']price["\'][^>]+content=["\']([^"\']+)', re.I
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', re.I
)
GENERIC_PRICE_RE = re.compile(
    r"(?:€|£|\$|CHF|EUR|GBP|USD)\s?([0-9][0-9 .,\u00a0]{2,12})"
    r"|([0-9][0-9 .,\u00a0]{2,12})\s?(?:€|£|CHF)",
    re.I,
)


class PriceFetchError(RuntimeError):
    """Prix non récupérable (site injoignable, page illisible, aucune valeur)."""


def _as_amount(raw: str) -> float | None:
    """« 1 234,56 » ou « 1,234.56 » → 1234.56."""
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.,]", "", str(raw).replace("\u00a0", ""))
    if not cleaned:
        return None
    # Le dernier séparateur rencontré est le séparateur décimal.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        head, _, tail = cleaned.rpartition(",")
        cleaned = f"{head}.{tail}" if len(tail) <= 2 else cleaned.replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if 0 < value < 10_000_000 else None


def _assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise PriceFetchError("Seules les adresses http(s) sont acceptées")
    host = parsed.hostname
    if not host:
        raise PriceFetchError("Adresse invalide")

    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise PriceFetchError(f"Nom d'hôte introuvable : {host}") from exc

    for info in addresses:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise PriceFetchError("Cette adresse pointe vers le réseau local : refusée")


def _download(url: str) -> str:
    """Récupère le HTML (borné). Isolé dans une fonction pour les tests."""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read(MAX_BYTES + 1)
            charset = response.headers.get_content_charset() or "utf-8"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise PriceFetchError(f"Site injoignable ({exc})") from exc

    if len(raw) > MAX_BYTES:
        raw = raw[:MAX_BYTES]
    return raw.decode(charset, errors="replace")


def _from_json_ld(html: str) -> tuple[float, str | None] | None:
    for bloc in JSON_LD_RE.findall(html):
        try:
            data = json.loads(bloc.strip())
        except (ValueError, TypeError):
            continue
        for candidate in _walk_json(data):
            amount = _as_amount(candidate.get("price"))
            if amount:
                currency = candidate.get("priceCurrency")
                return amount, currency.upper() if currency else None
    return None


def _walk_json(node) -> list[dict]:
    """Parcourt un JSON-LD à la recherche des objets portant un prix."""
    found: list[dict] = []
    if isinstance(node, dict):
        if "price" in node:
            found.append(node)
        for value in node.values():
            found.extend(_walk_json(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_walk_json(value))
    return found


def _from_meta(html: str) -> tuple[float, str | None] | None:
    for pattern in META_PRICE_RES:
        match = pattern.search(html)
        if match:
            amount = _as_amount(match.group(1))
            if amount:
                currency = META_CURRENCY_RE.search(html)
                return amount, currency.group(1).upper() if currency else None

    match = ITEMPROP_PRICE_RE.search(html)
    if match:
        amount = _as_amount(match.group(1))
        if amount:
            currency = META_CURRENCY_RE.search(html)
            return amount, currency.group(1).upper() if currency else None
    return None


def _from_generic(html: str) -> tuple[float, str | None] | None:
    text = re.sub(r"<[^>]+>", " ", html)
    for match in GENERIC_PRICE_RE.finditer(text):
        raw, currency = match.group(1), None
        if raw is None:
            raw = match.group(2)
            currency = "EUR"
        else:
            token = match.group(0).strip().lower()
            for symbol, code in SYMBOL_TO_CURRENCY.items():
                if token.startswith(symbol) if symbol.isascii() else token.startswith(symbol):
                    currency = code
                    break
        amount = _as_amount(raw)
        if amount:
            return amount, currency
    return None


def fetch_price(url: str) -> dict:
    """Renvoie {price, currency, title, strategy} ou lève `PriceFetchError`."""
    _assert_public_url(url)
    html = _download(url)

    if not html.strip():
        raise PriceFetchError("Page vide")

    for strategy, reader in (
        ("JSON-LD", _from_json_ld),
        ("métadonnées", _from_meta),
        ("motif générique", _from_generic),
    ):
        found = reader(html)
        if found:
            amount, currency_code = found
            if currency_code not in (None, "EUR", "USD", "GBP", "CHF") and len(currency_code) != 3:
                currency_code = None
            title = OG_TITLE_RE.search(html) or TITLE_RE.search(html)
            return {
                "price": amount,
                "currency": currency_code,
                "title": (title.group(1).strip()[:180] if title else None),
                "strategy": strategy,
            }

    raise PriceFetchError("Aucun prix détecté sur cette page")
