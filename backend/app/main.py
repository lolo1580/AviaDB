"""API FastAPI — AviaDB.

Étape 1 : noyau de données & API CRUD.
Endpoints REST pour lister, créer, modifier et supprimer un objet avec ses
spécificités (détails diecast / patch, tags). Les photos sont modélisées mais
leur upload arrivera à l'étape 2.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import date
from typing import Literal

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from . import admin, alembic_runner, api_keys, auth, crud, currency, media, models, report, schemas
from .database import SessionLocal, get_db
from .stats import compute_stats

logger = logging.getLogger("aviadb.activity")

# Raccourci : toutes les routes d'écriture exigent un admin authentifié.
# Les routes GET (consultation) restent publiques.
_admin_only = [Depends(auth.require_admin)]

# Chargements anticipés systématiques pour sérialiser un item complet.
_ITEM_LOADS = (
    selectinload(models.Item.diecast),
    selectinload(models.Item.patch),
    selectinload(models.Item.photos),
    selectinload(models.Item.tags),
    selectinload(models.Item.links),
    selectinload(models.Item.price_points),
)


def _cleanup_interval() -> int:
    return max(300, int(os.getenv("MEDIA_CLEANUP_INTERVAL", str(24 * 3600))))


def _cleanup_min_age() -> int:
    return max(0, int(os.getenv("MEDIA_CLEANUP_MIN_AGE", "3600")))


def _run_media_cleanup() -> None:
    with SessionLocal() as db:
        removed = media.cleanup_orphans(db, min_age_seconds=_cleanup_min_age())
    if removed:
        logger.info("Nettoyage des médias : %s fichier(s) orphelin(s) supprimé(s)", removed)


async def _media_maintenance_loop() -> None:
    """Nettoie périodiquement les images orphelines (fichier sans ligne en base)."""
    while True:
        try:
            await asyncio.to_thread(_run_media_cleanup)
        except Exception:  # pragma: no cover - la boucle doit survivre
            logger.exception("Échec du nettoyage des médias")
        await asyncio.sleep(_cleanup_interval())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schéma : migrations Alembic. Sous pytest, la suite gère elle-même son
    # schéma (drop_all/create_all) : on saute les migrations.
    if os.getenv("AVIADB_SKIP_MIGRATIONS") != "1":
        alembic_runner.run_migrations()

    # Crée le compte admin initial si ADMIN_PASSWORD est défini, puis met à jour
    # l'état de protection (authentification requise ou non).
    with SessionLocal() as db:
        auth.bootstrap_admin(db)
        currency.backfill_items(db)
        # Borne le journal d'activité (voir `prune_activity`).
        prune_activity(db, _activity_keep())
        # Empreintes des images existantes (dédoublonnage).
        media.backfill_hashes(db)
        # Les vignettes ne sont plus stockées : on retire les anciennes.
        media.drop_legacy_thumbnails(db)

    maintenance = asyncio.create_task(_media_maintenance_loop())
    try:
        yield
    finally:
        maintenance.cancel()
        with suppress(asyncio.CancelledError):
            await maintenance


app = FastAPI(title="AviaDB API", version="0.2.0", lifespan=lifespan)

# --------------------------------------------------------------------------- #
# Accès protégé : tout l'API et les images exigent une session admin.
# Seules ces routes restent publiques (nécessaires avant la connexion) :
# --------------------------------------------------------------------------- #
_PUBLIC_PATHS = {
    "/api/health",
    "/api/admin/login",
    "/api/admin/session",
}
# Les routes publiques s'authentifient par clé d'API, pas par session.
_PUBLIC_PREFIXES = ("/api/public/",)
_PROTECTED_PREFIXES = ("/api/", "/uploads/")
_PROTECTED_EXACT = {"/docs", "/redoc", "/openapi.json"}


async def _enforce_auth(request: Request, call_next):
    """Refuse (401) tout accès non authentifié, sauf chemins publics.

    Sans compte configuré (et sans `ADMIN_PASSWORD`), la protection est désactivée.
    """
    if not auth.protection_enabled():
        return await call_next(request)

    path = request.url.path
    is_protected = path in _PROTECTED_EXACT or path.startswith(_PROTECTED_PREFIXES)
    is_public = (
        path in _PUBLIC_PATHS
        or path.startswith(_PUBLIC_PREFIXES)
        or request.method == "OPTIONS"
    )

    if is_protected and not is_public:
        token = auth.token_from(
            request.headers.get("authorization"),
            request.cookies.get(auth.COOKIE_NAME),
        )
        if not auth.verify_token(token):
            return JSONResponse(
                {"detail": "Authentification requise"},
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)


app.middleware("http")(_enforce_auth)

# Le frontend est servi séparément en dev (Vite) : on autorise le cross-origin.
# (enregistré en dernier => exécuté en premier, donc le CORS enveloppe le 401)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# Journal d'activité : les requêtes de modification sont tracées (audit).
# --------------------------------------------------------------------------- #
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_UNLOGGED_PATHS = {"/api/admin/login"}
# Fréquence d'élagage : toutes les N écritures journalisées.
_ACTIVITY_PRUNE_EVERY = 500
_activity_writes = 0


def _activity_keep() -> int:
    """Nombre d'entrées de journal conservées (minimum 100)."""
    return max(100, int(os.getenv("ACTIVITY_KEEP", "5000")))


