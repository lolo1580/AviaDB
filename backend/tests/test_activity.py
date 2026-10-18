"""Journal d'activité (audit)."""

from __future__ import annotations

from sqlalchemy import func, select

from app import main, models
from app.database import SessionLocal


def test_activity_requires_session(client):
    assert client.get("/api/admin/activity").status_code == 401


def test_activity_logs_mutations(admin_client, create_item):
    create_item(name="Rafale")

    response = admin_client.get("/api/admin/activity")

    assert response.status_code == 200, response.text
    entries = response.json()
    assert entries
    latest = entries[0]
    assert latest["method"] == "POST"
    assert latest["path"] == "/api/items"
    assert latest["username"] == "admin"
    assert latest["status_code"] == 201


def test_activity_records_failures(admin_client):
    # Une écriture refusée (403/404) est aussi tracée.
    assert admin_client.delete("/api/items/999999").status_code == 404
    entries = admin_client.get("/api/admin/activity").json()
    assert any(entry["status_code"] == 404 for entry in entries)


def test_activity_pruning_keeps_most_recent():
    """Le journal est borné : seules les entrées les plus récentes sont conservées."""
    with SessionLocal() as db:
        for _ in range(5):
            db.add(models.ActivityLog(method="POST", path="/api/items", status_code=201))
        db.commit()

        removed = main.prune_activity(db, keep=2)

        assert removed == 3
        remaining = db.scalar(
            select(func.count()).select_from(models.ActivityLog)
        )
        assert remaining == 2


def test_activity_keep_has_a_floor(monkeypatch):
    monkeypatch.setenv("ACTIVITY_KEEP", "1")
    assert main._activity_keep() == 100
