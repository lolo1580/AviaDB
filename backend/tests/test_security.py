"""Passe de sécurité : garde-fous sur la sauvegarde, l'API publique et les mots de passe."""

from __future__ import annotations

import io
import logging
import os
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import delete as sa_delete

from app import api_keys, auth, backup, models
from app.database import SessionLocal
from app.main import app


def make_zip(entries: dict[str, bytes]) -> bytes:
    """Archive ZIP en mémoire, avec les tailles réelles."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_backup_is_streamed_from_a_file(admin_client, create_item, upload_photo):
    upload_photo(create_item()["id"])
    response = admin_client.get("/api/admin/backup")
    assert response.status_code == 200
    assert response.content[:2] == b"PK"
    assert "aviadb-backup-" in response.headers["content-disposition"]


def test_restore_rejects_an_oversized_archive(admin_client, monkeypatch):
    monkeypatch.setattr(backup, "MAX_ARCHIVE_BYTES", 2048)
    # Contenu incompressible : l'archive dépasse réellement la limite.
    payload = make_zip({backup.MANIFEST_NAME: os.urandom(4096)})
    response = admin_client.post(
        "/api/admin/restore",
        files={"file": ("gros.zip", payload, "application/zip")},
        data={"mode": "merge"},
    )
    assert response.status_code == 413
    assert "trop volumineuse" in response.json()["detail"]


def test_restore_rejects_a_zip_bomb(admin_client, monkeypatch):
    """5 Mo très compressibles annoncés : refusés avant toute écriture."""
    monkeypatch.setattr(backup, "MAX_UNCOMPRESSED_BYTES", 1024 * 1024)
    payload = make_zip(
        {
            backup.MANIFEST_NAME: b"{}",
            "images/items/1/bombe.webp": b"x" * (5 * 1024 * 1024),
        }
    )
    # L'archive reste minuscule : c'est tout l'intérêt de la bombe
    assert len(payload) < 100 * 1024

    response = admin_client.post(
        "/api/admin/restore",
        files={"file": ("bombe.zip", payload, "application/zip")},
        data={"mode": "merge"},
    )
    assert response.status_code == 413
    assert "décompressé" in response.json()["detail"]


def test_restore_rejects_too_many_entries(admin_client, monkeypatch):
    monkeypatch.setattr(backup, "MAX_ARCHIVE_ENTRIES", 3)
    payload = make_zip({backup.MANIFEST_NAME: b"{}", **{f"images/{i}": b"x" for i in range(5)}})
    response = admin_client.post(
        "/api/admin/restore",
        files={"file": ("nombreux.zip", payload, "application/zip")},
        data={"mode": "merge"},
    )
    assert response.status_code == 400
    assert "entrées" in response.json()["detail"]


def test_restore_ignores_a_path_traversal(admin_client):
    """Un chemin remontant hors du dossier images est ignoré, pas écrit."""
    payload = make_zip(
        {
            backup.MANIFEST_NAME: b'{"version": 2, "items": []}',
            "images/../../evade.webp": b"contenu",
        }
    )
    response = admin_client.post(
        "/api/admin/restore",
        files={"file": ("evasion.zip", payload, "application/zip")},
        data={"mode": "merge"},
    )
    assert response.status_code == 200, response.text
    assert any("chemin ignoré" in message for message in response.json()["errors"])


def test_public_api_is_rate_limited(admin_client, create_item, monkeypatch):
    monkeypatch.setattr(api_keys, "RATE_LIMIT", 3)
    api_keys._hits.clear()

    key = admin_client.post("/api/admin/api-keys", json={"label": "widget"}).json()["key"]
    anonymous = TestClient(app)

    codes = [
        anonymous.get("/api/public/stats", headers={"X-API-Key": key}).status_code
        for _ in range(4)
    ]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429
    api_keys._hits.clear()


def test_weak_default_password_is_reported(monkeypatch, caplog):
    """Le mot de passe par défaut du compose doit être signalé au démarrage."""
    monkeypatch.setenv("ADMIN_PASSWORD", "change-me")

    with SessionLocal() as db:
        db.execute(sa_delete(models.User))
        db.commit()
        with caplog.at_level(logging.WARNING, logger="aviadb.auth"):
            auth.bootstrap_admin(db)

    assert any("mot de passe faible" in record.getMessage() for record in caplog.records)


def test_unprotected_mode_is_reported(monkeypatch, caplog):
    monkeypatch.setenv("ADMIN_PASSWORD", "")

    with SessionLocal() as db:
        db.execute(sa_delete(models.User))
        db.commit()
        with caplog.at_level(logging.WARNING, logger="aviadb.auth"):
            auth.bootstrap_admin(db)

    assert any("sans authentification" in record.getMessage() for record in caplog.records)
