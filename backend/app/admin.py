"""Routes d'administration.

Les lectures (export, sauvegarde) sont ouvertes à tout compte authentifié ;
les écritures et la gestion des comptes exigent le rôle ADMIN.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from starlette.background import BackgroundTask

from . import api_keys, auth, backup, crud, currency, media, models, pricing, report, schemas
from .database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ITEM_LOADS = (
    selectinload(models.Item.diecast),
    selectinload(models.Item.patch),
    selectinload(models.Item.photos),
    selectinload(models.Item.tags),
)

CSV_COLUMNS = [
    "id", "name", "item_type", "country", "aircraft_model", "storage_location",
    "status", "purchase_date", "purchase_price", "estimated_value", "currency",
    "notes", "loaned_to", "loan_date", "loan_due_date",
    "scale", "manufacturer", "part_number", "registration_number", "configuration",
    "unit_squadron", "base", "material", "attachment_type", "shape", "event_or_mission",
    "tags", "created_at", "updated_at",
]

# Colonnes de détails du CSV, regroupées par table d'attributs.
DETAIL_COLUMNS = {
    "diecast": ("scale", "manufacturer", "part_number", "registration_number", "configuration"),
    "patch": ("unit_squadron", "base", "material", "attachment_type", "shape", "event_or_mission"),
}


def _all_items(db: Session) -> list[models.Item]:
    return list(
        db.scalars(select(models.Item).options(*_ITEM_LOADS).order_by(models.Item.id)).all()
    )


def _clean(value):
    """Chaîne vide -> None, sinon valeur ébarbée."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    value = value.strip()
    return value or None


def _csv_row(item: models.Item) -> dict:
    diecast = item.diecast
    patch = item.patch
    return {
        "id": item.id,
        "name": item.name,
        "item_type": item.item_type.value,
        "country": item.country,
        "aircraft_model": item.aircraft_model,
        "storage_location": item.storage_location,
        "status": item.status.value,
        "purchase_date": item.purchase_date.isoformat() if item.purchase_date else "",
        "purchase_price": item.purchase_price if item.purchase_price is not None else "",
        "estimated_value": item.estimated_value if item.estimated_value is not None else "",
        "currency": item.currency or "",
        "notes": item.notes or "",
        "loaned_to": item.loaned_to or "",
        "loan_date": item.loan_date.isoformat() if item.loan_date else "",
        "loan_due_date": item.loan_due_date.isoformat() if item.loan_due_date else "",
        "scale": diecast.scale if diecast else "",
        "manufacturer": diecast.manufacturer if diecast else "",
        "part_number": diecast.part_number if diecast else "",
        "registration_number": diecast.registration_number if diecast else "",
        "configuration": diecast.configuration if diecast else "",
        "unit_squadron": patch.unit_squadron if patch else "",
        "base": patch.base if patch else "",
        "material": patch.material.value if patch and patch.material else "",
        "attachment_type": patch.attachment_type.value if patch and patch.attachment_type else "",
        "shape": patch.shape.value if patch and patch.shape else "",
        "event_or_mission": patch.event_or_mission if patch else "",
        "tags": ", ".join(sorted(t.name for t in item.tags)),
        "created_at": item.created_at.isoformat() if item.created_at else "",
        "updated_at": item.updated_at.isoformat() if item.updated_at else "",
    }


# --------------------------------------------------------------------------- #
# Actions en masse (ADMIN)
# --------------------------------------------------------------------------- #
@router.post(
    "/bulk",
    response_model=schemas.BulkResultOut,
    dependencies=[Depends(auth.require_admin)],
)
def bulk_action(payload: schemas.BulkActionIn, db: Session = Depends(get_db)):
    items = list(
        db.scalars(
            select(models.Item).options(*_ITEM_LOADS).where(models.Item.id.in_(payload.ids))
        ).all()
    )
    if not items:
        return schemas.BulkResultOut(action=payload.action, affected=0)

    if payload.action == "delete":
        for item in items:
            media.delete_files(
                *[p.file_path for p in item.photos],
                *[p.thumb_path for p in item.photos],
            )
            db.delete(item)

    elif payload.action == "set_status":
        if payload.status is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "`status` requis pour set_status")
        for item in items:
            item.status = payload.status

    elif payload.action == "add_tags":
        extra = crud.resolve_tags(db, payload.tags)
        for item in items:
            existing = {t.name for t in item.tags}
            item.tags.extend(t for t in extra if t.name not in existing)

    elif payload.action == "remove_tags":
        wanted = {(t or "").strip().lower() for t in payload.tags}
        for item in items:
            item.tags = [t for t in item.tags if t.name.lower() not in wanted]

    db.commit()
    return schemas.BulkResultOut(action=payload.action, affected=len(items))


