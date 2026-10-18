"""Opérations de persistance partagées (API publique et admin)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import currency, models, schemas


def resolve_tags(db: Session, names: list[str]) -> list[models.Tag]:
    """Récupère les tags existants ou les crée (get-or-create), sans doublon."""
    resolved: list[models.Tag] = []
    seen: set[str] = set()
    for raw in names:
        name = (raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        tag = db.scalars(select(models.Tag).where(models.Tag.name == name)).first()
        if tag is None:
            tag = models.Tag(name=name)
            db.add(tag)
        resolved.append(tag)
    return resolved


def apply_amounts(db: Session, item: models.Item) -> None:
    """Fixe la devise et l'équivalent EUR du prix d'achat.

    Le prix d'achat est converti avec le taux du **jour de l'achat** ; le
    résultat en EUR est figé sur l'objet, donc indépendant de la devise de
    référence choisie ensuite. Si le taux historique est introuvable, on
    retombe sur le taux courant (et `purchase_rate_date` reste vide).
    """
    base = currency.get_base_currency(db)
    code = (item.currency or base).upper()
    if code not in currency.CURRENCIES:
        code = base
    item.currency = code

    if item.purchase_price is None:
        item.purchase_eur_value = None
        item.purchase_rate_date = None
        return

    per_eur, used_date = currency.historical_per_eur(db, code, item.purchase_date)
    item.purchase_eur_value = round(item.purchase_price / per_eur, 4) if per_eur else None
    item.purchase_rate_date = used_date


def create_item(db: Session, payload: schemas.ItemCreate) -> models.Item:
    """Construit un Item (socle + détails + tags + montants) et l'ajoute à la session."""
    item = models.Item(**payload.model_dump(exclude={"diecast", "patch", "tags"}))

    if payload.diecast is not None:
        item.diecast = models.DiecastDetails(**payload.diecast.model_dump())
    if payload.patch is not None:
        item.patch = models.PatchDetails(**payload.patch.model_dump())

    item.tags = resolve_tags(db, payload.tags)
    apply_amounts(db, item)
    db.add(item)
    return item


# --------------------------------------------------------------------------- #
# Classes (arborescence)
# --------------------------------------------------------------------------- #
def all_classes(db: Session) -> list[models.ItemClass]:
    """Toutes les classes, triées pour un affichage hiérarchique stable."""
    return list(
        db.scalars(
            select(models.ItemClass).order_by(
                models.ItemClass.position, models.ItemClass.name
            )
        ).all()
    )


def class_descendant_ids(classes: list[models.ItemClass], root_id: int) -> set[int]:
    """Identifiants de `root_id` et de toute sa descendance."""
    children: dict[int | None, list[int]] = {}
    for node in classes:
        children.setdefault(node.parent_id, []).append(node.id)

    found: set[int] = set()
    pending = [root_id]
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(children.get(current, []))
    return found


def class_path(classes_by_id: dict[int, models.ItemClass], class_id: int | None) -> list[str]:
    """Chemin lisible (« Aéronefs › Chasseur › Rafale ») d'une classe."""
    names: list[str] = []
    seen: set[int] = set()
    current = class_id
    while current is not None and current in classes_by_id and current not in seen:
        seen.add(current)
        node = classes_by_id[current]
        names.append(node.name)
        current = node.parent_id
    return list(reversed(names))
