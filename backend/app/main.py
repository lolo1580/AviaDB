"""API FastAPI — AviaDB.

Étape 1 : noyau de données & API CRUD.
Endpoints REST pour lister, créer, modifier et supprimer un objet avec ses
spécificités (détails diecast / patch, tags). Les photos sont modélisées mais
leur upload arrivera à l'étape 2.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from . import admin, auth, crud, currency, media, migrations, models, schemas
from .database import Base, SessionLocal, engine, get_db, year_expression

# Raccourci : toutes les routes d'écriture exigent un admin authentifié.
# Les routes GET (consultation) restent publiques.
_admin_only = [Depends(auth.require_admin)]

# Chargements anticipés systématiques pour sérialiser un item complet.
_ITEM_LOADS = (
    selectinload(models.Item.diecast),
    selectinload(models.Item.patch),
    selectinload(models.Item.photos),
    selectinload(models.Item.tags),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crée le fichier SQLite et les tables au démarrage si nécessaire, puis
    # complète le schéma d'une base existante (colonnes ajoutées après coup).
    Base.metadata.create_all(bind=engine)
    migrations.ensure_schema()

    # Crée le compte admin initial si ADMIN_PASSWORD est défini, puis met à jour
    # l'état de protection (authentification requise ou non).
    with SessionLocal() as db:
        auth.bootstrap_admin(db)
        currency.backfill_items(db)
    yield


app = FastAPI(title="AviaDB API", version="0.1.0", lifespan=lifespan)

# --------------------------------------------------------------------------- #
# Accès protégé : tout l'API et les images exigent une session admin.
# Seules ces routes restent publiques (nécessaires avant la connexion) :
# --------------------------------------------------------------------------- #
_PUBLIC_PATHS = {
    "/api/health",
    "/api/admin/login",
    "/api/admin/session",
}
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

    if is_protected and path not in _PUBLIC_PATHS and request.method != "OPTIONS":
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

# Fichiers médias servis en statique : /uploads/items/<id>/<uuid>.webp
media.ensure_upload_dir()
app.mount("/uploads", StaticFiles(directory=media.UPLOAD_DIR), name="uploads")

# Authentification admin (login/logout/session) et routes d'administration.
app.include_router(auth.router)
app.include_router(admin.router)


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
    q: str | None = Query(None, description="Recherche texte (nom, modèle, immat., unité, notes...)"),
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
    media.delete_files(
        *[p.file_path for p in item.photos],
        *[p.thumb_path for p in item.photos],
    )
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
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    is_primary: bool = Form(False),
    db: Session = Depends(get_db),
):
    item = _load_item(db, item_id)
    file_path, thumb_path = media.save_image(file, item.id)

    # La première photo d'un item devient automatiquement principale.
    make_primary = is_primary or not item.photos
    next_position = max((p.position for p in item.photos), default=-1) + 1
    photo = models.ItemPhoto(
        item=item,
        file_path=file_path,
        thumb_path=thumb_path,
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

    media.delete_files(photo.file_path, photo.thumb_path)
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
def _buckets(rows) -> list[schemas.CountBucket]:
    return [
        schemas.CountBucket(key=str(key.value if hasattr(key, "value") else key), count=count)
        for key, count in rows
        if key is not None
    ]


def _currency_buckets(db: Session, base: str) -> list[schemas.CountBucket]:
    """Répartition par devise.

    Le regroupement se fait sur la colonne brute puis la devise par défaut est
    appliquée côté Python : `GROUP BY coalesce(colonne, :parametre)` est refusé
    par PostgreSQL (l'expression du SELECT et celle du GROUP BY portent des
    paramètres liés distincts).
    """
    counts: dict[str, int] = {}
    for code, count in db.execute(
        select(models.Item.currency, func.count()).group_by(models.Item.currency)
    ).all():
        key = (code or base).upper()
        counts[key] = counts.get(key, 0) + count
    return [
        schemas.CountBucket(key=key, count=count) for key, count in sorted(counts.items())
    ]


@app.get("/api/stats", response_model=schemas.StatsOut, tags=["stats"])
def stats(db: Session = Depends(get_db)):
    total_items = db.scalar(select(func.count()).select_from(models.Item)) or 0
    total_photos = db.scalar(select(func.count()).select_from(models.ItemPhoto)) or 0

    base = currency.get_base_currency(db)
    rates = currency.get_rates(db)

    # Valeur estimée : conversion depuis la devise de chaque objet, aux taux courants
    estimated_rows = db.execute(
        select(models.Item.currency, func.sum(models.Item.estimated_value))
        .where(models.Item.estimated_value.isnot(None))
        .group_by(models.Item.currency)
    ).all()
    total_estimated = sum(
        currency.to_base(float(total or 0.0), code, base, rates)
        for code, total in estimated_rows
    )

    # Prix d'achat : équivalent EUR figé à la date d'achat, puis converti en base
    purchase_rows = db.execute(
        select(
            models.Item.currency,
            models.Item.purchase_eur_value,
            models.Item.purchase_price,
        ).where(models.Item.purchase_price.isnot(None))
    ).all()
    total_eur = 0.0
    for code, eur_value, price in purchase_rows:
        if eur_value is None:
            # Objet antérieur à la gestion des devises : conversion au taux courant
            eur_value = currency.to_eur(float(price), code, rates)
        total_eur += float(eur_value)
    total_purchase = total_eur * rates.get(base, 1.0)

    with_value = db.scalar(
        select(func.count())
        .select_from(models.Item)
        .where(models.Item.estimated_value.isnot(None))
    ) or 0

    by_type = _buckets(
        db.execute(
            select(models.Item.item_type, func.count()).group_by(models.Item.item_type)
        ).all()
    )
    by_status = _buckets(
        db.execute(
            select(models.Item.status, func.count()).group_by(models.Item.status)
        ).all()
    )
    by_country = _buckets(
        db.execute(
            select(models.Item.country, func.count())
            .where(models.Item.country.isnot(None))
            .group_by(models.Item.country)
            .order_by(func.count().desc(), models.Item.country)
            .limit(20)
        ).all()
    )
    by_scale = _buckets(
        db.execute(
            select(models.DiecastDetails.scale, func.count())
            .where(models.DiecastDetails.scale.isnot(None))
            .group_by(models.DiecastDetails.scale)
            .order_by(func.count().desc(), models.DiecastDetails.scale)
        ).all()
    )
    by_manufacturer = _buckets(
        db.execute(
            select(models.DiecastDetails.manufacturer, func.count())
            .where(models.DiecastDetails.manufacturer.isnot(None))
            .group_by(models.DiecastDetails.manufacturer)
            .order_by(func.count().desc(), models.DiecastDetails.manufacturer)
            .limit(20)
        ).all()
    )
    by_material = _buckets(
        db.execute(
            select(models.PatchDetails.material, func.count())
            .where(models.PatchDetails.material.isnot(None))
            .group_by(models.PatchDetails.material)
            .order_by(func.count().desc())
        ).all()
    )

    # Années d'achat (to_char sur PostgreSQL, strftime sur SQLite)
    year_column = year_expression(models.Item.purchase_date)
    by_year = _buckets(
        db.execute(
            select(year_column, func.count())
            .where(models.Item.purchase_date.isnot(None))
            .group_by(year_column)
            .order_by(year_column)
        ).all()
    )

    # Valeur estimée cumulée par pays, convertie dans la devise de référence
    value_rows = db.execute(
        select(models.Item.country, models.Item.currency, func.sum(models.Item.estimated_value))
        .where(models.Item.country.isnot(None), models.Item.estimated_value.isnot(None))
        .group_by(models.Item.country, models.Item.currency)
    ).all()
    country_totals: dict[str, float] = {}
    for country, code, total in value_rows:
        if country is None:
            continue
        country_totals[country] = country_totals.get(country, 0.0) + currency.to_base(
            float(total or 0.0), code, base, rates
        )
    value_by_country = [
        schemas.ValueBucket(key=country, value=round(value, 2))
        for country, value in sorted(
            country_totals.items(), key=lambda pair: pair[1], reverse=True
        )[:20]
    ]

    by_currency = _currency_buckets(db, base)

    return schemas.StatsOut(
        total_items=total_items,
        total_photos=total_photos,
        base_currency=base,
        rates_updated_at=currency.get_rates_meta(db)["rates_updated_at"],
        total_estimated_value=round(total_estimated, 2),
        total_purchase_value=round(total_purchase, 2),
        items_with_estimated_value=with_value,
        by_type=by_type,
        by_status=by_status,
        by_country=by_country,
        by_currency=by_currency,
        by_scale=by_scale,
        by_manufacturer=by_manufacturer,
        by_material=by_material,
        by_year=by_year,
        value_by_country=value_by_country,
    )


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
# Tags
# --------------------------------------------------------------------------- #
@app.get("/api/tags", response_model=list[schemas.TagOut], tags=["tags"])
def list_tags(db: Session = Depends(get_db)):
    return list(db.scalars(select(models.Tag).order_by(models.Tag.name)).all())