# --------------------------------------------------------------------------- #
# Export / import / sauvegarde (lecture : tout compte authentifié)
# --------------------------------------------------------------------------- #
@router.get("/export", response_model=schemas.ExportOut)
def export_json(db: Session = Depends(get_db)):
    items = _all_items(db)
    return schemas.ExportOut(
        exported_at=datetime.now(UTC),
        total=len(items),
        items=[schemas.ItemOut.model_validate(i) for i in items],
    )


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for item in _all_items(db):
        writer.writerow(_csv_row(item))

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="aviadb-{stamp}.csv"'},
    )


@router.get("/backup")
def download_backup(db: Session = Depends(get_db)):
    """Archive ZIP : aviadb.json (objets, réglages, comptes) + toutes les images."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = backup.build_backup_file(db)
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"aviadb-backup-{stamp}.zip",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@router.get("/report.pdf")
def inventory_report(db: Session = Depends(get_db)):
    """Rapport d'inventaire (PDF) : totaux et liste détaillée des objets."""
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        content=report.build_inventory_pdf(db),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="aviadb-inventaire-{stamp}.pdf"'
        },
    )


def _entry_to_payload(entry: dict) -> schemas.ItemCreate:
    """Construit un ItemCreate à partir d'une entrée JSON (export ou sauvegarde)."""
    tags = []
    for tag in entry.get("tags") or []:
        name = tag.get("name") if isinstance(tag, dict) else tag
        if name:
            tags.append(str(name))
    return schemas.ItemCreate(
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
        tags=tags,
        diecast=backup._details(entry.get("diecast"), schemas.DiecastDetailsIn),
        patch=backup._details(entry.get("patch"), schemas.PatchDetailsIn),
    )


def _import_entries(db: Session, entries: list) -> tuple[int, list[str]]:
    created = 0
    errors: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not entry.get("name"):
            errors.append(f"entrée {index} ignorée : nom manquant")
            continue
        try:
            with db.begin_nested():
                db.add(crud.create_item(db, _entry_to_payload(entry)))
                db.flush()
            created += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"entrée {index} ({entry.get('name')!r}) : {exc}")
    db.commit()
    return created, errors


@router.post(
    "/import",
    response_model=schemas.ImportResultOut,
    dependencies=[Depends(auth.require_admin)],
)
def import_json(payload: list[schemas.ItemCreate], db: Session = Depends(get_db)):
    created = 0
    errors: list[str] = []
    for index, entry in enumerate(payload):
        try:
            with db.begin_nested():
                db.add(crud.create_item(db, entry))
                db.flush()
            created += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"entrée {index} ({entry.name!r}) : {exc}")
    db.commit()
    return schemas.ImportResultOut(created=created, errors=errors)


@router.post(
    "/import.csv",
    response_model=schemas.ImportResultOut,
    dependencies=[Depends(auth.require_admin)],
)
def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = file.file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fichier vide")

    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "name" not in reader.fieldnames:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Colonne « name » manquante. Utilisez un CSV issu de l'export.",
        )

    entries = []
    for row in reader:
        entry = {key: _clean(value) for key, value in row.items() if key}
        entry["item_type"] = entry.get("item_type") or models.ItemType.OTHER.value
        entry["status"] = entry.get("status") or models.ItemStatus.STORED_BOX.value
        entry["tags"] = [t.strip() for t in (entry.get("tags") or "").split(",") if t.strip()]
        for numeric in ("purchase_price", "estimated_value"):
            if entry.get(numeric) is not None:
                try:
                    entry[numeric] = float(entry[numeric])
                except ValueError:
                    entry[numeric] = None

        # Le CSV est à plat : on regroupe les colonnes de détails en objets imbriqués.
        diecast = {
            key: entry.get(key) for key in DETAIL_COLUMNS["diecast"] if entry.get(key) is not None
        }
        patch = {
            key: entry.get(key) for key in DETAIL_COLUMNS["patch"] if entry.get(key) is not None
        }
        entry["diecast"] = diecast or None
        entry["patch"] = patch or None

        entries.append(entry)

    created, errors = _import_entries(db, entries)
    return schemas.ImportResultOut(created=created, errors=errors)


