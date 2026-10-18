"""Médias : upload, conversion WebP, vignettes, photo principale, ordre."""

from __future__ import annotations

from PIL import Image

from app import media


def test_upload_converts_to_webp_with_thumbnail(admin_client, create_item, upload_photo):
    item = create_item()
    photo = upload_photo(item["id"], caption="Gros plan dérive")

    assert photo["file_path"].endswith(".webp")
    assert (photo["thumb_path"] or "").endswith("_thumb.webp")
    assert photo["is_primary"] is True
    assert photo["caption"] == "Gros plan dérive"

    main_file = media.UPLOAD_DIR / photo["file_path"]
    thumb_file = media.UPLOAD_DIR / photo["thumb_path"]
    assert main_file.is_file() and thumb_file.is_file()

    with Image.open(main_file) as image:
        assert image.format == "WEBP"
        assert max(image.size) <= 1600
    with Image.open(thumb_file) as image:
        assert max(image.size) <= 480


def test_static_file_is_served_as_webp(admin_client, create_item, upload_photo):
    photo = upload_photo(create_item()["id"])
    response = admin_client.get(f"/uploads/{photo['file_path']}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"


def test_first_photo_is_primary_then_primary_can_switch(admin_client, create_item, upload_photo):
    item = create_item()
    first = upload_photo(item["id"])
    second = upload_photo(item["id"])
    assert first["is_primary"] is True
    assert second["is_primary"] is False

    response = admin_client.post(f"/api/photos/{second['id']}/primary")
    assert response.status_code == 200

    photos = admin_client.get(f"/api/items/{item['id']}/photos").json()
    assert [photo["id"] for photo in photos if photo["is_primary"]] == [second["id"]]


def test_photo_caption_can_be_updated(admin_client, create_item, upload_photo):
    photo = upload_photo(create_item()["id"])
    response = admin_client.patch(f"/api/photos/{photo['id']}", json={"caption": "Vue de dos"})
    assert response.status_code == 200
    assert response.json()["caption"] == "Vue de dos"


def test_photo_order_can_be_changed(admin_client, create_item, upload_photo):
    item = create_item()
    first = upload_photo(item["id"])
    second = upload_photo(item["id"])
    third = upload_photo(item["id"])

    response = admin_client.post(
        f"/api/items/{item['id']}/photos/reorder",
        json={"ids": [third["id"], first["id"], second["id"]]},
    )
    assert response.status_code == 200, response.text
    assert [photo["id"] for photo in response.json()] == [third["id"], first["id"], second["id"]]

    listed = admin_client.get(f"/api/items/{item['id']}/photos").json()
    assert [photo["id"] for photo in listed] == [third["id"], first["id"], second["id"]]


def test_uploads_are_rejected_when_invalid(admin_client, create_item, png_bytes):
    item = create_item()

    not_an_image = admin_client.post(
        f"/api/items/{item['id']}/photos",
        files={"file": ("notes.txt", b"pas une image", "text/plain")},
    )
    assert not_an_image.status_code == 400

    too_big = admin_client.post(
        f"/api/items/{item['id']}/photos",
        files={"file": ("big.jpg", b"\x00" * (16 * 1024 * 1024), "image/jpeg")},
    )
    assert too_big.status_code == 413

    missing_item = admin_client.post(
        "/api/items/999999/photos",
        files={"file": ("x.png", png_bytes(size=(10, 10)), "image/png")},
    )
    assert missing_item.status_code == 404


def test_deleting_photo_removes_file_and_promotes_next(admin_client, create_item, upload_photo):
    item = create_item()
    first = upload_photo(item["id"])
    second = upload_photo(item["id"])
    admin_client.post(f"/api/photos/{second['id']}/primary")

    second_file = media.UPLOAD_DIR / second["file_path"]
    assert admin_client.delete(f"/api/photos/{second['id']}").status_code == 204
    assert not second_file.is_file()

    remaining = admin_client.get(f"/api/items/{item['id']}/photos").json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == first["id"]
    assert remaining[0]["is_primary"] is True


def test_deleting_item_removes_its_files(admin_client, create_item, upload_photo):
    item = create_item()
    photo = upload_photo(item["id"])
    path = media.UPLOAD_DIR / photo["file_path"]

    assert admin_client.delete(f"/api/items/{item['id']}").status_code == 204
    assert not path.is_file()
    assert not any(media.UPLOAD_DIR.rglob("*.webp"))