def prune_activity(db: Session, keep: int) -> int:
    """Ne conserve que les `keep` entrées les plus récentes du journal.

    Renvoie le nombre d'entrées supprimées. Le journal est un fichier d'audit, pas
    une source de vérité : on le borne pour qu'il ne croisse pas indéfiniment.
    """
    cutoff = db.scalar(
        select(models.ActivityLog.id)
        .order_by(models.ActivityLog.id.desc())
        .offset(keep)
        .limit(1)
    )
    if cutoff is None:
        return 0
    # `cutoff` est l'entrée à la frontière : on la supprime aussi (`<=`) pour ne
    # conserver exactement que `keep` lignes.
    result = db.execute(delete(models.ActivityLog).where(models.ActivityLog.id <= cutoff))
    db.commit()
    return int(result.rowcount or 0)


def _maybe_prune_activity(db: Session) -> None:
    global _activity_writes
    _activity_writes += 1
    if _activity_writes % _ACTIVITY_PRUNE_EVERY == 0:
        prune_activity(db, _activity_keep())


async def _record_activity(request: Request, call_next):
    """Écrit une entrée d'audit après chaque requête d'écriture. Ne bloque jamais."""
    response = await call_next(request)
    path = request.url.path
    if (
        request.method not in _MUTATING_METHODS
        or not path.startswith("/api/")
        or path in _UNLOGGED_PATHS
        or response.status_code >= 500
    ):
        return response

    try:
        claims = auth.verify_token(
            auth.token_from(
                request.headers.get("authorization"),
                request.cookies.get(auth.COOKIE_NAME),
            )
        )
        with SessionLocal() as db:
            db.add(
                models.ActivityLog(
                    username=claims.get("sub") if claims else None,
                    method=request.method,
                    path=path[:255],
                    status_code=response.status_code,
                )
            )
            db.commit()
            _maybe_prune_activity(db)
    except Exception:  # pragma: no cover - l'audit ne doit jamais casser une requête
        logger.exception("Échec d'écriture du journal d'activité")
    return response


app.middleware("http")(_record_activity)

# Images : route dédiée (les variantes sont produites à la volée via `?w=`).
media.ensure_upload_dir()


@app.get("/uploads/{path:path}", include_in_schema=False)
def serve_upload(
    path: str,
    w: int | None = Query(None, ge=media.MIN_VARIANT, le=media.MAX_VARIANT),
):
    """Sert une image stockée ; `?w=` renvoie une variante (mise en cache)."""
    target = media.resolve_upload(path)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier introuvable")

    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    if w is not None:
        try:
            payload = media.render_variant(path, w)
        except FileNotFoundError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier introuvable") from None
        return Response(content=payload, media_type="image/webp", headers=headers)
    return FileResponse(target, headers=headers)

# Authentification admin (login/logout/session), routes d'administration et API publique.
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(api_keys.router)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _load_item(db: Session, item_id: int) -> models.Item:
    item = db.scalars(
        select(models.Item).options(*_ITEM_LOADS).where(models.Item.id == item_id)
    ).first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Item {item_id} introuvable")
    return item


