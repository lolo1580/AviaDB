"""Authentification et autorisation — comptes utilisateurs et rôles.

Modèle :
- `ADMIN` : accès complet (lecture + écriture + gestion des comptes) ;
- `VIEWER` : lecture seule.

L'accès à l'application est protégé dès qu'au moins un compte existe (ou que
`ADMIN_PASSWORD` est défini, ce qui crée le premier compte admin au démarrage).

Les jetons sont des HMAC-SHA256 signés (sans état serveur), transmis par cookie
`HttpOnly` ou en-tête `Authorization: Bearer`. Les mots de passe sont hachés en
PBKDF2-SHA256 (stdlib, aucun paquet externe).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas
from .database import get_db

logger = logging.getLogger("aviadb.auth")

COOKIE_NAME = "aviadb_admin"
PBKDF2_ITERATIONS = 200_000


# --------------------------------------------------------------------------- #
# Configuration (lue dynamiquement : surchargeable, donc testable)
# --------------------------------------------------------------------------- #
def admin_password() -> str:
    return os.getenv("ADMIN_PASSWORD", "") or ""


def admin_username() -> str:
    return os.getenv("ADMIN_USERNAME", "") or "admin"


def secret_key() -> str:
    return os.getenv("SECRET_KEY", "") or admin_password() or "aviadb-dev-secret"


def token_ttl() -> int:
    return int(os.getenv("ADMIN_TOKEN_TTL", str(12 * 3600)))


def cookie_secure() -> bool:
    return os.getenv("ADMIN_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}


def max_failures() -> int:
    return int(os.getenv("ADMIN_MAX_FAILURES", "10"))


def failure_window() -> int:
    return int(os.getenv("ADMIN_FAILURE_WINDOW", "300"))


# --------------------------------------------------------------------------- #
# État de protection (mis en cache, recalculé aux changements de comptes)
# --------------------------------------------------------------------------- #
# Mots de passe notoirement faibles : le compose en propose un par défaut, mieux
# vaut prévenir bruyamment s'il n'a pas été changé.
WEAK_PASSWORDS = {
    "change-me",
    "changeme",
    "password",
    "motdepasse",
    "admin",
    "aviadb",
    "secret",
    "123456",
}

_protection_enabled = False


def protection_enabled() -> bool:
    return _protection_enabled


def refresh_protection(db: Session) -> bool:
    """Recalcule si l'application doit exiger une authentification."""
    global _protection_enabled
    users = db.scalar(select(func.count()).select_from(models.User)) or 0
    _protection_enabled = bool(admin_password()) or users > 0
    return _protection_enabled


# --------------------------------------------------------------------------- #
# Mots de passe
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError, AttributeError):
        return False


# --------------------------------------------------------------------------- #
# Jetons
# --------------------------------------------------------------------------- #
def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_token(username: str, role: str, ttl: int | None = None) -> tuple[str, int]:
    expires_at = int(time.time()) + (ttl if ttl is not None else token_ttl())
    payload = _b64e(json.dumps({"sub": username, "role": role, "exp": expires_at}).encode())
    signature = hmac.new(secret_key().encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64e(signature)}", expires_at


def verify_token(token: str | None) -> dict | None:
    """Renvoie les « claims » du jeton s'il est valide, sinon None."""
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(secret_key().encode(), payload.encode(), hashlib.sha256).digest()
    try:
        given = _b64d(signature)
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(expected, given):
        return None
    try:
        claims = json.loads(_b64d(payload))
    except (ValueError, TypeError):
        return None
    if int(claims.get("exp", 0)) <= time.time():
        return None
    return claims


