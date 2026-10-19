"""Médias : upload, WebP, variantes à la volée, transformation, dédoublonnage."""

from __future__ import annotations

import io

from PIL import Image

from app import media, models
from app.database import SessionLocal


def test_upload_converts_to_webp_without_stored_thumbnail(
    admin_client, create_item, upload_photo
):
    item = create_item()
    photo = upload_photo(item["id"], caption="Gros plan dérive")

    assert photo["file_path"].endswith(".webp")
    # La vignette n'est plus stockée : elle est générée à la demande.
    assert photo["thumb_path"] is None
    assert photo["is_primary"] is True
    assert photo["caption"] == "Gros plan dérive"

    main_file = media.UPLOAD_DIR / photo["file_path"]
    assert main_file.is_file()
    with Image.open(main_file) as image:
        assert image.format == "WEBP"
        assert max(image.size) <= 1600


def test_thumbnail_is_generated_on_the_fly(admin_client, create_item, upload_photo):
    photo = upload_photo(create_item()["id"])

    response = admin_client.get(f"/uploads/{photo['file_path']}", params={"w": 120})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    with Image.open(io.BytesIO(response.content)) as image:
        assert max(image.size) <= 120

    # La variante est mise en cache sur disque pour les appels suivants.
    cache = media.UPLOAD_DIR / photo["file_path"].replace(".webp", "_w120.webp")
    assert cache.is_file()


def test_variant_width_is_bounded(admin_client, create_item, upload_photo):
    photo = upload_photo(create_item()["id"])
    response = admin_client.get(f"/uploads/{photo['file_path']}", params={"w": 10})
    assert response.status_code == 422


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


def test_duplicate_upload_is_not_stored_twice(admin_client, create_item, png_bytes):
    item = create_item()
    payload = png_bytes(size=(120, 90))

    first = admin_client.post(
        f"/api/items/{item['id']}/photos",
        files={"file": ("a.png", payload, "image/png")},
    )
    second = admin_client.post(
        f"/api/items/{item['id']}/photos",
        files={"file": ("b.png", payload, "image/png")},
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    photos = admin_client.get(f"/api/items/{item['id']}/photos").json()
    assert len(photos) == 1
    folder = media.UPLOAD_DIR / "items" / str(item["id"])
    assert len(list(folder.glob("*.webp"))) == 1


def test_rotate_photo(admin_client, create_item, upload_photo):
    photo = upload_photo(create_item()["id"], size=(1200, 800))
    old_path = photo["file_path"]

    response = admin_client.patch(
        f"/api/photos/{photo['id']}/transform", json={"rotate": 90}
    )

    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated["file_path"] != old_path
    assert not (media.UPLOAD_DIR / old_path).is_file()
    with Image.open(media.UPLOAD_DIR / rotated["file_path"]) as image:
        assert image.height > image.width


def test_crop_photo(admin_client, create_item, upload_photo):
    photo = upload_photo(create_item()["id"], size=(1200, 800))
    before = photo["file_path"]

    response = admin_client.patch(
        f"/api/photos/{photo['id']}/transform",
        json={"crop": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}},
    )

    assert response.status_code == 200, response.text
    cropped = response.json()
    assert cropped["file_path"] != before
    with Image.open(media.UPLOAD_DIR / cropped["file_path"]) as image:
        assert max(image.size) <= 600  # 1200 × 0,5


def test_invalid_crop_is_rejected(admin_client, create_item, upload_photo):
    photo = upload_photo(create_item()["id"])
    response = admin_client.patch(
        f"/api/photos/{photo['id']}/transform",
        json={"crop": {"x": 0.8, "y": 0, "width": 0.5, "height": 0.5}},
    )
    assert response.status_code == 422


def test_cleanup_removes_unreferenced_files(admin_client, create_item, upload_photo):
    item = create_item()
    photo = upload_photo(item["id"])
    folder = media.UPLOAD_DIR / "items" / str(item["id"])
    orphan = folder / "orphelin.webp"
    orphan.write_bytes((media.UPLOAD_DIR / photo["file_path"]).read_bytes())

    with SessionLocal() as db:
        # Un fichier récent est protégé (téléversement en cours)...
        assert media.cleanup_orphans(db, min_age_seconds=3600) == 0
        # ... puis supprimé une fois le délai passé.
        assert media.cleanup_orphans(db, min_age_seconds=0) == 1

    assert not orphan.is_file()
    assert (media.UPLOAD_DIR / photo["file_path"]).is_file()


def test_legacy_thumbnails_are_removed(admin_client, create_item, upload_photo):
    item = create_item()
    photo = upload_photo(item["id"])
    folder = media.UPLOAD_DIR / "items" / str(item["id"])
    legacy = folder / "ancienne_thumb.webp"
    legacy.write_bytes((media.UPLOAD_DIR / photo["file_path"]).read_bytes())

    with SessionLocal() as db:
        row = db.get(models.ItemPhoto, photo["id"])
        row.thumb_path = legacy.relative_to(media.UPLOAD_DIR).as_posix()
        db.commit()
        assert media.drop_legacy_thumbnails(db) == 1

    assert not legacy.is_file()
    assert (media.UPLOAD_DIR / photo["file_path"]).is_file()
