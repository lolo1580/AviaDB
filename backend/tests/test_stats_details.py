"""Statistiques détaillées et fiche objet PDF."""

from __future__ import annotations

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
