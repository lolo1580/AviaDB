"""Statistiques détaillées et fiche objet PDF."""

from __future__ import annotations

import pytest

from app.database import SessionLocal
from app.stats import compute_stats


def test_item_pdf_report(admin_client, create_item):
    item = create_item(name="Rafale", estimated_value=50, currency="EUR")

    response = admin_client.get(f"/api/items/{item['id']}/report.pdf")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


def test_stats_details_by_class_and_location(admin_client, create_item):
    create_item(name="A", estimated_value=100, currency="EUR", storage_location="Vitrine")
    create_item(name="B", estimated_value=50, currency="EUR", storage_location="Grenier")

    stats = admin_client.get("/api/stats").json()

    locations = {bucket["key"]: bucket["value"] for bucket in stats["value_by_location"]}
    assert locations["Vitrine"] == 100
    assert locations["Grenier"] == 50
    assert "value_by_class" in stats
    assert "top_gains" in stats


def test_public_stats_omit_details():
    """La route publique ne doit exposer ni emplacement ni écart par objet."""
    with SessionLocal() as db:
        stats = compute_stats(db)
    assert stats.value_by_location == []
    assert stats.value_by_class == []
    assert stats.top_gains == []
    assert stats.top_losses == []


def test_value_excludes_wanted_and_preorder(admin_client, create_item):
    """Les pièces non possédées ne comptent pas dans la valeur de la collection."""
    create_item(name="Possédé", estimated_value=100, status="STORED_BOX", currency="EUR")
    create_item(name="Recherché", estimated_value=50, status="WANTED", currency="EUR")
    create_item(name="Précommande", estimated_value=30, status="PREORDER", currency="EUR")

    stats = admin_client.get("/api/stats").json()

    # Les compteurs incluent tout le monde...
    assert stats["total_items"] == 3
    assert {b["key"]: b["count"] for b in stats["by_status"]} == {
        "STORED_BOX": 1,
        "WANTED": 1,
        "PREORDER": 1,
    }
    # ... mais les valeurs excluent les objets non possédés.
    assert stats["total_estimated_value"] == pytest.approx(100.0)
    assert stats["items_with_estimated_value"] == 1
    assert stats["value_by_location"] == [{"key": "Sans emplacement", "value": 100.0}]
    assert stats["value_by_class"] == [{"key": "Sans classe", "value": 100.0}]
    assert stats["top_gains"] == []
