"""Liens externes et suivi du prix d'une pièce."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app import pricing

ITEM = {"name": "Rafale à surveiller", "item_type": "DIECAST", "status": "WANTED"}


@pytest.fixture
def price_page(monkeypatch):
    """Simule la page téléchargée : ni résolution DNS, ni requête réseau."""
    monkeypatch.setattr(pricing, "_assert_public_url", lambda url: None)
    monkeypatch.setattr(pricing, "_download", lambda url: "")

    def _set(html: str):
        monkeypatch.setattr(pricing, "_download", lambda url: html)

    return _set


# --------------------------------------------------------------------------- #
# Liens
# --------------------------------------------------------------------------- #
def test_links_are_attached_to_the_item(admin_client, create_item):
    item = create_item(**ITEM)

    first = admin_client.post(
        f"/api/items/{item['id']}/links",
        json={"url": "https://exemple.fr/rafale", "label": "Boutique A"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["url"] == "https://exemple.fr/rafale"

    admin_client.post(f"/api/items/{item['id']}/links", json={"url": "exemple.fr/autre"})

    links = admin_client.get(f"/api/items/{item['id']}").json()["links"]
    assert len(links) == 2
    # Une adresse sans schéma est complétée en https
    assert links[1]["url"] == "https://exemple.fr/autre"
    assert links[1]["label"] is None


def test_link_can_be_renamed_and_removed(admin_client, create_item):
    item = create_item(**ITEM)
    link = admin_client.post(
        f"/api/items/{item['id']}/links", json={"url": "https://exemple.fr/x"}
    ).json()

    renamed = admin_client.patch(f"/api/links/{link['id']}", json={"label": "Fiche"})
    assert renamed.status_code == 200 and renamed.json()["label"] == "Fiche"

    assert admin_client.delete(f"/api/links/{link['id']}").status_code == 204
    assert admin_client.get(f"/api/items/{item['id']}").json()["links"] == []


def test_deleting_an_item_removes_its_links(admin_client, create_item):
    item = create_item(**ITEM)
    admin_client.post(f"/api/items/{item['id']}/links", json={"url": "https://exemple.fr/x"})
    assert admin_client.delete(f"/api/items/{item['id']}").status_code == 204
    assert admin_client.get("/api/items").json()["total"] == 0


def test_viewer_cannot_add_links(admin_client, create_item):
    item = create_item(**ITEM)
    admin_client.post(
        "/api/admin/users",
        json={"username": "lecteur", "password": "lecteurpass", "role": "VIEWER"},
    )
    admin_client.post("/api/admin/logout")
    admin_client.post("/api/admin/login", json={"username": "lecteur", "password": "lecteurpass"})

    assert admin_client.post(
        f"/api/items/{item['id']}/links", json={"url": "https://exemple.fr/x"}
    ).status_code == 403


# --------------------------------------------------------------------------- #
# Relevés de prix
# --------------------------------------------------------------------------- #
def test_price_points_are_recorded_in_order(admin_client, create_item):
    item = create_item(**ITEM, currency="EUR")

    for day, amount in (("2026-01-10", 60.0), ("2026-03-05", 55.0), ("2026-02-01", 58.0)):
        response = admin_client.post(
            f"/api/items/{item['id']}/prices", json={"price": amount, "recorded_on": day}
        )
        assert response.status_code == 201, response.text

    points = admin_client.get(f"/api/items/{item['id']}").json()["price_points"]
    assert [point["recorded_on"] for point in points] == ["2026-01-10", "2026-02-01", "2026-03-05"]
    assert [point["price"] for point in points] == [60.0, 58.0, 55.0]
    # Équivalent EUR figé à l'enregistrement (devise de référence = EUR ici)
    assert all(point["eur_value"] == point["price"] for point in points)


def test_price_point_converts_a_foreign_currency(admin_client, create_item):
    admin_client.put("/api/admin/rates", json={"rates": {"EUR": 1.0, "USD": 2.0}})
    item = create_item(**ITEM)

    created = admin_client.post(
        f"/api/items/{item['id']}/prices",
        json={"price": 120.0, "currency": "USD", "recorded_on": "2026-04-01"},
    ).json()
    assert created["currency"] == "USD"
    assert created["eur_value"] == pytest.approx(60.0)


def test_price_point_can_be_removed(admin_client, create_item):
    item = create_item(**ITEM)
    point = admin_client.post(f"/api/items/{item['id']}/prices", json={"price": 42.0}).json()
    assert admin_client.delete(f"/api/prices/{point['id']}").status_code == 204
    assert admin_client.get(f"/api/items/{item['id']}").json()["price_points"] == []


def test_invalid_price_is_rejected(admin_client, create_item):
    item = create_item(**ITEM)
    assert admin_client.post(f"/api/items/{item['id']}/prices", json={"price": 0}).status_code == 422
    assert admin_client.post(f"/api/items/{item['id']}/prices", json={"price": -5}).status_code == 422


# --------------------------------------------------------------------------- #
# Lecture assistée d'un prix (aucun appel réseau : le téléchargement est simulé)
# --------------------------------------------------------------------------- #
def test_price_is_read_from_json_ld(admin_client, price_page):
    html = """
    <html><head><title>Rafale 1/72</title>
    <script type="application/ld+json">
    {"@type":"Product","name":"Rafale","offers":{"@type":"Offer","price":"89.90","priceCurrency":"EUR"}}
    </script></head><body>…</body></html>
    """
    price_page(html)
    response = admin_client.post("/api/admin/fetch-price", json={"url": "https://exemple.fr/p/1"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["price"] == pytest.approx(89.90)
    assert payload["currency"] == "EUR"
    assert payload["strategy"] == "JSON-LD"
    assert payload["title"] == "Rafale 1/72"


def test_price_is_read_from_meta_tags(admin_client, price_page):
    html = """
    <meta property="og:price:amount" content="1 234,50">
    <meta property="og:price:currency" content="EUR">
    """
    price_page(html)
    payload = admin_client.post(
        "/api/admin/fetch-price", json={"url": "https://exemple.fr/p/2"}
    ).json()
    assert payload["price"] == pytest.approx(1234.50)
    assert payload["strategy"] == "métadonnées"


def test_price_falls_back_to_a_generic_pattern(admin_client, price_page):
    price_page("<p>Prix : 45,00 €</p>")
    payload = admin_client.post(
        "/api/admin/fetch-price", json={"url": "https://exemple.fr/p/3"}
    ).json()
    assert payload["price"] == pytest.approx(45.0)
    assert payload["strategy"] == "motif générique"


def test_unreadable_page_is_reported(admin_client, price_page):
    price_page("<html><body>Aucun tarif</body></html>")
    response = admin_client.post("/api/admin/fetch-price", json={"url": "https://exemple.fr/p/4"})
    assert response.status_code == 422
    assert "Aucun prix détecté" in response.json()["detail"]


def test_private_addresses_are_refused(admin_client):
    """La récupération ne doit pas servir de sonde vers le réseau local."""
    for url in ("http://127.0.0.1:8000/api/items", "http://10.0.0.5/", "http://localhost/"):
        response = admin_client.post("/api/admin/fetch-price", json={"url": url})
        assert response.status_code == 422, url
        assert "réseau local" in response.json()["detail"]

    assert admin_client.post(
        "/api/admin/fetch-price", json={"url": "ftp://exemple.fr/fichier"}
    ).status_code == 422


def test_unreachable_site_is_reported(admin_client, monkeypatch):
    monkeypatch.setattr(pricing, "_assert_public_url", lambda url: None)

    def boom(url):
        raise pricing.PriceFetchError("Site injoignable (test)")

    monkeypatch.setattr(pricing, "_download", boom)
    response = admin_client.post("/api/admin/fetch-price", json={"url": "https://exemple.fr/p/5"})
    assert response.status_code == 422
    assert "injoignable" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Sauvegarde : liens et relevés voyagent avec l'objet
# --------------------------------------------------------------------------- #
def test_backup_carries_links_and_prices(admin_client, create_item):
    from helpers import restore

    item = create_item(**ITEM, currency="EUR")
    admin_client.post(f"/api/items/{item['id']}/links", json={"url": "https://exemple.fr/x", "label": "Boutique"})
    admin_client.post(
        f"/api/items/{item['id']}/prices",
        json={"price": 55.0, "recorded_on": "2026-03-05", "note": "promo"},
    )

    archive = admin_client.get("/api/admin/backup").content
    admin_client.delete(f"/api/items/{item['id']}")

    assert restore(admin_client, archive, "replace").status_code == 200
    restored = admin_client.get("/api/items").json()["items"][0]
    assert [link["url"] for link in restored["links"]] == ["https://exemple.fr/x"]
    assert restored["links"][0]["label"] == "Boutique"
    assert len(restored["price_points"]) == 1
    point = restored["price_points"][0]
    assert point["price"] == pytest.approx(55.0)
    assert point["recorded_on"] == "2026-03-05"
    assert point["note"] == "promo"
