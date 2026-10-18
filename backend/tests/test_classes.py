"""Classes hiérarchiques : création, filtre par descendance, déplacement, suppression."""

from __future__ import annotations


def ids_of(response):
    return sorted(item["id"] for item in response.json()["items"])


def make_class(client, name, parent_id=None):
    response = client.post("/api/admin/classes", json={"name": name, "parent_id": parent_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_class_tree_is_listed_flat_with_counts(admin_client, create_item):
    root = make_class(admin_client, "Aéronefs")
    child = make_class(admin_client, "Chasseur", root["id"])
    leaf = make_class(admin_client, "Rafale", child["id"])

    create_item(name="Rafale M", class_id=leaf["id"])

    classes = admin_client.get("/api/classes").json()
    assert {node["name"]: node["parent_id"] for node in classes} == {
        "Aéronefs": None,
        "Chasseur": root["id"],
        "Rafale": child["id"],
    }
    assert {node["name"]: node["item_count"] for node in classes} == {
        "Aéronefs": 0,
        "Chasseur": 0,
        "Rafale": 1,
    }


def test_filter_on_a_class_includes_descendants(admin_client, create_item):
    root = make_class(admin_client, "Aéronefs")
    child = make_class(admin_client, "Chasseur", root["id"])
    leaf = make_class(admin_client, "Rafale", child["id"])
    other = make_class(admin_client, "Écussons")

    rafale = create_item(name="Rafale M", class_id=leaf["id"])
    patch = create_item(name="Patch", item_type="PATCH", class_id=other["id"])
    create_item(name="Sans classe")

    assert ids_of(admin_client.get("/api/items", params={"class_id": root["id"]})) == [rafale["id"]]
    assert ids_of(admin_client.get("/api/items", params={"class_id": child["id"]})) == [rafale["id"]]
    assert ids_of(admin_client.get("/api/items", params={"class_id": other["id"]})) == [patch["id"]]
    assert admin_client.get("/api/items").json()["total"] == 3


def test_duplicate_name_rejected_at_the_same_level(admin_client):
    make_class(admin_client, "Aéronefs")
    assert admin_client.post("/api/admin/classes", json={"name": "Aéronefs"}).status_code == 409

    other = make_class(admin_client, "Écussons")
    # Un même nom est autorisé sous un autre parent
    assert admin_client.post(
        "/api/admin/classes", json={"name": "Aéronefs", "parent_id": other["id"]}
    ).status_code == 201


def test_rename_and_move(admin_client):
    root = make_class(admin_client, "Aéronefs")
    branch = make_class(admin_client, "Chasseur", root["id"])
    node = make_class(admin_client, "Rafale", branch["id"])

    renamed = admin_client.patch(f"/api/admin/classes/{node['id']}", json={"name": "Rafale M"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Rafale M"

    moved = admin_client.patch(f"/api/admin/classes/{node['id']}", json={"parent_id": root["id"]})
    assert moved.status_code == 200 and moved.json()["parent_id"] == root["id"]

    # Remonter à la racine
    detached = admin_client.patch(f"/api/admin/classes/{node['id']}", json={"parent_id": None})
    assert detached.status_code == 200 and detached.json()["parent_id"] is None


def test_a_class_cannot_be_moved_under_itself(admin_client):
    root = make_class(admin_client, "Aéronefs")
    child = make_class(admin_client, "Chasseur", root["id"])
    leaf = make_class(admin_client, "Rafale", child["id"])

    assert admin_client.patch(f"/api/admin/classes/{root['id']}", json={"parent_id": root["id"]}).status_code == 400
    assert admin_client.patch(f"/api/admin/classes/{root['id']}", json={"parent_id": leaf["id"]}).status_code == 400
    assert admin_client.patch("/api/admin/classes/99999", json={"name": "X"}).status_code == 404


def test_deleting_a_class_with_items_requires_confirmation(admin_client, create_item):
    root = make_class(admin_client, "Aéronefs")
    child = make_class(admin_client, "Chasseur", root["id"])
    item = create_item(name="Rafale M", class_id=child["id"])

    refused = admin_client.delete(f"/api/admin/classes/{root['id']}")
    assert refused.status_code == 409
    assert "1 objet(s)" in refused.json()["detail"]

    # Avec confirmation : la classe et sa descendance partent, l'objet reste
    assert admin_client.delete(f"/api/admin/classes/{root['id']}", params={"force": True}).status_code == 204
    assert admin_client.get("/api/classes").json() == []
    assert admin_client.get(f"/api/items/{item['id']}").json()["class_id"] is None


def test_viewer_cannot_manage_classes(admin_client, create_item):
    admin_client.post(
        "/api/admin/users",
        json={"username": "lecteur", "password": "lecteurpass", "role": "VIEWER"},
    )
    admin_client.post("/api/admin/logout")
    admin_client.post("/api/admin/login", json={"username": "lecteur", "password": "lecteurpass"})

    assert admin_client.get("/api/classes").status_code == 200
    assert admin_client.post("/api/admin/classes", json={"name": "Test"}).status_code == 403
