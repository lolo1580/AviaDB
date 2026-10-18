"""Clés d'API : cycle de vie et point d'accès public aux métriques."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def create_key(admin_client, label="Page d'accueil"):
    response = admin_client.post("/api/admin/api-keys", json={"label": label})
    assert response.status_code == 201, response.text
    return response.json()


def test_key_is_returned_once_and_never_listed_again(admin_client):
    created = create_key(admin_client)
    assert created["key"].startswith("aviadb_")
    assert created["api_key"]["prefix"].endswith("…")
    assert created["api_key"]["is_active"] is True
    assert created["api_key"]["request_count"] == 0
    assert "key_hash" not in created["api_key"]
    assert created["key"] not in created["api_key"]["prefix"]

    listed = admin_client.get("/api/admin/api-keys").json()
    assert len(listed) == 1
    assert "key" not in listed[0]
    assert "key_hash" not in listed[0]


def test_public_stats_require_a_valid_key(admin_client, create_item):
    create_item(name="Rafale confidentiel", country="France", estimated_value=120)
    key = create_key(admin_client)["key"]

    anonymous = TestClient(app)
    assert anonymous.get("/api/public/stats").status_code == 401
    assert anonymous.get("/api/public/stats", headers={"X-API-Key": "aviadb_faux"}).status_code == 401

    response = anonymous.get("/api/public/stats", headers={"X-API-Key": key})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_items"] == 1
    assert payload["total_estimated_value"] == 120.0
    assert {bucket["key"] for bucket in payload["by_country"]} == {"France"}

    # Aucune donnée nominative ni prix unitaire
    assert "Rafale confidentiel" not in response.text
    assert "purchase_eur_value" not in response.text


def test_usage_is_tracked(admin_client, create_item):
    create_item(name="Objet")
    key = create_key(admin_client)["key"]
    anonymous = TestClient(app)

    for _ in range(3):
        assert anonymous.get("/api/public/stats", headers={"X-API-Key": key}).status_code == 200

    entry = admin_client.get("/api/admin/api-keys").json()[0]
    assert entry["request_count"] == 3
    assert entry["last_used_at"] is not None


def test_key_can_be_disabled_then_removed(admin_client, create_item):
    create_item(name="Objet")
    created = create_key(admin_client)
    key, key_id = created["key"], created["api_key"]["id"]
    anonymous = TestClient(app)

    renamed = admin_client.patch(f"/api/admin/api-keys/{key_id}", json={"label": "Accueil du site"})
    assert renamed.status_code == 200 and renamed.json()["label"] == "Accueil du site"

    assert admin_client.patch(f"/api/admin/api-keys/{key_id}", json={"is_active": False}).status_code == 200
    assert anonymous.get("/api/public/stats", headers={"X-API-Key": key}).status_code == 401

    assert admin_client.patch(f"/api/admin/api-keys/{key_id}", json={"is_active": True}).status_code == 200
    assert anonymous.get("/api/public/stats", headers={"X-API-Key": key}).status_code == 200

    assert admin_client.delete(f"/api/admin/api-keys/{key_id}").status_code == 204
    assert anonymous.get("/api/public/stats", headers={"X-API-Key": key}).status_code == 401
    assert admin_client.get("/api/admin/api-keys").json() == []


def test_public_endpoint_stays_open_when_the_app_is_protected(admin_client, create_item):
    """Le middleware d'authentification laisse passer /api/public/* (clé à la place)."""
    create_item(name="Objet")
    key = create_key(admin_client)["key"]

    anonymous = TestClient(app)
    # Les routes normales restent fermées…
    assert anonymous.get("/api/items").status_code == 401
    assert anonymous.get("/api/stats").status_code == 401
    # …mais la route publique répond avec la clé
    assert anonymous.get("/api/public/stats", headers={"X-API-Key": key}).status_code == 200


def test_viewer_cannot_manage_keys(admin_client):
    admin_client.post(
        "/api/admin/users",
        json={"username": "lecteur", "password": "lecteurpass", "role": "VIEWER"},
    )
    admin_client.post("/api/admin/logout")
    admin_client.post("/api/admin/login", json={"username": "lecteur", "password": "lecteurpass"})

    assert admin_client.get("/api/admin/api-keys").status_code == 403
    assert admin_client.post("/api/admin/api-keys", json={"label": "x"}).status_code == 403


def test_api_key_can_be_passed_as_query_parameter(admin_client, create_item):
    """Pratique pour un widget : `/api/public/stats?api_key=…`."""
    create_item(name="Objet")
    key = create_key(admin_client)["key"]
    anonymous = TestClient(app)
    assert anonymous.get("/api/public/stats", params={"api_key": key}).status_code == 200
