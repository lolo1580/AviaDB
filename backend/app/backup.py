"""Sauvegarde et restauration — archive ZIP contenant le JSON et les images.

Format de l'archive :
    aviadb.json          export complet (items + détails + tags + photos)
    images/…             tous les fichiers du dossier uploads/

La restauration accepte les archives produites ici comme les exports JSON
renvoyés par `/api/admin/export`.
"""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import auth, crud, currency, media, models, schemas

logger = logging.getLogger("aviadb.backup")

MANIFEST_NAME = "aviadb.json"
IMAGES_PREFIX = "images"

# Bornes de sécurité à la restauration : une archive piégée (ou simplement
# énorme) ne doit pas épuiser la mémoire du conteneur.
MAX_ARCHIVE_BYTES = int(os.getenv("MAX_BACKUP_BYTES", 256 * 1024 * 1024))
MAX_UNCOMPRESSED_BYTES = int(os.getenv("MAX_BACKUP_UNCOMPRESSED", 1024 * 1024 * 1024))
MAX_ARCHIVE_ENTRIES = int(os.getenv("MAX_BACKUP_ENTRIES", 20000))

_ITEM_LOADS = (
    selectinload(models.Item.diecast),
    selectinload(models.Item.patch),
    selectinload(models.Item.photos),
    selectinload(models.Item.tags),
    selectinload(models.Item.links),
    selectinload(models.Item.price_points),
)


def _details(raw, model_cls):
    """Ne conserve que les champs connus du schéma de détails."""
    if not isinstance(raw, dict):
        return None
    allowed = set(model_cls.model_fields)
    return model_cls(**{key: value for key, value in raw.items() if key in allowed})


def _tag_names(raw) -> list[str]:
    names = []
    for tag in raw or []:
        name = tag.get("name") if isinstance(tag, dict) else tag
        if name:
            names.append(str(name))
    return names


def _dump_settings(db: Session) -> dict:
    """Tous les réglages (devise de référence, taux, cache des taux historiques)."""
    dumped = {}
    for row in db.scalars(select(models.Setting)).all():
        try:
            dumped[row.key] = json.loads(row.value)
        except (TypeError, ValueError):
            continue
    return dumped


def _dump_users(db: Session) -> list[dict]:
    """Comptes, empreintes de mots de passe incluses (jamais en clair)."""
    return [
        {
            "username": user.username,
            "password_hash": user.password_hash,
            "role": user.role.value,
            "is_active": user.is_active,
        }
        for user in db.scalars(select(models.User).order_by(models.User.username)).all()
    ]


