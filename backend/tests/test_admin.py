"""Authentification, comptes, actions en masse, import/export, sauvegarde."""

from __future__ import annotations

from helpers import ADMIN_LOGIN, BASE_URL, SETTINGS_URL, restore, set_rates

from app import auth, media

VIEWER = {"username": "viewer", "password": "viewerpass", "role": "VIEWER"}


def _admin_id(client) -> int:
    return next(u["id"] for u in client.get("/api/admin/users").json() if u["username"] == "admin")


# --------------------------------------------------------------------------- #
# Accès protégé
# --------------------------------------------------------------------------- #
def test_everything_requires_auth(client, admin_client, create_item, upload_photo):
    photo = upload_photo(create_item()["id"])
    admin_client.post("/api/admin/logout")

    assert client.get("/api/items").status_code == 401
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/meta/facets").status_code == 401
    assert client.get(f"/uploads/{photo['file_path']}").status_code == 401
    assert client.get("/openapi.json").status_code == 401

    # Santé et session restent accessibles pour permettre la connexion
    assert client.get("/api/health").status_code == 200
    session = client.get("/api/admin/session").json()
    assert session == {
        "enabled": True,
        "authenticated": False,
        "username": None,
        "role": None,
    }


def test_login_session_and_logout(client):
    assert client.post("/api/admin/login", json={"username": "admin", "password": "faux"}).status_code == 401

    response = client.post("/api/admin/login", json=ADMIN_LOGIN)
    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "ADMIN" and payload["username"] == "admin"

    session = client.get("/api/admin/session").json()
    assert session["authenticated"] is True and session["role"] == "ADMIN"

    assert client.post("/api/admin/logout").status_code == 204
    assert client.get("/api/admin/session").json()["authenticated"] is False
    assert client.get("/api/items").status_code == 401


def test_login_is_throttled(client, monkeypatch):
    monkeypatch.setenv("ADMIN_MAX_FAILURES", "3")
    auth.reset_failures()
    codes = [
        client.post("/api/admin/login", json={"username": "admin", "password": "faux"}).status_code
        for _ in range(4)
    ]
    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429