def _upsert_details(current, model_cls, data: dict):
    """Crée la ligne de détails si absente, sinon met à jour les champs fournis."""
    if current is None:
        return model_cls(**data)
    for key, value in data.items():
        setattr(current, key, value)
    return current


def _get_photo_or_404(db: Session, photo_id: int) -> models.ItemPhoto:
    photo = db.get(models.ItemPhoto, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Photo {photo_id} introuvable")
    return photo


def _set_primary(photo: models.ItemPhoto, siblings: list[models.ItemPhoto]) -> None:
    """Désigne `photo` comme principale et démarque ses sœurs."""
    for sibling in siblings:
        sibling.is_primary = sibling.id == photo.id


# --------------------------------------------------------------------------- #
# Santé & méta
# --------------------------------------------------------------------------- #
@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/api/meta/enums", response_model=schemas.EnumOptions, tags=["meta"])
def enum_options():
    """Valeurs d'énumération, pour alimenter les selects du frontend."""
    return schemas.EnumOptions(
        item_types=[e.value for e in models.ItemType],
        statuses=[e.value for e in models.ItemStatus],
        materials=[e.value for e in models.PatchMaterial],
        attachment_types=[e.value for e in models.AttachmentType],
        shapes=[e.value for e in models.PatchShape],
    )


@app.get("/api/meta/settings", response_model=schemas.SettingsOut, tags=["meta"])
def settings(db: Session = Depends(get_db)):
    """Devise de référence, devises disponibles et taux de change courants."""
    return admin.settings_payload(db)


# --------------------------------------------------------------------------- #
# Filtres & recherche (Étape 3)
# --------------------------------------------------------------------------- #
def _build_filters(
    *,
    q: str | None,
    item_types: list[models.ItemType] | None,
    statuses: list[models.ItemStatus] | None,
    countries: list[str] | None,
    aircraft_models: list[str] | None,
    storage_locations: list[str] | None,
    scales: list[str] | None,
    manufacturers: list[str] | None,
    tags: list[str] | None,
    value_min: float | None,
    value_max: float | None,
    has_loan: bool | None,
    class_ids: list[int] | None = None,
):
    """Traduit les paramètres de requête en conditions SQL + jointures nécessaires."""
    conditions = []
    need_diecast = need_patch = False

    if q and q.strip():
        like = f"%{q.strip()}%"
        need_diecast = need_patch = True
        conditions.append(
            or_(
                models.Item.name.ilike(like),
                models.Item.country.ilike(like),
                models.Item.aircraft_model.ilike(like),
                models.Item.storage_location.ilike(like),
                models.Item.notes.ilike(like),
                models.DiecastDetails.scale.ilike(like),
                models.DiecastDetails.manufacturer.ilike(like),
                models.DiecastDetails.part_number.ilike(like),
                models.DiecastDetails.registration_number.ilike(like),
                models.PatchDetails.unit_squadron.ilike(like),
                models.PatchDetails.base.ilike(like),
                models.PatchDetails.event_or_mission.ilike(like),
            )
        )

    if item_types:
        conditions.append(models.Item.item_type.in_(item_types))
    if statuses:
        conditions.append(models.Item.status.in_(statuses))
    if countries:
        conditions.append(models.Item.country.in_(countries))
    if aircraft_models:
        conditions.append(models.Item.aircraft_model.in_(aircraft_models))
    if storage_locations:
        conditions.append(models.Item.storage_location.in_(storage_locations))

    if scales:
        need_diecast = True
        conditions.append(models.DiecastDetails.scale.in_(scales))
    if manufacturers:
        need_diecast = True
        conditions.append(models.DiecastDetails.manufacturer.in_(manufacturers))

    if tags:
        conditions.append(models.Tag.name.in_(tags))

    if value_min is not None:
        conditions.append(models.Item.estimated_value >= value_min)
    if value_max is not None:
        conditions.append(models.Item.estimated_value <= value_max)

    if has_loan is True:
        conditions.append(models.Item.loaned_to.isnot(None))
    elif has_loan is False:
        conditions.append(models.Item.loaned_to.is_(None))

    if class_ids:
        conditions.append(models.Item.class_id.in_(class_ids))

    return conditions, need_diecast, need_patch, bool(tags)


def _apply_filters(stmt, conditions, need_diecast, need_patch, need_tags):
    if need_tags:
        stmt = stmt.join(models.Item.tags)
    if need_diecast:
        stmt = stmt.outerjoin(models.Item.diecast)
    if need_patch:
        stmt = stmt.outerjoin(models.Item.patch)
    if conditions:
        stmt = stmt.where(*conditions)
    return stmt


_SORT_COLUMNS = {
    "name": models.Item.name,
    "country": models.Item.country,
    "aircraft_model": models.Item.aircraft_model,
    "status": models.Item.status,
    "purchase_date": models.Item.purchase_date,
    "estimated_value": models.Item.estimated_value,
    "created_at": models.Item.created_at,
    "updated_at": models.Item.updated_at,
}


# --------------------------------------------------------------------------- #
# CRUD items
# --------------------------------------------------------------------------- #
@app.get("/api/items", response_model=schemas.ItemListOut, tags=["items"])
def list_items(
    q: str | None = Query(
        None, description="Recherche texte (nom, modèle, immat., unité, notes...)"
    ),
    item_type: list[models.ItemType] | None = Query(None),
    status: list[models.ItemStatus] | None = Query(None),
    country: list[str] | None = Query(None),
    aircraft_model: list[str] | None = Query(None),
    storage_location: list[str] | None = Query(None),
    scale: list[str] | None = Query(None),
    manufacturer: list[str] | None = Query(None),
    tag: list[str] | None = Query(None),
    value_min: float | None = Query(None, ge=0),
    value_max: float | None = Query(None, ge=0),
    has_loan: bool | None = Query(None, description="true = prêtés, false = sur place"),
    class_id: int | None = Query(None, description="Classe et ses sous-classes"),
    sort: Literal[
        "name",
        "country",
        "aircraft_model",
        "status",
        "purchase_date",
        "estimated_value",
        "created_at",
        "updated_at",
    ] = "name",
    order: Literal["asc", "desc"] = "asc",
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    # Une classe englobe toujours sa descendance.
    class_ids = None
    if class_id is not None:
        class_ids = sorted(crud.class_descendant_ids(crud.all_classes(db), class_id))

    conditions, need_diecast, need_patch, need_tags = _build_filters(
        q=q,
        item_types=item_type,
        statuses=status,
        countries=country,
        aircraft_models=aircraft_model,
        storage_locations=storage_location,
        scales=scale,
        manufacturers=manufacturer,
        tags=tag,
        value_min=value_min,
        value_max=value_max,
        has_loan=has_loan,
        class_ids=class_ids,
    )

    total = db.scalar(
        _apply_filters(
            select(func.count(func.distinct(models.Item.id))),
            conditions,
            need_diecast,
            need_patch,
            need_tags,
        )
    ) or 0

    stmt = _apply_filters(
        select(models.Item), conditions, need_diecast, need_patch, need_tags
    )
    if need_tags:
        # La jointure N-to-N peut dupliquer les lignes.
        stmt = stmt.distinct()

    column = _SORT_COLUMNS[sort]
    stmt = (
        stmt.options(*_ITEM_LOADS)
        .order_by(column.desc() if order == "desc" else column.asc(), models.Item.id)
        .offset(skip)
        .limit(limit)
    )

    return schemas.ItemListOut(total=total, items=list(db.scalars(stmt).all()))


@app.post(
    "/api/items",
    response_model=schemas.ItemOut,
    status_code=status.HTTP_201_CREATED,
    tags=["items"],
    dependencies=_admin_only,
)
def create_item(payload: schemas.ItemCreate, db: Session = Depends(get_db)):
    item = crud.create_item(db, payload)
    db.commit()
    return _load_item(db, item.id)


@app.get("/api/items/{item_id}", response_model=schemas.ItemOut, tags=["items"])
def get_item(item_id: int, db: Session = Depends(get_db)):
    return _load_item(db, item_id)


@app.get("/api/items/{item_id}/report.pdf", tags=["items"])
def item_report(item_id: int, db: Session = Depends(get_db)):
    """Fiche détaillée d'un objet (PDF) : photo, caractéristiques et historique."""
    item = _load_item(db, item_id)
    return Response(
        content=report.build_item_pdf(db, item),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="aviadb-fiche-{item.id}.pdf"'
        },
    )


@app.patch(
    "/api/items/{item_id}",
    response_model=schemas.ItemOut,
    tags=["items"],
    dependencies=_admin_only,
)
@app.put(
    "/api/items/{item_id}",
    response_model=schemas.ItemOut,
    include_in_schema=False,
    dependencies=_admin_only,
)
def update_item(item_id: int, payload: schemas.ItemUpdate, db: Session = Depends(get_db)):
    item = _load_item(db, item_id)
    fields = payload.model_dump(exclude_unset=True)

    if "tags" in fields:
        item.tags = crud.resolve_tags(db, fields.pop("tags") or [])

    if "diecast" in fields:
        data = fields.pop("diecast")
        item.diecast = (
            None
            if data is None
            else _upsert_details(item.diecast, models.DiecastDetails, data)
        )

    if "patch" in fields:
        data = fields.pop("patch")
        item.patch = (
            None if data is None else _upsert_details(item.patch, models.PatchDetails, data)
        )

    for key, value in fields.items():
        setattr(item, key, value)

    # Recalcule la devise et l'équivalent EUR du prix d'achat si besoin.
    if {"purchase_price", "purchase_date", "currency"} & set(fields) or (
        item.purchase_price is not None and item.purchase_eur_value is None
    ):
        crud.apply_amounts(db, item)

    db.commit()
    return _load_item(db, item.id)


@app.delete(
    "/api/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["items"],
    dependencies=_admin_only,
)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = _load_item(db, item_id)
    for photo in item.photos:
        media.delete_photo_files(photo)
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Photos (Étape 2)
# --------------------------------------------------------------------------- #
@app.get(
    "/api/items/{item_id}/photos",
    response_model=list[schemas.PhotoOut],
    tags=["photos"],
)
def list_photos(item_id: int, db: Session = Depends(get_db)):
    return _load_item(db, item_id).photos


@app.post(
    "/api/items/{item_id}/photos",
    response_model=schemas.PhotoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["photos"],
    dependencies=_admin_only,
)
def upload_photo(
    item_id: int,
    response: Response,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    is_primary: bool = Form(False),
    force: bool = Form(False),
    db: Session = Depends(get_db),
):
    item = _load_item(db, item_id)
    file_path, thumb_path, content_hash, perceptual_hash = media.save_image(file, item.id)

    # Dédoublonnage global : image identique ou perceptuellement très proche.
    if not force:
        duplicate = media.find_duplicate(db, content_hash, perceptual_hash)
        if duplicate is not None:
            photo_id, owner_id, _distance = duplicate
            media.delete_files(file_path, thumb_path)

            if owner_id == item.id:
                existing = next((photo for photo in item.photos if photo.id == photo_id), None)
                if existing is None:
                    existing = db.get(models.ItemPhoto, photo_id)
                if existing is not None:
                    if is_primary and not existing.is_primary:
                        _set_primary(existing, item.photos)
                        db.commit()
                        db.refresh(existing)
                    response.status_code = status.HTTP_200_OK
                    return existing

            owner = db.get(models.Item, owner_id)
            owner_name = owner.name if owner is not None else f"objet {owner_id}"
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Cette image (ou une très proche) est déjà utilisée par "
                f"l’objet « {owner_name} » (#{owner_id}).",
            )

    # La première photo d'un item devient automatiquement principale.
    make_primary = is_primary or not item.photos
    next_position = max((p.position for p in item.photos), default=-1) + 1
    photo = models.ItemPhoto(
        item=item,
        file_path=file_path,
        thumb_path=thumb_path,
        content_hash=content_hash,
        perceptual_hash=perceptual_hash,
        position=next_position,
        caption=caption,
        is_primary=False,
    )
    db.add(photo)
    try:
        db.flush()
        if make_primary:
            _set_primary(photo, item.photos)
    except Exception:
        db.rollback()
        media.delete_files(file_path, thumb_path)
        raise
    db.commit()
    db.refresh(photo)
    return photo