@router.post(
    "/restore",
    response_model=schemas.RestoreResultOut,
    dependencies=[Depends(auth.require_admin)],
)
def restore(
    file: UploadFile = File(...),
    mode: str = Form("merge"),
    db: Session = Depends(get_db),
):
    if mode not in {"merge", "replace"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "`mode` doit être « merge » ou « replace »"
        )
    result = backup.restore_backup(db, file, replace=(mode == "replace"))
    return schemas.RestoreResultOut(**result)


# --------------------------------------------------------------------------- #
# Devise de référence et taux de change (ADMIN)
# --------------------------------------------------------------------------- #
def settings_payload(db: Session) -> schemas.SettingsOut:
    """Devise de référence, devises disponibles et taux courants."""
    return schemas.SettingsOut(
        default_currency=currency.get_base_currency(db),
        currencies=[
            schemas.CurrencyOption(code=code, label=label)
            for code, label in currency.CURRENCIES.items()
        ],
        rates=currency.get_rates(db),
        **currency.get_rates_meta(db),
    )


@router.put(
    "/settings",
    response_model=schemas.SettingsOut,
    dependencies=[Depends(auth.require_admin)],
)
def update_settings(payload: schemas.SettingsUpdate, db: Session = Depends(get_db)):
    try:
        currency.set_base_currency(db, payload.default_currency)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    return settings_payload(db)


@router.put(
    "/rates",
    response_model=schemas.SettingsOut,
    dependencies=[Depends(auth.require_admin)],
)
def update_rates(payload: schemas.RatesUpdate, db: Session = Depends(get_db)):
    """Corrige les taux à la main (convention BCE : 1 EUR = X)."""
    unknown = [code for code in payload.rates if code.upper() not in currency.CURRENCIES]
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Devise(s) inconnue(s) : {', '.join(sorted(unknown))}",
        )
    currency.set_rates(db, payload.rates, "saisie manuelle")
    db.commit()
    return settings_payload(db)


@router.post(
    "/rates/refresh",
    response_model=schemas.SettingsOut,
    dependencies=[Depends(auth.require_admin)],
)
def refresh_rates(db: Session = Depends(get_db)):
    """Récupère les taux du jour auprès de la BCE (frankfurter.app)."""
    try:
        rates, source, _ = currency.fetch_current_rates()
    except currency.RateFetchError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Taux indisponibles ({exc}). Vérifiez l'accès réseau, "
            "ou saisissez les taux à la main.",
        ) from exc
    currency.set_rates(db, rates, source)
    db.commit()
    return settings_payload(db)


# --------------------------------------------------------------------------- #
# Gestion des comptes (ADMIN)
# --------------------------------------------------------------------------- #
def _get_user_or_404(db: Session, user_id: int) -> models.User:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Utilisateur {user_id} introuvable")
    return user


def _admin_count(db: Session, *, exclude_id: int | None = None) -> int:
    statement = select(func.count()).select_from(models.User).where(
        models.User.role == models.UserRole.ADMIN,
        models.User.is_active.is_(True),
    )
    if exclude_id is not None:
        statement = statement.where(models.User.id != exclude_id)
    return db.scalar(statement) or 0


@router.post(
    "/fetch-price",
    response_model=schemas.FetchPriceOut,
    dependencies=[Depends(auth.require_admin)],
)
def fetch_price(payload: schemas.FetchPriceIn):
    """Lit un prix sur une page de boutique — proposé, jamais enregistré seul."""
    try:
        return schemas.FetchPriceOut(**pricing.fetch_price(payload.url))
    except pricing.PriceFetchError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get(
    "/users",
    response_model=list[schemas.UserOut],
    dependencies=[Depends(auth.require_admin)],
)
def list_users(db: Session = Depends(get_db)):
    return list(db.scalars(select(models.User).order_by(models.User.username)).all())


