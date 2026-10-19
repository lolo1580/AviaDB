"""Précommandes : statut dédié et champs associés."""

from __future__ import annotations


def test_preorder_fields_roundtrip(admin_client, create_item):
    item = create_item(
        name="Rafale M precommande",
        item_type="DIECAST",
        status="PREORDER",
        estimated_value=80,
        currency="EUR",
        preorder_release_date="2027-03-01",
        preorder_shop="Boutique Aero",
        preorder_deposit=20,
    )

    assert item["status"] == "PREORDER"
    assert item["preorder_release_date"] == "2027-03-01"
    assert item["preorder_shop"] == "Boutique Aero"
    assert item["preorder_deposit"] == 20

    fetched = admin_client.get(f"/api/items/{item['id']}").json()
    assert fetched["preorder_shop"] == "Boutique Aero"
    assert fetched["preorder_deposit"] == 20


def test_preorder_status_is_listed(admin_client):
    statuses = admin_client.get("/api/meta/enums").json()["statuses"]
    assert "PREORDER" in statuses


def test_preorder_can_be_created_and_updated(admin_client, create_item):
    item = create_item(name="A commander", status="WANTED")

    updated = admin_client.patch(
        f"/api/items/{item['id']}",
        json={
            "status": "PREORDER",
            "preorder_shop": "Revendeur",
            "preorder_deposit": 15.5,
        },
    )

    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["status"] == "PREORDER"
    assert payload["preorder_shop"] == "Revendeur"
    assert payload["preorder_deposit"] == 15.5


def test_csv_export_includes_preorder_columns(admin_client, create_item):
    create_item(name="Precommandee", status="PREORDER", preorder_shop="Shop")

    csv_text = admin_client.get("/api/admin/export.csv").text
    header = csv_text.splitlines()[0]

    assert "preorder_release_date" in header
    assert "preorder_shop" in header
    assert "preorder_deposit" in header
    assert "Shop" in csv_text