@app.patch(
    "/api/photos/{photo_id}",
    response_model=schemas.PhotoOut,
    tags=["photos"],
    dependencies=_admin_only,
)
def update_photo(
    photo_id: int, payload: schemas.PhotoUpdate, db: Session = Depends(get_db)
):
    photo = _get_photo_or_404(db, photo_id)
    fields = payload.model_dump(exclude_unset=True)

    if "caption" in fields:
        photo.caption = fields.pop("caption")

    if "is_primary" in fields:
        value = fields.pop("is_primary")
        if value:
            _set_primary(photo, photo.item.photos)
        else:
            photo.is_primary = False

    db.commit()
    db.refresh(photo)
    return photo


@app.patch(
    "/api/photos/{photo_id}/transform",
    response_model=schemas.PhotoOut,
    tags=["photos"],
    dependencies=_admin_only,
)
def transform_photo(
    photo_id: int, payload: schemas.PhotoTransformIn, db: Session = Depends(get_db)
):
    """Applique une rotation (sens horaire) et/ou un recadrage manuel."""
    photo = _get_photo_or_404(db, photo_id)
    crop = None
    if payload.crop is not None:
        crop = (payload.crop.x, payload.crop.y, payload.crop.width, payload.crop.height)

    try:
        new_path, content_hash, perceptual_hash = media.transform_image(
            photo.file_path, rotate=payload.rotate, crop=crop
        )
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier image introuvable") from None

    # Nouveau nom : l'URL change, donc pas de vieille image en cache navigateur.
    old_files = [photo.file_path, photo.thumb_path, *media.cached_variants(photo.file_path)]
    photo.file_path = new_path
    photo.thumb_path = None
    photo.content_hash = content_hash
    photo.perceptual_hash = perceptual_hash
    db.commit()
    db.refresh(photo)
    media.delete_files(*old_files)
    return photo