def token_from(authorization: str | None, cookie: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return cookie


def claims_from_request(
    authorization: str | None = Header(None),
    aviadb_admin: str | None = Cookie(None),
) -> dict | None:
    return verify_token(token_from(authorization, aviadb_admin))


# --------------------------------------------------------------------------- #
# Dépendances d'autorisation
# --------------------------------------------------------------------------- #
def is_authenticated(
    authorization: str | None = Header(None),
    aviadb_admin: str | None = Cookie(None),
) -> bool:
    return claims_from_request(authorization, aviadb_admin) is not None


def require_authenticated(
    claims: dict | None = Depends(claims_from_request),
) -> dict:
    """Exige une session valide (n'importe quel rôle)."""
    if not protection_enabled():
        return {"sub": "anonymous", "role": models.UserRole.ADMIN.value}
    if claims is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


def require_admin(
    claims: dict = Depends(require_authenticated),
    db: Session = Depends(get_db),
) -> dict:
    """Exige le rôle ADMIN, et revérifie le compte en base (révocation immédiate)."""
    if not protection_enabled():
        return claims

    if claims.get("role") != models.UserRole.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")

    # Vérification en base : un compte supprimé ou rétrogradé perd ses droits.
    user = db.scalars(select(models.User).where(models.User.username == claims.get("sub"))).first()
    if user is None or not user.is_active or user.role != models.UserRole.ADMIN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte invalide ou désactivé")
    return claims


# --------------------------------------------------------------------------- #
# Anti brute-force (en mémoire)
# --------------------------------------------------------------------------- #
_failures: dict[str, list[float]] = {}


def reset_failures() -> None:
    _failures.clear()


def _too_many_failures(client: str) -> bool:
    now = time.time()
    recent = [ts for ts in _failures.get(client, []) if now - ts < failure_window()]
    _failures[client] = recent
    return len(recent) >= max_failures()


def _record_failure(client: str) -> None:
    _failures.setdefault(client, []).append(time.time())


# --------------------------------------------------------------------------- #
# Amorçage : premier compte admin
# --------------------------------------------------------------------------- #
def bootstrap_admin(db: Session) -> bool:
    """Crée le compte admin initial si `ADMIN_PASSWORD` est défini et qu'aucun
    compte n'existe. Le mot de passe n'est jamais écrasé ensuite (gérez les
    comptes depuis l'interface)."""
    password = admin_password()
    users = db.scalar(select(func.count()).select_from(models.User)) or 0
    created = False
    if password and users == 0:
        db.add(
            models.User(
                username=admin_username(),
                password_hash=hash_password(password),
                role=models.UserRole.ADMIN,
            )
        )
        db.commit()
        created = True
        logger.info("Compte admin initial « %s » créé", admin_username())

    refresh_protection(db)
    if created:
        logger.info("Protection par authentification activée")
    elif not protection_enabled():
        logger.warning(
            "Aucun compte et ADMIN_PASSWORD non défini : l'application est accessible "
            "sans authentification. Définissez ADMIN_PASSWORD pour activer la protection."
        )

    if protection_enabled() and password.strip().lower() in WEAK_PASSWORDS:
        logger.warning(
            "ADMIN_PASSWORD est un mot de passe faible (« %s ») : changez-le, ou "
            "modifiez-le depuis Administration → Comptes.",
            password,
        )
    return created


# --------------------------------------------------------------------------- #
# Routes de session
# --------------------------------------------------------------------------- #
router = APIRouter(prefix="/api/admin", tags=["auth"])


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if not protection_enabled():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Aucun compte configuré (définissez ADMIN_PASSWORD)",
        )

    client = request.client.host if request.client else "unknown"
    if _too_many_failures(client):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Trop de tentatives, réessayez dans quelques minutes",
        )

    user = db.scalars(
        select(models.User).where(models.User.username == payload.username)
    ).first()

    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        _record_failure(client)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants incorrects")

    _failures.pop(client, None)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token, expires_at = create_token(user.username, user.role.value)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=token_ttl(),
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
        path="/",
    )
    return schemas.TokenOut(token=token, expires_at=expires_at, username=user.username, role=user.role.value)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return None


@router.get("/session", response_model=schemas.SessionOut)
def session(claims: dict | None = Depends(claims_from_request)):
    return schemas.SessionOut(
        enabled=protection_enabled(),
        authenticated=claims is not None,
        username=claims.get("sub") if claims else None,
        role=claims.get("role") if claims else None,
    )
