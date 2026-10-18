"""Mode sans protection : aucun compte et aucun ADMIN_PASSWORD."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete

from app import auth, models
from app.database import SessionLocal
from app.main import app


def test_open_mode_when_no_accounts(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "")

    with SessionLocal() as db:
        db.execute(sa_delete(models.User))
        db.commit()
        auth.refresh_protection(db)

    with TestClient(app) as client:
        assert client.get("/api/admin/session").json() == {
            "enabled": False,
            "authenticated": False,
            "username": None,
            "role": None,
        }

        # Tout est accessible, y compris l'écriture et la gestion des comptes
        assert client.get("/api/items").status_code == 200
        created = client.post("/api/items", json={"name": "Sans auth", "item_type": "OTHER"})
        assert created.status_code == 201
        assert client.get("/api/admin/users").status_code == 200


def test_protection_resumes_with_a_password(monkeypatch):
    """Dès qu'un mot de passe est défini, le compte initial est recréé."""
    monkeypatch.setenv("ADMIN_PASSWORD", "nouveau-mot-de-passe")

    with SessionLocal() as db:
        db.execute(sa_delete(models.User))
        db.commit()
        auth.refresh_protection(db)
        # Un mot de passe suffit à exiger l'authentification…
        assert auth.protection_enabled() is True
        # …et le compte initial est (re)créé.
        assert auth.bootstrap_admin(db) is True

    with TestClient(app) as client:
        assert client.get("/api/items").status_code == 401
        response = client.post(
            "/api/admin/login", json={"username": "admin", "password": "nouveau-mot-de-passe"}
        )
        assert response.status_code == 200
        assert client.get("/api/items").status_code == 200