@app.post(
    "/api/photos/{photo_id}/primary",
    response_model=schemas.PhotoOut,
    tags=["photos"],
    dependencies=_admin_only,
)
def set_primary_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = _get_photo_or_404(db, photo_id)
    _set_primary(photo, photo.item.photos)
    db.commit()
    db.refresh(photo)
    return photo


@app.delete(
    "/api/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["photos"],
    dependencies=_admin_only,
)
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = _get_photo_or_404(db, photo_id)
    siblings = [p for p in photo.item.photos if p.id != photo.id]
    was_primary = photo.is_primary

    media.delete_photo_files(photo)
    db.delete(photo)

    # Si la photo supprimée était la principale, on promeut la suivante.
    if was_primary and siblings:
        siblings[0].is_primary = True

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/items/{item_id}/photos/reorder",
    response_model=list[schemas.PhotoOut],
    tags=["photos"],
    dependencies=_admin_only,
)
def reorder_photos(item_id: int, payload: schemas.PhotoReorderIn, db: Session = Depends(get_db)):
    """Réordonne les photos selon la liste d'identifiants fournie."""
    item = _load_item(db, item_id)
    known = {photo.id: photo for photo in item.photos}

    ordered = [photo_id for photo_id in payload.ids if photo_id in known]
    # Les photos non mentionnées sont repoussées à la fin, dans leur ordre actuel.
    ordered += [photo.id for photo in item.photos if photo.id not in set(payload.ids)]

    for position, photo_id in enumerate(ordered):
        known[photo_id].position = position

    db.commit()
    # Après commit, la collection est rechargée dans l'ordre (position, id).
    return item.photos


