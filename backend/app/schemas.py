"""Schémas Pydantic (v2) — entrées/sorties de l'API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import (
    AttachmentType,
    ItemStatus,
    ItemType,
    PatchMaterial,
    PatchShape,
    UserRole,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DateGuard(BaseModel):
    """Refuse les dates manifestement erronées.

    Un champ `date` mal rempli côté navigateur (« 05/05 » saisi à la main) peut
    produire « 0005-05-05 » : on borne les années à une plage plausible.
    """

    @field_validator("purchase_date", "loan_date", "loan_due_date", check_fields=False)
    @classmethod
    def _plausible_date(cls, value: date | None) -> date | None:
        if value is not None and not 1900 <= value.year <= 2100:
            raise ValueError("année hors limites plausibles (1900 à 2100)")
        return value


# --------------------------------------------------------------------------- #
# Détails maquettes
# --------------------------------------------------------------------------- #
class DiecastDetailsIn(BaseModel):
    scale: str | None = Field(None, max_length=32)
    manufacturer: str | None = Field(None, max_length=120)
    part_number: str | None = Field(None, max_length=120)
    registration_number: str | None = Field(None, max_length=120)
    configuration: str | None = None


class DiecastDetailsOut(ORMModel):
    id: int
    scale: str | None = None
    manufacturer: str | None = None
    part_number: str | None = None
    registration_number: str | None = None
    configuration: str | None = None


# --------------------------------------------------------------------------- #
# Détails patchs
# --------------------------------------------------------------------------- #
class PatchDetailsIn(BaseModel):
    unit_squadron: str | None = Field(None, max_length=120)
    base: str | None = Field(None, max_length=120)
    material: PatchMaterial | None = None
    attachment_type: AttachmentType | None = None
    shape: PatchShape | None = None
    event_or_mission: str | None = Field(None, max_length=160)


class PatchDetailsOut(ORMModel):
    id: int
    unit_squadron: str | None = None
    base: str | None = None
    material: PatchMaterial | None = None
    attachment_type: AttachmentType | None = None
    shape: PatchShape | None = None
    event_or_mission: str | None = None


# --------------------------------------------------------------------------- #
# Photos & tags
# --------------------------------------------------------------------------- #
class PhotoOut(ORMModel):
    id: int
    file_path: str
    thumb_path: str | None = None
    position: int = 0
    is_primary: bool
    caption: str | None = None
    created_at: datetime


class PhotoUpdate(BaseModel):
    caption: str | None = Field(None, max_length=255)
    is_primary: bool | None = None


class PhotoReorderIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class TagOut(ORMModel):
    id: int
    name: str


# --------------------------------------------------------------------------- #
# Item
# --------------------------------------------------------------------------- #
class ItemBase(DateGuard):
    name: str = Field(min_length=1, max_length=255)
    item_type: ItemType
    country: str | None = Field(None, max_length=120)
    aircraft_model: str | None = Field(None, max_length=120)
    storage_location: str | None = Field(None, max_length=120)
    status: ItemStatus = ItemStatus.STORED_BOX
    purchase_date: date | None = None
    purchase_price: float | None = Field(None, ge=0)
    estimated_value: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    notes: str | None = None
    loaned_to: str | None = Field(None, max_length=120)
    loan_date: date | None = None
    loan_due_date: date | None = None


class ItemCreate(ItemBase):
    diecast: DiecastDetailsIn | None = None
    patch: PatchDetailsIn | None = None
    tags: list[str] = Field(default_factory=list)


class ItemUpdate(DateGuard):
    """Mise à jour partielle : seuls les champs fournis sont modifiés."""

    name: str | None = Field(None, min_length=1, max_length=255)
    item_type: ItemType | None = None
    country: str | None = Field(None, max_length=120)
    aircraft_model: str | None = Field(None, max_length=120)
    storage_location: str | None = Field(None, max_length=120)
    status: ItemStatus | None = None
    purchase_date: date | None = None
    purchase_price: float | None = Field(None, ge=0)
    estimated_value: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    notes: str | None = None
    loaned_to: str | None = Field(None, max_length=120)
    loan_date: date | None = None
    loan_due_date: date | None = None
    diecast: DiecastDetailsIn | None = None
    patch: PatchDetailsIn | None = None
    tags: list[str] | None = None


class ItemOut(ORMModel):
    id: int
    name: str
    item_type: ItemType
    country: str | None = None
    aircraft_model: str | None = None
    storage_location: str | None = None
    status: ItemStatus
    purchase_date: date | None = None
    purchase_price: float | None = None
    estimated_value: float | None = None
    currency: str | None = None
    purchase_eur_value: float | None = None
    purchase_rate_date: date | None = None
    notes: str | None = None
    loaned_to: str | None = None
    loan_date: date | None = None
    loan_due_date: date | None = None
    created_at: datetime
    updated_at: datetime
    diecast: DiecastDetailsOut | None = None
    patch: PatchDetailsOut | None = None
    photos: list[PhotoOut] = Field(default_factory=list)
    tags: list[TagOut] = Field(default_factory=list)


class ItemListOut(BaseModel):
    total: int
    items: list[ItemOut]


class CountBucket(BaseModel):
    key: str
    count: int


class ValueBucket(BaseModel):
    key: str
    value: float


class StatsOut(BaseModel):
    total_items: int
    total_photos: int
    base_currency: str
    rates_updated_at: str | None = None
    total_estimated_value: float
    total_purchase_value: float
    items_with_estimated_value: int
    by_type: list[CountBucket]
    by_status: list[CountBucket]
    by_country: list[CountBucket]
    by_currency: list[CountBucket]
    by_scale: list[CountBucket]
    by_manufacturer: list[CountBucket]
    by_material: list[CountBucket]
    by_year: list[CountBucket]
    value_by_country: list[ValueBucket]


class CurrencyOption(BaseModel):
    code: str
    label: str


class SettingsOut(BaseModel):
    default_currency: str
    currencies: list[CurrencyOption]
    rates: dict[str, float]
    rates_updated_at: str | None = None
    rates_source: str | None = None


class SettingsUpdate(BaseModel):
    default_currency: str = Field(min_length=3, max_length=3)


class RatesUpdate(BaseModel):
    rates: dict[str, float]


class FacetsOut(BaseModel):
    countries: list[str]
    aircraft_models: list[str]
    storage_locations: list[str]
    scales: list[str]
    manufacturers: list[str]
    tags: list[str]


class EnumOptions(BaseModel):
    item_types: list[str]
    statuses: list[str]
    materials: list[str]
    attachment_types: list[str]
    shapes: list[str]


# --------------------------------------------------------------------------- #
# Administration
# --------------------------------------------------------------------------- #
class LoginIn(BaseModel):
    username: str = Field("admin", min_length=1, max_length=64)
    password: str = Field(min_length=1)


class TokenOut(BaseModel):
    token: str
    expires_at: int
    username: str
    role: str


class SessionOut(BaseModel):
    enabled: bool
    authenticated: bool
    username: str | None = None
    role: str | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: UserRole = UserRole.VIEWER


class UserUpdate(BaseModel):
    password: str | None = Field(None, min_length=6, max_length=128)
    role: UserRole | None = None
    is_active: bool | None = None


class UserOut(ORMModel):
    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class RestoreResultOut(BaseModel):
    created: int
    photos_restored: int
    users_restored: int = 0
    replaced: bool
    errors: list[str] = Field(default_factory=list)


class BulkActionIn(BaseModel):
    ids: list[int] = Field(min_length=1)
    action: Literal["delete", "set_status", "add_tags", "remove_tags"]
    status: ItemStatus | None = None
    tags: list[str] = Field(default_factory=list)


class BulkResultOut(BaseModel):
    action: str
    affected: int


class ExportOut(BaseModel):
    version: int = 1
    exported_at: datetime
    total: int
    items: list[ItemOut]


class ImportResultOut(BaseModel):
    created: int
    errors: list[str] = Field(default_factory=list)


class TagUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
