"""Modèles SQLAlchemy (PostgreSQL).

Schéma : une table socle `items` reliée à des tables d'attributs spécifiques.
Toutes les colonnes de `items` sont optionnelles (hors `name`/`item_type`/`status`)
afin qu'un même objet socle puisse décrire un avion en métal, un écusson en tissu
ou tout autre objet.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Énumérations métier
# --------------------------------------------------------------------------- #
class ItemType(str, enum.Enum):
    DIECAST = "DIECAST"
    PATCH = "PATCH"
    OTHER = "OTHER"


class ItemStatus(str, enum.Enum):
    EXHIBITED = "EXHIBITED"
    STORED_BOX = "STORED_BOX"
    WANTED = "WANTED"
    PREORDER = "PREORDER"
    TRANSIT = "TRANSIT"


class PatchMaterial(str, enum.Enum):
    EMBROIDERED = "EMBROIDERED"
    PVC = "PVC"
    LEATHER = "LEATHER"
    WOVEN = "WOVEN"


class AttachmentType(str, enum.Enum):
    HOOK_VELCRO = "HOOK_VELCRO"
    LOOP_VELCRO = "LOOP_VELCRO"
    SEW_ON = "SEW_ON"


class PatchShape(str, enum.Enum):
    ROUND = "ROUND"
    SHIELD = "SHIELD"
    TAB = "TAB"
    CUT_OUT = "CUT_OUT"


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"


def _enum(enum_cls: type[enum.Enum]) -> SAEnum:
    """Stocke les énumérations en VARCHAR (avec contrainte) plutôt qu'en type
    énuméré natif : les valeurs restent lisibles et les migrations sont simples."""
    return SAEnum(enum_cls, native_enum=False, validate_strings=True, length=32)


# --------------------------------------------------------------------------- #
# Table de liaison N-to-N items <-> tags
# --------------------------------------------------------------------------- #
item_tags = Table(
    "item_tags",
    Base.metadata,
    Column("item_id", ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


# --------------------------------------------------------------------------- #
# Socle commun
# --------------------------------------------------------------------------- #
class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    item_type: Mapped[ItemType] = mapped_column(_enum(ItemType), index=True)

    country: Mapped[str | None] = mapped_column(String(120), index=True)
    aircraft_model: Mapped[str | None] = mapped_column(String(120), index=True)
    storage_location: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[ItemStatus] = mapped_column(
        _enum(ItemStatus), default=ItemStatus.STORED_BOX, index=True
    )

    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_price: Mapped[float | None] = mapped_column(Float)
    estimated_value: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    # Prêt en cours (l'objet est sorti de la vitrine)
    loaned_to: Mapped[str | None] = mapped_column(String(120))
    loan_date: Mapped[date | None] = mapped_column(Date)
    loan_due_date: Mapped[date | None] = mapped_column(Date)

    # Devise de l'objet et équivalent du prix d'achat en EUR (taux historique)
    currency: Mapped[str | None] = mapped_column(String(3))
    purchase_eur_value: Mapped[float | None] = mapped_column(Float)
    purchase_rate_date: Mapped[date | None] = mapped_column(Date)

    # Classe (arborescente) à laquelle l'objet appartient
    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("classes.id", ondelete="SET NULL"), index=True
    )

    # Précommande (statut PREORDER) : sortie attendue, boutique, acompte versé
    preorder_release_date: Mapped[date | None] = mapped_column(Date)
    preorder_shop: Mapped[str | None] = mapped_column(String(120))
    preorder_deposit: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    diecast: Mapped[DiecastDetails | None] = relationship(
        back_populates="item", cascade="all, delete-orphan", uselist=False
    )
    patch: Mapped[PatchDetails | None] = relationship(
        back_populates="item", cascade="all, delete-orphan", uselist=False
    )
    photos: Mapped[list[ItemPhoto]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="(ItemPhoto.position, ItemPhoto.id)",
    )
    tags: Mapped[list[Tag]] = relationship(secondary=item_tags, back_populates="items")
    item_class: Mapped[ItemClass | None] = relationship(back_populates="items")
    links: Mapped[list[ItemLink]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ItemLink.id"
    )
    price_points: Mapped[list[PricePoint]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="(PricePoint.recorded_on, PricePoint.id)",
    )

    def __repr__(self) -> str:  # pragma: no cover - confort de debug
        return f"<Item id={self.id} name={self.name!r} type={self.item_type.value}>"


# --------------------------------------------------------------------------- #
# Détails spécifiques — maquettes diecast
# --------------------------------------------------------------------------- #
class DiecastDetails(Base):
    __tablename__ = "diecast_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), unique=True, index=True
    )

    scale: Mapped[str | None] = mapped_column(String(32))  # "1/72", "1/48"...
    manufacturer: Mapped[str | None] = mapped_column(String(120))  # "Hobby Master"
    part_number: Mapped[str | None] = mapped_column(String(120))  # réf boîte "HA6501"
    registration_number: Mapped[str | None] = mapped_column(String(120))  # immat. réelle
    configuration: Mapped[str | None] = mapped_column(Text)  # train, réservoirs, missiles

    item: Mapped[Item] = relationship(back_populates="diecast")


# --------------------------------------------------------------------------- #
# Détails spécifiques — patchs
# --------------------------------------------------------------------------- #
class PatchDetails(Base):
    __tablename__ = "patch_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), unique=True, index=True
    )

    unit_squadron: Mapped[str | None] = mapped_column(String(120))  # "Flottille 11F"
    base: Mapped[str | None] = mapped_column(String(120))  # "BAN Landivisiau"
    material: Mapped[PatchMaterial | None] = mapped_column(_enum(PatchMaterial))
    attachment_type: Mapped[AttachmentType | None] = mapped_column(_enum(AttachmentType))
    shape: Mapped[PatchShape | None] = mapped_column(_enum(PatchShape))
    event_or_mission: Mapped[str | None] = mapped_column(String(160))

    item: Mapped[Item] = relationship(back_populates="patch")


# --------------------------------------------------------------------------- #
# Photos (1-to-N)
# --------------------------------------------------------------------------- #
class ItemPhoto(Base):
    __tablename__ = "item_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )

    file_path: Mapped[str] = mapped_column(String(512))  # chemin relatif sous uploads/
    thumb_path: Mapped[str | None] = mapped_column(String(512))  # vignette (grille)
    position: Mapped[int] = mapped_column(Integer, default=0)  # ordre d'affichage
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    caption: Mapped[str | None] = mapped_column(String(255))
    # Empreinte SHA-256 de l'image normalisée : détection des doublons exacts.
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    # Empreinte perceptuelle (dHash 64 bits, hex) : détection des quasi-doublons.
    perceptual_hash: Mapped[str | None] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[Item] = relationship(back_populates="photos")


# --------------------------------------------------------------------------- #
# Tags (N-to-N)
# --------------------------------------------------------------------------- #
class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("name", name="uq_tags_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)

    items: Mapped[list[Item]] = relationship(secondary=item_tags, back_populates="tags")


# --------------------------------------------------------------------------- #
# Classes (arborescence : classe -> sous-classe -> …)
# --------------------------------------------------------------------------- #
class ItemClass(Base):
    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_classes_parent_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("classes.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    parent: Mapped[ItemClass | None] = relationship(
        back_populates="children", remote_side="ItemClass.id"
    )
    children: Mapped[list[ItemClass]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="(ItemClass.position, ItemClass.name)",
    )
    items: Mapped[list[Item]] = relationship(back_populates="item_class")

    def __repr__(self) -> str:  # pragma: no cover - confort de debug
        return f"<ItemClass id={self.id} name={self.name!r} parent={self.parent_id}>"


# --------------------------------------------------------------------------- #
# Clés d'API (accès en lecture aux métriques, pour un site externe)
# --------------------------------------------------------------------------- #
class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("key_hash", name="uq_api_keys_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    # Seule l'empreinte est conservée : la clé en clair n'est affichée qu'une fois.
    key_hash: Mapped[str] = mapped_column(String(64), index=True)
    prefix: Mapped[str] = mapped_column(String(24))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:  # pragma: no cover - confort de debug
        return f"<ApiKey id={self.id} label={self.label!r} active={self.is_active}>"


# --------------------------------------------------------------------------- #
# Comptes utilisateurs (admin / lecteur)
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover - confort de debug
        return f"<User id={self.id} username={self.username!r} role={self.role.value}>"


# --------------------------------------------------------------------------- #
# Liens externes (boutique, fiche technique, référence…)
# --------------------------------------------------------------------------- #
class ItemLink(Base):
    __tablename__ = "item_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(1024))
    label: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[Item] = relationship(back_populates="links")


# --------------------------------------------------------------------------- #
# Relevés de prix (historique, pour suivre l'évolution d'une pièce)
# --------------------------------------------------------------------------- #
class PricePoint(Base):
    __tablename__ = "price_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    # Équivalent EUR figé au moment du relevé : permet de tracer une courbe
    # cohérente même si les relevés ne sont pas dans la même devise.
    eur_value: Mapped[float | None] = mapped_column(Float)
    recorded_on: Mapped[date] = mapped_column(Date, index=True)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[Item] = relationship(back_populates="price_points")


# --------------------------------------------------------------------------- #
# Réglages applicatifs (devise de référence, taux de change…)
# --------------------------------------------------------------------------- #
class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # valeur JSON


# --------------------------------------------------------------------------- #
# Journal d'activité (audit des requêtes de modification)
# --------------------------------------------------------------------------- #
class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    username: Mapped[str | None] = mapped_column(String(64))  # None = session anonyme
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(255))
    status_code: Mapped[int] = mapped_column(Integer)

    def __repr__(self) -> str:  # pragma: no cover - confort de debug
        return f"<ActivityLog {self.method} {self.path} -> {self.status_code}>"