# --------------------------------------------------------------------------- #
# Statistiques du dashboard (Étape 3)
# --------------------------------------------------------------------------- #
@app.get("/api/stats", response_model=schemas.StatsOut, tags=["stats"])
def stats(db: Session = Depends(get_db)):
    """Compteurs, valeurs et répartitions (devise de référence).

    Inclut les analytiques détaillés (valeur par classe, emplacement, année,
    plus-values) : la route exige une session, contrairement à l'API publique.
    """
    return compute_stats(db, include_details=True)


@app.get("/api/meta/facets", response_model=schemas.FacetsOut, tags=["meta"])
def facets(db: Session = Depends(get_db)):
    """Valeurs distinctes présentes en base, pour alimenter les filtres du frontend."""

    def distinct(col) -> list[str]:
        return list(
            db.scalars(
                select(col).where(col.isnot(None)).distinct().order_by(col)
            ).all()
        )

    return schemas.FacetsOut(
        countries=distinct(models.Item.country),
        aircraft_models=distinct(models.Item.aircraft_model),
        storage_locations=distinct(models.Item.storage_location),
        scales=distinct(models.DiecastDetails.scale),
        manufacturers=distinct(models.DiecastDetails.manufacturer),
        tags=list(db.scalars(select(models.Tag.name).order_by(models.Tag.name)).all()),
    )


