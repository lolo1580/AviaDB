"""Clés d'API : émission, vérification et point d'accès public.

Une clé donne accès **aux seules métriques agrégées** (`/api/public/stats`), sans
aucune donnée nominative ni prix par objet. Elle s'utilise via l'en-tête
`X-API-Key`, ce qui permet à un site externe (page d'accueil, widget) de lire
quelques chiffres sans disposer d'un compte.

Seule l'empreinte SHA-256 de la clé est stockée : la valeur en clair n'est
affichée qu'une fois, à la création.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas
from .database import get_db
from .stats import compute_stats

logger = logging.getLogger("aviadb.api_keys")

KEY_PREFIX = "aviadb_"
KEY_BYTES = 24  # ~32 caractères en base64 urlsafe

# Limitation de débit par clé : un widget mal configuré ne doit pas marteler la
# base. En mémoire, suffisant pour un service mono-processus.
RATE_LIMIT = int(os.getenv("PUBLIC_RATE_LIMIT", "60"))
RATE_WINDOW = int(os.getenv("PUBLIC_RATE_WINDOW", "60"))
_hits: dict[int, list[float]] = {}


def _too_many_requests(key_id: int) -> bool:
    now = time.time()
    recent = [stamp for stamp in _hits.get(key_id, []) if now - stamp < RATE_WINDOW]
    _hits[key_id] = recent
    return len(recent) >= RATE_LIMIT


def _record_hit(key_id: int) -> None:
    _hits.setdefault(key_id, []).append(time.time())


def generate_key() -> str:
    """Clé en clair, montrée une seule fois à la création."""
    return f"{KEY_PREFIX}{secrets.token_urlsafe(KEY_BYTES)}"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def display_prefix(key: str) -> str:
    return f"{key[: len(KEY_PREFIX) + 6]}…"


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> models.ApiKey:
    """Dépendance des routes publiques : valide la clé et journalise l'usage."""
    token = x_api_key or request.query_params.get("api_key")
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Clé d'API requise (en-tête X-API-Key)",
        )

    record = db.scalars(
        select(models.ApiKey).where(models.ApiKey.key_hash == hash_key(token))
    ).first()
    if record is None or not record.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clé d'API invalide ou révoquée")

    if _too_many_requests(record.id):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Trop d'appels (max {RATE_LIMIT} par {RATE_WINDOW} s)",
        )
    _record_hit(record.id)

    record.last_used_at = datetime.now(UTC)
    record.request_count += 1
    db.commit()
    return record


router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/stats", response_model=schemas.StatsOut)
def public_stats(_: models.ApiKey = Depends(require_api_key), db: Session = Depends(get_db)):
    """Métriques agrégées de la collection, en lecture seule.

    Aucun nom d'objet, aucun prix unitaire, aucun emplacement n'est exposé.
    """
    return compute_stats(db)
