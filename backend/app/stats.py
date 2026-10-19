"""Calcul des statistiques de la collection.

Extrait de `main.py` : les mêmes agrégats servent à l'interface (`/api/stats`)
et à l'API publique protégée par clé (`/api/public/stats`).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import crud, currency, models, schemas

# Statuts dont l'objet n'est pas encore possédé (recherché ou précommandé) :
# ils sont exclus des valeurs de la collection.
_NOT_OWNED = (models.ItemStatus.WANTED, models.ItemStatus.PREORDER)


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


def compute_stats(db: Session, *, include_details: bool = False) -> schemas.StatsOut:
    """Compteurs, valeurs et répartitions, dans la devise de référence.

    `include_details` ajoute les analytiques réservés à la session authentifiée
    (valeur par classe, par emplacement, par année, plus-values) : l'API publique
    ne doit exposer aucun emplacement ni écart de valeur par objet.
    """
    total_items = db.scalar(select(func.count()).select_from(models.Item)) or 0
    total_photos = db.scalar(select(func.count()).select_from(models.ItemPhoto)) or 0

    base = currency.get_base_currency(db)
    rates = currency.get_rates(db)

    # Valeur estimée : conversion depuis la devise de chaque objet, aux taux courants
    estimated_rows = db.execute(
        select(models.Item.currency, func.sum(models.Item.estimated_value))
        .where(
            models.Item.estimated_value.isnot(None),
            models.Item.status.notin_(_NOT_OWNED),
        )
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
        ).where(
            models.Item.purchase_price.isnot(None),
            models.Item.status.notin_(_NOT_OWNED),
        )
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
        .where(
            models.Item.estimated_value.isnot(None),
            models.Item.status.notin_(_NOT_OWNED),
        )
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

    # Années d'achat (PostgreSQL : extraction de l'année)
    year_column = func.to_char(models.Item.purchase_date, "YYYY")
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
        .where(
            models.Item.country.isnot(None),
            models.Item.estimated_value.isnot(None),
            models.Item.status.notin_(_NOT_OWNED),
        )
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

    # Répartition par classe de premier niveau (racine de l'arborescence)
    classes = crud.all_classes(db)
    by_id = {node.id: node for node in classes}
    roots = {
        node.id: (crud.class_path(by_id, node.id) or [None])[0]
        for node in classes
    }
    class_rows = db.execute(
        select(models.Item.class_id, func.count())
        .where(models.Item.class_id.isnot(None))
        .group_by(models.Item.class_id)
    ).all()
    class_counts: dict[str, int] = {}
    for class_id, count in class_rows:
        key = roots.get(class_id) or "Sans classe"
        class_counts[key] = class_counts.get(key, 0) + count
    by_class = [
        schemas.CountBucket(key=key, count=count)
        for key, count in sorted(class_counts.items(), key=lambda pair: -pair[1])
    ]

    # ----------------------------------------------------------------------- #
    # Analytiques détaillés (session uniquement)
    # ----------------------------------------------------------------------- #
    value_by_class: list[schemas.ValueBucket] = []
    value_by_location: list[schemas.ValueBucket] = []
    value_by_year: list[schemas.ValueBucket] = []
    top_gains: list[schemas.ItemValueBucket] = []
    top_losses: list[schemas.ItemValueBucket] = []

    if include_details:
        # Valeur estimée par classe racine.
        class_value_rows = db.execute(
            select(
                models.Item.class_id,
                models.Item.currency,
                func.sum(models.Item.estimated_value),
            )
            .where(
                models.Item.estimated_value.isnot(None),
                models.Item.status.notin_(_NOT_OWNED),
            )
            .group_by(models.Item.class_id, models.Item.currency)
        ).all()
        class_values: dict[str, float] = {}
        for class_id, code, total in class_value_rows:
            key = (roots.get(class_id) if class_id is not None else None) or "Sans classe"
            class_values[key] = class_values.get(key, 0.0) + currency.to_base(
                float(total or 0.0), code, base, rates
            )
        value_by_class = [
            schemas.ValueBucket(key=key, value=round(value, 2))
            for key, value in sorted(class_values.items(), key=lambda pair: -pair[1])
        ]

        # Valeur estimée par emplacement de stockage.
        location_rows = db.execute(
            select(
                models.Item.storage_location,
                models.Item.currency,
                func.sum(models.Item.estimated_value),
            )
            .where(
                models.Item.estimated_value.isnot(None),
                models.Item.status.notin_(_NOT_OWNED),
            )
            .group_by(models.Item.storage_location, models.Item.currency)
        ).all()
        location_values: dict[str, float] = {}
        for location, code, total in location_rows:
            key = location or "Sans emplacement"
            location_values[key] = location_values.get(key, 0.0) + currency.to_base(
                float(total or 0.0), code, base, rates
            )
        value_by_location = [
            schemas.ValueBucket(key=key, value=round(value, 2))
            for key, value in sorted(location_values.items(), key=lambda pair: -pair[1])
        ]

        # Valeur d'acquisition par année (équivalent EUR figé, puis devise de référence).
        year_value_rows = db.execute(
            select(
                year_column,
                models.Item.currency,
                models.Item.purchase_eur_value,
                models.Item.purchase_price,
            ).where(
                models.Item.purchase_date.isnot(None),
                models.Item.purchase_price.isnot(None),
                models.Item.status.notin_(_NOT_OWNED),
            )
        ).all()
        year_values: dict[str, float] = {}
        for year, code, eur_value, price in year_value_rows:
            if eur_value is None:
                eur_value = currency.to_eur(float(price), code, rates)
            year_values[year] = year_values.get(year, 0.0) + float(eur_value) * rates.get(base, 1.0)
        value_by_year = [
            schemas.ValueBucket(key=year, value=round(value, 2))
            for year, value in sorted(year_values.items())
        ]

        # Plus-values / moins-values par objet.
        gains: list[schemas.ItemValueBucket] = []
        for item in db.scalars(
            select(models.Item).where(
                models.Item.estimated_value.isnot(None),
                models.Item.status.notin_(_NOT_OWNED),
            )
        ).all():
            if item.purchase_price is None and item.purchase_eur_value is None:
                continue
            estimated = currency.to_base(float(item.estimated_value), item.currency, base, rates)
            purchase_eur = item.purchase_eur_value
            if purchase_eur is None:
                purchase_eur = currency.to_eur(float(item.purchase_price), item.currency, rates)
            purchase = float(purchase_eur) * rates.get(base, 1.0)
            gains.append(
                schemas.ItemValueBucket(
                    id=item.id,
                    name=item.name,
                    estimated_value=round(estimated, 2),
                    purchase_value=round(purchase, 2),
                    gain=round(estimated - purchase, 2),
                )
            )
        top_gains = sorted((g for g in gains if g.gain > 0), key=lambda g: -g.gain)[:5]
        top_losses = sorted((g for g in gains if g.gain < 0), key=lambda g: g.gain)[:5]

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
        by_class=by_class,
        by_year=by_year,
        value_by_country=value_by_country,
        value_by_class=value_by_class,
        value_by_location=value_by_location,
        value_by_year=value_by_year,
        top_gains=top_gains,
        top_losses=top_losses,
    )
