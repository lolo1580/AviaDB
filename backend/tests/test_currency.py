"""Devises, taux de change et conversions.

Aucun appel réseau : le fournisseur est simulé (voir la fixture `no_network`).
"""

from __future__ import annotations

from datetime import date

import pytest
from helpers import BASE_URL, RATES_URL, REFRESH_URL, SETTINGS_URL, set_rates

from app import currency


def test_settings_expose_currencies_and_base(admin_client):
    payload = admin_client.get(SETTINGS_URL).json()
    assert payload["default_currency"] == "EUR"
    assert payload["rates"]["EUR"] == 1.0
    codes = {option["code"] for option in payload["currencies"]}
    assert {"EUR", "USD", "GBP", "CHF"} <= codes
    assert payload["rates_updated_at"] is None


def test_base_currency_is_configurable(admin_client):
    assert admin_client.put(BASE_URL, json={"default_currency": "usd"}).status_code == 200
    assert admin_client.get(SETTINGS_URL).json()["default_currency"] == "USD"
    assert admin_client.put(BASE_URL, json={"default_currency": "XXX"}).status_code == 400


def test_viewer_cannot_change_currency_settings(admin_client):
    admin_client.post(
        "/api/admin/users",
        json={"username": "lecteur", "password": "lecteurpass", "role": "VIEWER"},
    )
    admin_client.post("/api/admin/logout")
    admin_client.post("/api/admin/login", json={"username": "lecteur", "password": "lecteurpass"})

    assert admin_client.get(SETTINGS_URL).status_code == 200
    assert admin_client.put(BASE_URL, json={"default_currency": "USD"}).status_code == 403
    assert admin_client.post(REFRESH_URL).status_code == 403


def test_manual_rates_and_unknown_currency(admin_client):
    set_rates(admin_client, {"EUR": 1.0, "USD": 2.0})
    assert admin_client.get(SETTINGS_URL).json()["rates"]["USD"] == 2.0

    response = admin_client.put(RATES_URL, json={"rates": {"XXX": 1.0}})
    assert response.status_code == 400


def test_estimated_value_is_converted_to_base_currency(admin_client, create_item):
    # 1 EUR = 2 USD
    set_rates(admin_client, {"EUR": 1.0, "USD": 2.0})
    create_item(name="US", currency="USD", estimated_value=200)

    # Base EUR : 200 USD = 100 EUR
    stats = admin_client.get("/api/stats").json()
    assert stats["base_currency"] == "EUR"
    assert stats["total_estimated_value"] == pytest.approx(100.0)
    assert stats["by_currency"] == [{"key": "USD", "count": 1}]

    # Base USD : le montant reste 200 USD
    admin_client.put(BASE_URL, json={"default_currency": "USD"})
    stats = admin_client.get("/api/stats").json()
    assert stats["base_currency"] == "USD"
    assert stats["total_estimated_value"] == pytest.approx(200.0)


def test_value_by_country_aggregates_mixed_currencies(admin_client, create_item):
    set_rates(admin_client, {"EUR": 1.0, "USD": 2.0})
    create_item(name="FR", country="France", currency="EUR", estimated_value=50)
    create_item(name="US", country="France", currency="USD", estimated_value=100)

    stats = admin_client.get("/api/stats").json()
    assert stats["value_by_country"] == [{"key": "France", "value": pytest.approx(100.0)}]


def test_purchase_price_uses_historical_rate(admin_client, create_item, monkeypatch):
    calls = {}

    def fake_historical(code, on_date):
        calls["args"] = (code, on_date)
        return 1.25, date(2024, 5, 1)

    monkeypatch.setattr(currency, "fetch_historical_per_eur", fake_historical)
    set_rates(admin_client, {"EUR": 1.0, "USD": 1.10})

    item = create_item(
        name="Achat 2024", currency="USD", purchase_price=125, purchase_date="2024-05-01"
    )
    assert calls["args"] == ("USD", date(2024, 5, 1))
    assert item["purchase_eur_value"] == pytest.approx(100.0)
    assert item["purchase_rate_date"] == "2024-05-01"

    # Le total d'achat est en EUR, indépendamment du taux courant (1,10)
    stats = admin_client.get("/api/stats").json()
    assert stats["total_purchase_value"] == pytest.approx(100.0)