# --------------------------------------------------------------------------- #
# Liens et suivi du prix (Étape 5)
# --------------------------------------------------------------------------- #
def _valid_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        url = f"https://{url}"
    if len(url) > 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Adresse trop longue")
    return url


@app.post(
    "/api/items/{item_id}/links",
    response_model=schemas.LinkOut,
    status_code=status.HTTP_201_CREATED,
    tags=["links"],
    dependencies=_admin_only,
)
def add_link(item_id: int, payload: schemas.LinkIn, db: Session = Depends(get_db)):
    item = _load_item(db, item_id)
    link = models.ItemLink(
        item=item, url=_valid_url(payload.url), label=(payload.label or "").strip() or None
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@app.patch(
    "/api/links/{link_id}",
    response_model=schemas.LinkOut,
    tags=["links"],
    dependencies=_admin_only,
)
def update_link(link_id: int, payload: schemas.LinkUpdate, db: Session = Depends(get_db)):
    link = db.get(models.ItemLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Lien {link_id} introuvable")

    fields = payload.model_dump(exclude_unset=True)
    if fields.get("url"):
        link.url = _valid_url(fields["url"])
    if "label" in fields:
        link.label = (fields["label"] or "").strip() or None
    db.commit()
    db.refresh(link)
    return link


@app.delete(
    "/api/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["links"],
    dependencies=_admin_only,
)
def delete_link(link_id: int, db: Session = Depends(get_db)):
    link = db.get(models.ItemLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Lien {link_id} introuvable")
    db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/items/{item_id}/prices",
    response_model=schemas.PricePointOut,
    status_code=status.HTTP_201_CREATED,
    tags=["prices"],
    dependencies=_admin_only,
)
def add_price_point(
    item_id: int, payload: schemas.PricePointIn, db: Session = Depends(get_db)
):
    """Enregistre un relevé de prix. L'équivalent EUR est figé au taux du jour."""
    item = _load_item(db, item_id)
    code = (payload.currency or item.currency or currency.get_base_currency(db)).upper()
    if code not in currency.CURRENCIES:
        code = currency.get_base_currency(db)
    rates = currency.get_rates(db)

    point = models.PricePoint(
        item=item,
        price=payload.price,
        currency=code,
        eur_value=round(currency.to_eur(payload.price, code, rates), 4),
        recorded_on=payload.recorded_on or date.today(),
        source_url=payload.source_url,
        note=payload.note,
    )
    db.add(point)
    db.commit()
    db.refresh(point)
    return point


@app.delete(
    "/api/prices/{price_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["prices"],
    dependencies=_admin_only,
)
def delete_price_point(price_id: int, db: Session = Depends(get_db)):
    point = db.get(models.PricePoint, price_id)
    if point is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Relevé {price_id} introuvable")
    db.delete(point)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Tags
# --------------------------------------------------------------------------- #
@app.get("/api/tags", response_model=list[schemas.TagOut], tags=["tags"])
def list_tags(db: Session = Depends(get_db)):
    return list(db.scalars(select(models.Tag).order_by(models.Tag.name)).all())


# --------------------------------------------------------------------------- #
# Classes (arborescence)
# --------------------------------------------------------------------------- #
@app.get("/api/classes", response_model=list[schemas.ClassOut], tags=["classes"])
def list_classes(db: Session = Depends(get_db)):
    """Toutes les classes, aplaties, avec le nombre d'objets de chacune.

    L'arborescence est reconstruite par le client à partir de `parent_id`.
    """
    counts = dict(
        db.execute(
            select(models.ItemClass.id, func.count(models.Item.id))
            .join(models.Item, models.Item.class_id == models.ItemClass.id, isouter=True)
            .group_by(models.ItemClass.id)
        ).all()
    )
    return [
        schemas.ClassOut(
            id=node.id,
            name=node.name,
            parent_id=node.parent_id,
            position=node.position,
            item_count=counts.get(node.id, 0),
        )
        for node in crud.all_classes(db)
    ]
