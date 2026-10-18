"""CRUD des objets : création, lecture, mise à jour partielle, suppression."""

from __future__ import annotations


def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_enums_options(admin_client):
    payload = admin_client.get("/api/meta/enums").json()
    assert "DIECAST" in payload["item_types"]
    assert "STORED_BOX" in payload["statuses"]
    assert "SHIELD" in payload["shapes"]


def test_create_diecast_with_tags_is_deduplicated(create_item):
    item = create_item(
        name="Rafale M 11F Tiger Meet 2024",
        country="France",
        aircraft_model="Rafale M",
        estimated_value=120,
        tags=["Tiger Meet", "Marine", "Tiger Meet"],
        diecast={"scale": "1/72", "manufacturer": "Hobby Master", "part_number": "HA6501"},
    )
    assert item["item_type"] == "DIECAST"
    assert item["diecast"]["scale"] == "1/72"
    assert sorted(tag["name"] for tag in item["tags"]) == ["Marine", "Tiger Meet"]
    assert item["photos"] == []


def test_create_patch_with_details(create_item):
    item = create_item(
        name="Patch Flottille 11F",
        item_type="PATCH",
        country="France",
        patch={
            "unit_squadron": "Flottille 11F",
            "base": "BAN Landivisiau",
            "material": "EMBROIDERED",
            "attachment_type": "HOOK_VELCRO",
            "shape": "SHIELD",
        },
    )
    assert item["patch"]["material"] == "EMBROIDERED"
    assert item["patch"]["base"] == "BAN Landivisiau"
    assert item["diecast"] is None


def test_list_returns_total_and_items(admin_client, create_item):
    create_item(name="A")
    create_item(name="B")
    payload = admin_client.get("/api/items").json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 2


def test_partial_update_merges_nested_details(admin_client, create_item):
    item = create_item(diecast={"scale": "1/72", "manufacturer": "Hobby Master"})

    response = admin_client.patch(
        f"/api/items/{item['id']}",
        json={"status": "EXHIBITED", "tags": ["Tiger Meet"], "diecast": {"scale": "1/48"}},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["status"] == "EXHIBITED"
    assert updated["diecast"]["scale"] == "1/48"
    # Les champs non fournis sont conservés
    assert updated["diecast"]["manufacturer"] == "Hobby Master"
    assert [tag["name"] for tag in updated["tags"]] == ["Tiger Meet"]


def test_loan_fields_round_trip(admin_client, create_item):
    item = create_item()
    response = admin_client.patch(
        f"/api/items/{item['id']}",
        json={"loaned_to": "Club aéro", "loan_date": "2026-01-10", "loan_due_date": "2026-03-01"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["loaned_to"] == "Club aéro"
    assert payload["loan_due_date"] == "2026-03-01"


def test_validation_errors(admin_client):
    assert admin_client.post("/api/items", json={"name": "", "item_type": "PATCH"}).status_code == 422
    assert admin_client.post("/api/items", json={"name": "X", "item_type": "BOGUS"}).status_code == 422


def test_implausible_purchase_date_is_rejected(admin_client, create_item):
    """Un champ date mal saisi (« 05/05 » → an 0005) ne doit pas passer."""
    response = admin_client.post(
        "/api/items",
        json={"name": "Date douteuse", "item_type": "OTHER", "purchase_date": "0005-05-05"},
    )
    assert response.status_code == 422
    assert "année hors limites" in response.text

    item = create_item(name="Date correcte", purchase_date="2022-05-05")
    assert admin_client.patch(f"/api/items/{item['id']}", json={"purchase_date": "0005-05-05"}).status_code == 422
    assert admin_client.patch(f"/api/items/{item['id']}", json={"purchase_date": "2021-03-02"}).status_code == 200


def test_missing_item_returns_404(admin_client):
    assert admin_client.get("/api/items/999999").status_code == 404


def test_delete_removes_item(admin_client, create_item):
    item = create_item(name="À supprimer")
    assert admin_client.delete(f"/api/items/{item['id']}").status_code == 204
    assert admin_client.get(f"/api/items/{item['id']}").status_code == 404
    assert admin_client.get("/api/items").json()["total"] == 0


def test_tags_endpoint_lists_vocabulary(admin_client, create_item):
    create_item(name="A", tags=["Marine"])
    create_item(name="B", tags=["Rafale"])
    assert sorted(tag["name"] for tag in admin_client.get("/api/tags").json()) == ["Marine", "Rafale"]