def test_purchase_price_falls_back_to_current_rate(admin_client, create_item, monkeypatch):
    monkeypatch.setattr(currency, "fetch_historical_per_eur", lambda code, on_date: (None, None))
    set_rates(admin_client, {"EUR": 1.0, "USD": 1.25})

    item = create_item(
        name="Achat sans historique", currency="USD", purchase_price=250, purchase_date="1995-01-01"
    )
    assert item["purchase_eur_value"] == pytest.approx(200.0)
    assert item["purchase_rate_date"] is None


def test_historical_rate_is_cached(admin_client, create_item, monkeypatch):
    calls = []

    def fake_historical(code, on_date):
        calls.append(code)
        return 1.25, date(2024, 5, 1)

    monkeypatch.setattr(currency, "fetch_historical_per_eur", fake_historical)
    set_rates(admin_client, {"EUR": 1.0, "USD": 1.10})

    create_item(name="A", currency="USD", purchase_price=125, purchase_date="2024-05-01")
    create_item(name="B", currency="USD", purchase_price=250, purchase_date="2024-05-01")

    # Le second objet réutilise le taux mis en cache
    assert calls == ["USD"]


def test_currency_defaults_to_base(admin_client, create_item):
    item = create_item(name="Sans devise")
    assert item["currency"] == "EUR"

    admin_client.put(BASE_URL, json={"default_currency": "CHF"})
    other = create_item(name="Après changement")
    assert other["currency"] == "CHF"


def test_updating_purchase_details_recomputes_conversion(admin_client, create_item, monkeypatch):
    monkeypatch.setattr(currency, "fetch_historical_per_eur", lambda code, on_date: (1.0, on_date))
    set_rates(admin_client, {"EUR": 1.0, "USD": 1.10})

    item = create_item(name="A", currency="USD", purchase_price=110, purchase_date="2024-05-01")
    assert item["purchase_eur_value"] == pytest.approx(110.0)

    # Nouveau taux historique simulé : 1 EUR = 2 USD
    monkeypatch.setattr(currency, "fetch_historical_per_eur", lambda code, on_date: (2.0, on_date))
    response = admin_client.patch(f"/api/items/{item['id']}", json={"purchase_date": "2023-01-01"})
    assert response.status_code == 200
    assert response.json()["purchase_eur_value"] == pytest.approx(55.0)
    assert response.json()["purchase_rate_date"] == "2023-01-01"


def test_rates_can_be_refreshed_from_provider(admin_client, monkeypatch):
    monkeypatch.setattr(
        currency,
        "fetch_current_rates",
        lambda: ({"EUR": 1.0, "USD": 1.5, "GBP": 0.8}, "source de test", "2026-01-02"),
    )
    payload = admin_client.post(REFRESH_URL).json()
    assert payload["rates"]["USD"] == 1.5
    assert payload["rates_source"] == "source de test"
    assert payload["rates_updated_at"] is not None


def test_rates_refresh_reports_provider_failure(admin_client, monkeypatch):
    def boom():
        raise currency.RateFetchError("hors ligne")

    monkeypatch.setattr(currency, "fetch_current_rates", boom)
    response = admin_client.post(REFRESH_URL)
    assert response.status_code == 502
    assert "hors ligne" in response.json()["detail"]


def test_backup_preserves_currency_and_historic_value(admin_client, create_item, monkeypatch):
    monkeypatch.setattr(currency, "fetch_historical_per_eur", lambda code, on_date: (1.25, date(2024, 5, 1)))
    set_rates(admin_client, {"EUR": 1.0, "USD": 1.10})
    item = create_item(name="Archive", currency="USD", purchase_price=125, purchase_date="2024-05-01")

    archive = admin_client.get("/api/admin/backup").content
    admin_client.post("/api/admin/bulk", json={"ids": [item["id"]], "action": "delete"})

    # Aucun taux historique ne doit être redemandé pendant la restauration
    monkeypatch.setattr(
        currency,
        "fetch_historical_per_eur",
        lambda code, on_date: pytest.fail("appel réseau pendant la restauration"),
    )
    response = admin_client.post(
        "/api/admin/restore",
        files={"file": ("backup.zip", archive, "application/zip")},
        data={"mode": "replace"},
    )
    assert response.status_code == 200, response.text

    restored = admin_client.get("/api/items").json()["items"][0]
    assert restored["currency"] == "USD"
    assert restored["purchase_eur_value"] == pytest.approx(100.0)
    assert restored["purchase_rate_date"] == "2024-05-01"
