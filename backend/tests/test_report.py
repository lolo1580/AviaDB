"""Rapport d'inventaire PDF."""

from __future__ import annotations


def test_report_requires_session(client):
    # Toute route /api/* exige une session.
    assert client.get("/api/admin/report.pdf").status_code == 401


def test_report_is_a_pdf(admin_client, create_item):
    create_item(name="Rafale", item_type="DIECAST", estimated_value=1234567, currency="EUR")
    create_item(name="Écusson 11F", item_type="PATCH", status="WANTED")

    response = admin_client.get("/api/admin/report.pdf")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
    assert "inventaire" in response.headers["content-disposition"]


def test_report_on_empty_collection(admin_client):
    response = admin_client.get("/api/admin/report.pdf")
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"


def test_report_handles_xml_special_characters(admin_client, create_item):
    """Un nom d'objet contenant « & » ou « < » ne doit pas casser le PDF."""
    item = create_item(name="A&B <prototype>", item_type="DIECAST")

    listing = admin_client.get("/api/admin/report.pdf")
    assert listing.status_code == 200, listing.text
    assert listing.content[:4] == b"%PDF"

    fiche = admin_client.get(f"/api/items/{item['id']}/report.pdf")
    assert fiche.status_code == 200, fiche.text
    assert fiche.content[:4] == b"%PDF"