@router.post(
    "/users",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_admin)],
)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    exists = db.scalars(
        select(models.User).where(models.User.username == payload.username)
    ).first()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet identifiant existe déjà")

    user = models.User(
        username=payload.username,
        password_hash=auth.hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    auth.refresh_protection(db)
    return user


@router.patch(
    "/users/{user_id}",
    response_model=schemas.UserOut,
    dependencies=[Depends(auth.require_admin)],
)
def update_user(user_id: int, payload: schemas.UserUpdate, db: Session = Depends(get_db)):
    user = _get_user_or_404(db, user_id)
    fields = payload.model_dump(exclude_unset=True)

    demoting = (fields.get("role") not in (None, models.UserRole.ADMIN)) or (
        fields.get("is_active") is False
    )
    if (
        demoting
        and user.role == models.UserRole.ADMIN
        and _admin_count(db, exclude_id=user.id) == 0
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Impossible de retirer le dernier administrateur actif",
        )

    if "password" in fields and fields["password"]:
        user.password_hash = auth.hash_password(fields["password"])
    if fields.get("role") is not None:
        user.role = fields["role"]
    if fields.get("is_active") is not None:
        user.is_active = fields["is_active"]

    db.commit()
    db.refresh(user)
    return user


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(auth.require_admin)],
)
def delete_user(
    user_id: int,
    claims: dict = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, user_id)
    if claims.get("sub") == user.username:
        raise HTTPException(status.HTTP_409_CONFLICT, "Impossible de supprimer votre propre compte")
    if user.role == models.UserRole.ADMIN and _admin_count(db, exclude_id=user.id) == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Impossible de supprimer le dernier administrateur actif",
        )
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Journal d'activité — ADMIN
# --------------------------------------------------------------------------- #
@router.get(
    "/activity",
    response_model=list[schemas.ActivityOut],
    dependencies=[Depends(auth.require_admin)],
)
def list_activity(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    """Dernières modifications (audit) : qui a modifié quoi, quand."""
    return list(
        db.scalars(
            select(models.ActivityLog).order_by(models.ActivityLog.at.desc()).limit(limit)
        ).all()
    )


# --------------------------------------------------------------------------- #
# Gestion des tags (ADMIN)
# --------------------------------------------------------------------------- #
@router.patch(
    "/tags/{tag_id}",
    response_model=schemas.TagOut,
    dependencies=[Depends(auth.require_admin)],
)
def rename_tag(tag_id: int, payload: schemas.TagUpdate, db: Session = Depends(get_db)):
    tag = db.get(models.Tag, tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tag {tag_id} introuvable")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nom de tag vide")

    clash = db.scalars(
        select(models.Tag).where(models.Tag.name == name, models.Tag.id != tag_id)
    ).first()
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Le tag « {name} » existe déjà")

    tag.name = name
    db.commit()
    db.refresh(tag)
    return tag


@router.delete(
    "/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(auth.require_admin)],
)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.get(models.Tag, tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Tag {tag_id} introuvable")

    db.execute(sa_delete(models.item_tags).where(models.item_tags.c.tag_id == tag_id))
    db.delete(tag)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Classes (arborescence) — ADMIN
# --------------------------------------------------------------------------- #
def _get_class_or_404(db: Session, class_id: int) -> models.ItemClass:
    node = db.get(models.ItemClass, class_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Classe {class_id} introuvable")
    return node


def _ensure_unique_name(
    db: Session, name: str, parent_id: int | None, *, exclude_id: int | None = None
) -> None:
    """Une même fratrie ne peut pas contenir deux fois le même nom.

    Vérifié côté application : PostgreSQL considère deux `NULL` comme distincts,
    une contrainte d'unicité laisserait donc passer deux classes racines homonymes.
    """
    statement = select(models.ItemClass).where(
        models.ItemClass.name == name,
        (
            models.ItemClass.parent_id.is_(None)
            if parent_id is None
            else models.ItemClass.parent_id == parent_id
        ),
    )
    if exclude_id is not None:
        statement = statement.where(models.ItemClass.id != exclude_id)
    if db.scalars(statement).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"« {name} » existe déjà à ce niveau")


@router.post(
    "/classes",
    response_model=schemas.ClassOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_admin)],
)
def create_class(payload: schemas.ClassIn, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if payload.parent_id is not None:
        _get_class_or_404(db, payload.parent_id)
    _ensure_unique_name(db, name, payload.parent_id)

    position = db.scalar(
        select(func.coalesce(func.max(models.ItemClass.position), -1) + 1).where(
            models.ItemClass.parent_id.is_(None)
            if payload.parent_id is None
            else models.ItemClass.parent_id == payload.parent_id
        )
    )
    node = models.ItemClass(name=name, parent_id=payload.parent_id, position=position or 0)
    db.add(node)
    db.commit()
    db.refresh(node)
    return schemas.ClassOut(
        id=node.id, name=node.name, parent_id=node.parent_id, position=node.position, item_count=0
    )


def _descendants_of(db: Session, root_id: int) -> set[int]:
    return crud.class_descendant_ids(crud.all_classes(db), root_id)


@router.patch(
    "/classes/{class_id}",
    response_model=schemas.ClassOut,
    dependencies=[Depends(auth.require_admin)],
)
def update_class(class_id: int, payload: schemas.ClassUpdate, db: Session = Depends(get_db)):
    node = _get_class_or_404(db, class_id)
    fields = payload.model_dump(exclude_unset=True)

    if "parent_id" in fields and fields["parent_id"] is not None:
        parent_id = fields["parent_id"]
        if parent_id == class_id or parent_id in _descendants_of(db, class_id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Une classe ne peut pas être placée sous elle-même",
            )
        _get_class_or_404(db, parent_id)

    name = (fields.get("name") or node.name).strip()
    parent_id = fields["parent_id"] if "parent_id" in fields else node.parent_id
    _ensure_unique_name(db, name, parent_id, exclude_id=node.id)

    node.name = name
    node.parent_id = parent_id
    db.commit()
    db.refresh(node)

    used = db.scalar(
        select(func.count()).select_from(models.Item).where(models.Item.class_id == node.id)
    ) or 0
    return schemas.ClassOut(
        id=node.id,
        name=node.name,
        parent_id=node.parent_id,
        position=node.position,
        item_count=used,
    )


@router.delete(
    "/classes/{class_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(auth.require_admin)],
)
def delete_class(
    class_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """Supprime la classe **et sa descendance**.

    Sans `force`, refuse si des objets y sont rattachés : on ne désaffecte pas
    des pièces à l'insu de l'utilisateur.
    """
    node = _get_class_or_404(db, class_id)
    ids = _descendants_of(db, class_id)
    used = db.scalar(
        select(func.count()).select_from(models.Item).where(models.Item.class_id.in_(ids))
    ) or 0

    if used and not force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{used} objet(s) utilisent cette classe ou l'une de ses sous-classes. "
            "Confirmez la suppression pour les laisser sans classe.",
        )

    # `Item.class_id` passe à NULL (ON DELETE SET NULL), le reste part en cascade.
    db.delete(node)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Clés d'API — ADMIN
# --------------------------------------------------------------------------- #
@router.get(
    "/api-keys",
    response_model=list[schemas.ApiKeyOut],
    dependencies=[Depends(auth.require_admin)],
)
def list_api_keys(db: Session = Depends(get_db)):
    return list(db.scalars(select(models.ApiKey).order_by(models.ApiKey.created_at.desc())).all())


@router.post(
    "/api-keys",
    response_model=schemas.ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_admin)],
)
def create_api_key(payload: schemas.ApiKeyIn, db: Session = Depends(get_db)):
    """Génère une clé. La valeur en clair n'est renvoyée que par cette réponse."""
    token = api_keys.generate_key()
    record = models.ApiKey(
        label=payload.label.strip(),
        key_hash=api_keys.hash_key(token),
        prefix=api_keys.display_prefix(token),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return schemas.ApiKeyCreated(
        key=token, api_key=schemas.ApiKeyOut.model_validate(record)
    )


@router.patch(
    "/api-keys/{key_id}",
    response_model=schemas.ApiKeyOut,
    dependencies=[Depends(auth.require_admin)],
)
def update_api_key(key_id: int, payload: schemas.ApiKeyUpdate, db: Session = Depends(get_db)):
    record = db.get(models.ApiKey, key_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Clé {key_id} introuvable")

    fields = payload.model_dump(exclude_unset=True)
    if fields.get("label"):
        record.label = fields["label"].strip()
    if fields.get("is_active") is not None:
        record.is_active = fields["is_active"]
    db.commit()
    db.refresh(record)
    return record


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(auth.require_admin)],
)
def delete_api_key(key_id: int, db: Session = Depends(get_db)):
    record = db.get(models.ApiKey, key_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Clé {key_id} introuvable")
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