def test_bearer_token_is_accepted(tmp_path, client):
    token = client.post("/api/admin/login", json=ADMIN_LOGIN).json()["token"]
    client.post("/api/admin/logout")

    response = client.get("/api/items", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# Comptes et rôles
# --------------------------------------------------------------------------- #
def test_viewer_is_read_only(admin_client, create_item):
    create_item(name="Visible")
    assert admin_client.post("/api/admin/users", json=VIEWER).status_code == 201
    admin_client.post("/api/admin/logout")
    assert admin_client.post("/api/admin/login", json={"username": "viewer", "password": "viewerpass"}).status_code == 200

    assert admin_client.get("/api/items").status_code == 200
    assert admin_client.get("/api/admin/export").status_code == 200
    assert admin_client.get("/api/admin/backup").status_code == 200

    assert admin_client.post("/api/items", json={"name": "X", "item_type": "OTHER"}).status_code == 403
    assert admin_client.post("/api/admin/users", json=VIEWER).status_code == 403
    assert admin_client.post("/api/admin/bulk", json={"ids": [1], "action": "delete"}).status_code == 403


def test_duplicate_username_is_rejected(admin_client):
    assert admin_client.post("/api/admin/users", json=VIEWER).status_code == 201
    assert admin_client.post("/api/admin/users", json=VIEWER).status_code == 409


def test_last_admin_is_protected(admin_client):
    admin_id = _admin_id(admin_client)
    assert admin_client.patch(f"/api/admin/users/{admin_id}", json={"role": "VIEWER"}).status_code == 409
    assert admin_client.patch(f"/api/admin/users/{admin_id}", json={"is_active": False}).status_code == 409


def test_cannot_delete_own_account(admin_client):
    assert admin_client.delete(f"/api/admin/users/{_admin_id(admin_client)}").status_code == 409


def test_admin_can_be_demoted_when_another_admin_exists(admin_client):
    admin_client.post("/api/admin/users", json={"username": "second", "password": "secondpass", "role": "ADMIN"})
    assert admin_client.patch(f"/api/admin/users/{_admin_id(admin_client)}", json={"role": "VIEWER"}).status_code == 200


def test_password_change_takes_effect(admin_client):
    created = admin_client.post("/api/admin/users", json=VIEWER).json()
    assert admin_client.patch(f"/api/admin/users/{created['id']}", json={"password": "nouveaupass"}).status_code == 200

    admin_client.post("/api/admin/logout")
    assert admin_client.post("/api/admin/login", json={"username": "viewer", "password": "viewerpass"}).status_code == 401
    assert admin_client.post("/api/admin/login", json={"username": "viewer", "password": "nouveaupass"}).status_code == 200


# --------------------------------------------------------------------------- #
# Actions en masse
# --------------------------------------------------------------------------- #
def test_bulk_actions(admin_client, create_item):
    first = create_item(name="Un", tags=["alpha"])
    second = create_item(name="Deux")
    third = create_item(name="Trois")
    ids = [first["id"], second["id"], third["id"]]

    response = admin_client.post("/api/admin/bulk", json={"ids": ids, "action": "set_status", "status": "WANTED"})
    assert response.json() == {"action": "set_status", "affected": 3}
    assert all(admin_client.get(f"/api/items/{i}").json()["status"] == "WANTED" for i in ids)

    assert admin_client.post(
        "/api/admin/bulk", json={"ids": [first["id"], second["id"]], "action": "add_tags", "tags": ["nato", "marine"]}
    ).json()["affected"] == 2
    assert {t["name"] for t in admin_client.get(f"/api/items/{first['id']}").json()["tags"]} == {"alpha", "nato", "marine"}

    admin_client.post("/api/admin/bulk", json={"ids": [first["id"]], "action": "remove_tags", "tags": ["nato"]})
    assert {t["name"] for t in admin_client.get(f"/api/items/{first['id']}").json()["tags"]} == {"alpha", "marine"}

    assert admin_client.post("/api/admin/bulk", json={"ids": [third["id"]], "action": "delete"}).json()["affected"] == 1
    assert admin_client.get(f"/api/items/{third['id']}").status_code == 404

    # Validations
    assert admin_client.post("/api/admin/bulk", json={"ids": [first["id"]], "action": "set_status"}).status_code == 400
    assert admin_client.post("/api/admin/bulk", json={"ids": [], "action": "delete"}).status_code == 422


# --------------------------------------------------------------------------- #
# Export / import
# --------------------------------------------------------------------------- #
def test_backup_carries_settings_and_accounts(admin_client, create_item):
    """La sauvegarde ZIP est complète : réglages (devise, taux) et comptes."""
    set_rates(admin_client, {"EUR": 1.0, "USD": 2.0})
    admin_client.put(BASE_URL, json={"default_currency": "USD"})
    created = admin_client.post(
        "/api/admin/users",
        json={"username": "archiviste", "password": "archiviste1", "role": "ADMIN"},
    ).json()

    archive = admin_client.get("/api/admin/backup").content

    # On repart d'un état différent
    admin_client.put(BASE_URL, json={"default_currency": "EUR"})
    set_rates(admin_client, {"EUR": 1.0})
    assert admin_client.delete(f"/api/admin/users/{created['id']}").status_code == 204

    response = restore(admin_client, archive, "merge")
    assert response.status_code == 200, response.text
    assert response.json()["users_restored"] == 1

    settings_after = admin_client.get(SETTINGS_URL).json()
    assert settings_after["default_currency"] == "USD"
    assert settings_after["rates"]["USD"] == 2.0
    assert "archiviste" in {user["username"] for user in admin_client.get("/api/admin/users").json()}


def test_restore_does_not_overwrite_existing_account(admin_client):
    """Un compte existant n'est jamais écrasé par une restauration."""
    archive = admin_client.get("/api/admin/backup").content
    response = restore(admin_client, archive, "merge")
    assert response.status_code == 200
    assert response.json()["users_restored"] == 0
    # Le mot de passe en vigueur reste valide
    admin_client.post("/api/admin/logout")
    assert admin_client.post("/api/admin/login", json=ADMIN_LOGIN).status_code == 200


def test_export_json_and_csv(admin_client, create_item):
    create_item(name="Exporté", country="France", estimated_value=12.5)

    exported = admin_client.get("/api/admin/export").json()
    assert exported["total"] == 1
    assert exported["items"][0]["name"] == "Exporté"

    csv_response = admin_client.get("/api/admin/export.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    lines = csv_response.text.strip().splitlines()
    assert lines[0].startswith("id,name,item_type")
    assert len(lines) == 2


def test_import_json(admin_client):
    payload = [
        {"name": "Importé A", "item_type": "PATCH", "country": "Pologne", "tags": ["import"],
         "patch": {"unit_squadron": "313th Squadron", "material": "PVC"}},
        {"name": "Importé B", "item_type": "DIECAST", "diecast": {"scale": "1/200"}},
    ]
    response = admin_client.post("/api/admin/import", json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {"created": 2, "errors": []}
    assert admin_client.get("/api/items").json()["total"] == 2


def test_import_json_reports_bad_entries(admin_client):
    response = admin_client.post("/api/admin/import", json=[{"item_type": "OTHER"}])
    assert response.status_code == 422  # `name` manquant -> validation Pydantic


def test_import_csv(admin_client):
    content = (
        "name,item_type,country,status,estimated_value,scale,manufacturer,tags\n"
        'CSV 1,DIECAST,France,STORED_BOX,42,1/72,Hobby Master,"a, b"\n'
        "CSV 2,OTHER,,,,,,\n"
    )
    response = admin_client.post(
        "/api/admin/import.csv",
        files={"file": ("data.csv", content.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 2

    items = {item["name"]: item for item in admin_client.get("/api/items").json()["items"]}
    assert items["CSV 1"]["estimated_value"] == 42
    assert items["CSV 1"]["diecast"]["scale"] == "1/72"
    assert sorted(t["name"] for t in items["CSV 1"]["tags"]) == ["a", "b"]
    assert items["CSV 2"]["item_type"] == "OTHER"


def test_import_csv_requires_name_column(admin_client):
    response = admin_client.post(
        "/api/admin/import.csv",
        files={"file": ("bad.csv", b"foo,bar\n1,2\n", "text/csv")},
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Sauvegarde / restauration
# --------------------------------------------------------------------------- #
def test_backup_and_restore_replace(admin_client, create_item, upload_photo):
    item = create_item(name="Sauvegardé", estimated_value=99, tags=["archive"],
                       diecast={"scale": "1/72", "manufacturer": "Corgi"})
    upload_photo(item["id"], caption="vue")

    archive = admin_client.get("/api/admin/backup").content
    assert archive[:2] == b"PK"

    admin_client.post("/api/admin/bulk", json={"ids": [item["id"]], "action": "delete"})
    assert admin_client.get("/api/items").json()["total"] == 0

    response = restore(admin_client, archive, "replace")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["created"] == 1 and result["photos_restored"] == 1 and result["replaced"] is True

    restored = admin_client.get("/api/items").json()["items"][0]
    assert restored["name"] == "Sauvegardé"
    assert restored["diecast"]["manufacturer"] == "Corgi"
    assert [t["name"] for t in restored["tags"]] == ["archive"]
    assert len(restored["photos"]) == 1
    assert restored["photos"][0]["caption"] == "vue"
    assert (media.UPLOAD_DIR / restored["photos"][0]["file_path"]).is_file()


def test_restore_merge_keeps_existing(admin_client, create_item):
    create_item(name="Déjà là")
    archive = admin_client.get("/api/admin/backup").content

    response = restore(admin_client, archive, "merge")
    assert response.status_code == 200
    assert response.json()["created"] == 1
    assert admin_client.get("/api/items").json()["total"] == 2


def test_restore_rejects_invalid_archive(admin_client):
    response = restore(admin_client, b"pas un zip", "merge")
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Tags
# --------------------------------------------------------------------------- #
def test_tag_rename_and_delete(admin_client, create_item):
    create_item(name="Avec tag", tags=["import"])
    tags = {tag["name"]: tag["id"] for tag in admin_client.get("/api/tags").json()}
    create_item(name="Autre", tags=["marine"])

    assert admin_client.patch(f"/api/admin/tags/{tags['import']}", json={"name": "import-2026"}).status_code == 200
    assert admin_client.patch(f"/api/admin/tags/{tags['import']}", json={"name": "marine"}).status_code == 409
    assert admin_client.patch("/api/admin/tags/9999", json={"name": "x"}).status_code == 404

    assert admin_client.delete(f"/api/admin/tags/{tags['import']}").status_code == 204
    assert "import-2026" not in {tag["name"] for tag in admin_client.get("/api/tags").json()}