def build_backup_file(db: Session) -> Path:
    """Écrit l'archive de sauvegarde dans un fichier temporaire.

    On évite de tout garder en mémoire : une collection de photos peut peser
    plusieurs centaines de Mo. Le fichier est supprimé par l'appelant.
    """
    items = (
        db.scalars(select(models.Item).options(*_ITEM_LOADS).order_by(models.Item.id)).all()
    )
    document = {
        "version": 2,
        "exported_at": datetime.now(UTC).isoformat(),
        "total": len(items),
        "items": [schemas.ItemOut.model_validate(item).model_dump(mode="json") for item in items],
        "settings": _dump_settings(db),
        "users": _dump_users(db),
    }

    handle = tempfile.NamedTemporaryFile(prefix="aviadb-backup-", suffix=".zip", delete=False)
    handle.close()
    target = Path(handle.name)

    try:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(document, ensure_ascii=False, indent=2))
            for path in sorted(media.UPLOAD_DIR.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(media.UPLOAD_DIR).as_posix()
                    archive.write(path, f"{IMAGES_PREFIX}/{relative}")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def _restore_item(db: Session, entry: dict) -> models.Item:
    payload = schemas.ItemCreate(
        name=entry["name"],
        item_type=entry.get("item_type", models.ItemType.OTHER.value),
        country=entry.get("country"),
        aircraft_model=entry.get("aircraft_model"),
        storage_location=entry.get("storage_location"),
        status=entry.get("status", models.ItemStatus.STORED_BOX.value),
        purchase_date=entry.get("purchase_date"),
        purchase_price=entry.get("purchase_price"),
        estimated_value=entry.get("estimated_value"),
        currency=entry.get("currency"),
        notes=entry.get("notes"),
        loaned_to=entry.get("loaned_to"),
        loan_date=entry.get("loan_date"),
        loan_due_date=entry.get("loan_due_date"),
        tags=_tag_names(entry.get("tags")),
        diecast=_details(entry.get("diecast"), schemas.DiecastDetailsIn),
        patch=_details(entry.get("patch"), schemas.PatchDetailsIn),
    )
    item = crud.create_item(db, payload)

    # On conserve l'équivalent EUR et le taux historique tels qu'enregistrés,
    # pour que la restauration ne dépende pas d'un nouvel appel réseau.
    if entry.get("purchase_eur_value") is not None:
        item.purchase_eur_value = float(entry["purchase_eur_value"])
        raw_date = entry.get("purchase_rate_date")
        item.purchase_rate_date = date.fromisoformat(raw_date) if raw_date else None

    for position, photo in enumerate(entry.get("photos") or []):
        if not isinstance(photo, dict) or not photo.get("file_path"):
            continue
        item.photos.append(
            models.ItemPhoto(
                file_path=photo["file_path"],
                thumb_path=photo.get("thumb_path"),
                caption=photo.get("caption"),
                position=int(photo.get("position", position)),
                is_primary=bool(photo.get("is_primary")),
            )
        )

    for link in entry.get("links") or []:
        if isinstance(link, dict) and link.get("url"):
            item.links.append(models.ItemLink(url=link["url"], label=link.get("label")))

    for point in entry.get("price_points") or []:
        if not isinstance(point, dict) or point.get("price") is None:
            continue
        recorded = point.get("recorded_on")
        item.price_points.append(
            models.PricePoint(
                price=float(point["price"]),
                currency=(point.get("currency") or item.currency or "EUR"),
                eur_value=point.get("eur_value"),
                recorded_on=date.fromisoformat(recorded) if recorded else date.today(),
                source_url=point.get("source_url"),
                note=point.get("note"),
            )
        )
    return item


def restore_backup(db: Session, upload: UploadFile, replace: bool) -> dict:
    """Restaure une archive. `replace=True` vide la collection au préalable."""
    data = upload.file.read(MAX_ARCHIVE_BYTES + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fichier vide")
    if len(data) > MAX_ARCHIVE_BYTES:
        raise HTTPException(
            413,
            f"Archive trop volumineuse (max {MAX_ARCHIVE_BYTES // (1024 * 1024)} Mo)",
        )

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Archive ZIP illisible") from None

    # Garde-fous contre les archives pièges : nombre d'entrées et volume
    # décompressé annoncés, avant toute écriture sur disque.
    entries_meta = [info for info in archive.infolist() if not info.is_dir()]
    if len(entries_meta) > MAX_ARCHIVE_ENTRIES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Archive refusée : {len(entries_meta)} entrées (max {MAX_ARCHIVE_ENTRIES})",
        )
    total_size = sum(info.file_size for info in entries_meta)
    if total_size > MAX_UNCOMPRESSED_BYTES:
        raise HTTPException(
            413,
            "Archive refusée : volume décompressé trop important "
            f"({total_size // (1024 * 1024)} Mo, max {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} Mo)",
        )

    if MANIFEST_NAME not in archive.namelist():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"« {MANIFEST_NAME} » absent de l'archive"
        )

    try:
        document = json.loads(archive.read(MANIFEST_NAME))
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Manifeste JSON invalide") from None

    entries = document.get("items") if isinstance(document, dict) else document
    if not isinstance(entries, list):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Format inattendu : « items » doit être une liste"
        )

    errors: list[str] = []

    if replace:
        for item in db.scalars(select(models.Item).options(*_ITEM_LOADS)).all():
            media.delete_files(
                *[p.file_path for p in item.photos],
                *[p.thumb_path for p in item.photos],
            )
            db.delete(item)
        db.flush()

    # 0) Réglages (devise de référence, taux) — restaurés avant les objets pour
    #    que les conversions soient calculées dans la bonne devise.
    settings_document = document.get("settings") if isinstance(document, dict) else None
    if isinstance(settings_document, dict):
        for key, value in settings_document.items():
            currency.set_setting(db, key, value)
        db.flush()

    # Les comptes présents dans l'archive sont recréés s'ils n'existent pas ;
    # un compte existant n'est jamais écrasé (on ne se verrouille pas dehors).
    users_document = document.get("users") if isinstance(document, dict) else None
    restored_users = 0
    if isinstance(users_document, list):
        for entry in users_document:
            if not isinstance(entry, dict) or not entry.get("username"):
                continue
            existing = db.scalars(
                select(models.User).where(models.User.username == entry["username"])
            ).first()
            if existing is not None:
                continue
            try:
                db.add(
                    models.User(
                        username=entry["username"],
                        password_hash=entry["password_hash"],
                        role=models.UserRole(entry.get("role", models.UserRole.VIEWER.value)),
                        is_active=bool(entry.get("is_active", True)),
                    )
                )
                db.flush()
                restored_users += 1
            except (KeyError, ValueError) as exc:
                errors.append(f"compte {entry.get('username')!r} ignoré : {exc}")
        auth.refresh_protection(db)

    # 1) Les images d'abord, pour que les enregistrements y fassent référence.
    restored_files = 0
    for name in archive.namelist():
        if not name.startswith(f"{IMAGES_PREFIX}/") or name.endswith("/"):
            continue
        relative = PurePosixPath(name).relative_to(IMAGES_PREFIX)
        target = (media.UPLOAD_DIR / relative.as_posix()).resolve()
        if not target.is_relative_to(media.UPLOAD_DIR):
            errors.append(f"chemin ignoré : {name}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(name))
        restored_files += 1

    # 2) Puis les objets, chacun dans un point de sauvegarde (une erreur
    #    n'annule pas les précédents).
    created = 0
    photos = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not entry.get("name"):
            errors.append(f"entrée {index} ignorée : nom manquant")
            continue
        try:
            with db.begin_nested():
                _restore_item(db, entry)
                db.flush()
            created += 1
            photos += len(entry.get("photos") or [])
        except Exception as exc:  # noqa: BLE001 - on rapporte l'erreur telle quelle
            errors.append(f"entrée {index} ({entry.get('name')!r}) : {exc}")

    db.commit()
    logger.info(
        "Restauration : %s objet(s), %s photo(s), %s fichier(s) d'image, "
        "%s compte(s) (remplacement=%s)",
        created,
        photos,
        restored_files,
        restored_users,
        replace,
    )
    return {
        "created": created,
        "photos_restored": photos,
        "users_restored": restored_users,
        "replaced": replace,
        "errors": errors,
    }
