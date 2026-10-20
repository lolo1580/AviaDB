"""Gestion des médias — upload, normalisation, variantes et stockage.

Chaque image téléversée est convertie en WebP et bornée à `IMAGE_MAX_DIMENSION`
(1600 px par défaut). Les variantes plus petites (vignettes) ne sont **pas**
stockées à l'upload : elles sont produites **à la volée** par
`render_variant()` et mises en cache sur disque (`<nom>_w<largeur>.webp`).

Les fichiers sont rangés sous `UPLOAD_DIR/items/<item_id>/<uuid>.webp` et servis
par la route `/uploads/...` du backend.

Fonctions de maintenance :
- `content_hash` (SHA-256) permet de détecter une image déjà présente ;
- `cleanup_orphans()` supprime les fichiers qui ne sont plus référencés en base.
"""

from __future__ import annotations

import hashlib
import io
import mimetypes
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

# Certaines bases MIME minimales (images slim) ignorent le WebP : on l'enregistre
# pour que les fichiers servis aient le bon Content-Type.
mimetypes.add_type("image/webp", ".webp")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads")).resolve()
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 15 * 1024 * 1024))
MAX_DIMENSION = int(os.getenv("IMAGE_MAX_DIMENSION", 1600))
WEBP_QUALITY = int(os.getenv("IMAGE_WEBP_QUALITY", 85))
THUMB_QUALITY = int(os.getenv("IMAGE_THUMB_QUALITY", 80))

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"}

# Distance de Hamming tolérée entre deux empreintes perceptuelles (0 à 64) :
# en dessous, les images sont considérées comme des quasi-doublons.
DUPLICATE_DISTANCE = int(os.getenv("PHOTO_DUPLICATE_DISTANCE", "5"))

# Bornes des variantes demandées à la volée.
MIN_VARIANT = 32
MAX_VARIANT = 2048


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #
def _resize(img: Image.Image, max_dim: int) -> Image.Image:
    if max(img.size) <= max_dim:
        return img
    resized = img.copy()
    resized.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    return resized


def _normalize(img: Image.Image) -> Image.Image:
    """Corrige l'orientation EXIF et normalise le mode couleur (WebP gère l'alpha)."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        return img.convert("RGBA")
    return img.convert("RGB")


def _encode_webp(img: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=quality, method=6)
    return buffer.getvalue()


def _perceptual_hash(img: Image.Image) -> str:
    """dHash 64 bits : compare les luminances de 9 × 8 pixels voisins."""
    small = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        for offset in range(8):
            left = pixels[row * 9 + offset]
            right = pixels[row * 9 + offset + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def perceptual_distance(first: str, second: str) -> int:
    """Distance de Hamming entre deux empreintes perceptuelles."""
    return (int(first, 16) ^ int(second, 16)).bit_count()


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
def save_image(upload: UploadFile, item_id: int) -> tuple[str, str | None, str, str]:
    """Normalise et enregistre l'image.

    Renvoie `(chemin principal, vignette, empreinte exacte, empreinte
    perceptuelle)`. La vignette vaut toujours `None` : elle est générée à la
    demande (voir `render_variant`).
    """
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fichier vide")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,  # Content Too Large
            f"Image trop volumineuse (max {MAX_UPLOAD_BYTES // (1024 * 1024)} Mo)",
        )

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except UnidentifiedImageError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Format d'image non reconnu") from None

    if img.format not in ALLOWED_FORMATS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Format {img.format} non supporté"
        )

    img = _resize(_normalize(img), MAX_DIMENSION)
    perceptual_hash = _perceptual_hash(img)
    payload = _encode_webp(img, WEBP_QUALITY)
    content_hash = hashlib.sha256(payload).hexdigest()

    rel_dir = Path("items") / str(item_id)
    (UPLOAD_DIR / rel_dir).mkdir(parents=True, exist_ok=True)

    main_rel = rel_dir / f"{uuid.uuid4().hex}.webp"
    try:
        (UPLOAD_DIR / main_rel).write_bytes(payload)
    except OSError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Échec de l'enregistrement de l'image"
        ) from None

    return main_rel.as_posix(), None, content_hash, perceptual_hash


# --------------------------------------------------------------------------- #
# Lecture et variantes à la volée
# --------------------------------------------------------------------------- #
def resolve_upload(relative: str) -> Path | None:
    """Chemin absolu sûr d'un fichier sous `UPLOAD_DIR`, ou `None`."""
    if not relative:
        return None
    target = (UPLOAD_DIR / relative).resolve()
    if not target.is_relative_to(UPLOAD_DIR) or not target.is_file():
        return None
    return target


def _variant_relative(relative: str, width: int) -> str:
    path = Path(relative)
    return (path.parent / f"{path.stem}_w{int(width)}.webp").as_posix()


def cached_variants(relative: str) -> list[str]:
    """Variantes déjà mises en cache pour ce fichier (chemins relatifs)."""
    if not relative:
        return []
    path = Path(relative)
    folder = UPLOAD_DIR / path.parent
    if not folder.is_dir():
        return []
    return [
        candidate.relative_to(UPLOAD_DIR).as_posix()
        for candidate in folder.glob(f"{path.stem}_w*.webp")
    ]


def render_variant(relative: str, width: int) -> bytes:
    """Renvoie une variante WebP à la largeur demandée, avec cache disque.

    Lève `FileNotFoundError` si l'image source n'existe pas.
    """
    width = max(MIN_VARIANT, min(MAX_VARIANT, int(width)))
    cache_rel = _variant_relative(relative, width)
    cache = UPLOAD_DIR / cache_rel
    if cache.is_file():
        return cache.read_bytes()

    source = resolve_upload(relative)
    if source is None:
        raise FileNotFoundError(relative)

    with Image.open(source) as img:
        img.load()
        img.thumbnail((width, width), Image.Resampling.LANCZOS)
        payload = _encode_webp(_normalize(img), THUMB_QUALITY)

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(payload)
    except OSError:
        pass  # le cache est optionnel : on renvoie quand même l'image
    return payload


# --------------------------------------------------------------------------- #
# Rotation / recadrage manuels
# --------------------------------------------------------------------------- #
def transform_image(
    relative: str,
    *,
    rotate: int = 0,
    crop: tuple[float, float, float, float] | None = None,
) -> tuple[str, str, str]:
    """Applique rotation (degrés horaires) et/ou recadrage, sous un nouveau nom.

    `crop` est un quadruplet `(x, y, largeur, hauteur)` en fractions (0 à 1) de
    l'image **après rotation**. Renvoie `(nouveau chemin, empreinte exacte,
    empreinte perceptuelle)`.
    """
    source = resolve_upload(relative)
    if source is None:
        raise FileNotFoundError(relative)

    with Image.open(source) as img:
        img.load()
        img = _normalize(img)

        if rotate % 360:
            # PIL tourne dans le sens anti-horaire : un signe négatif donne le
            # sens horaire attendu par l'interface (« pivoter à droite »).
            img = img.rotate(-(rotate % 360), expand=True)

        if crop is not None:
            x, y, width, height = crop
            img_w, img_h = img.size
            left = max(0, min(img_w - 1, int(x * img_w)))
            top = max(0, min(img_h - 1, int(y * img_h)))
            right = max(left + 1, min(img_w, left + max(1, int(width * img_w))))
            bottom = max(top + 1, min(img_h, top + max(1, int(height * img_h))))
            img = img.crop((left, top, right, bottom))

        final = _resize(img, MAX_DIMENSION)
        perceptual_hash = _perceptual_hash(final)
        payload = _encode_webp(final, WEBP_QUALITY)

    rel_dir = Path(relative).parent
    new_rel = rel_dir / f"{uuid.uuid4().hex}.webp"
    try:
        (UPLOAD_DIR / new_rel).write_bytes(payload)
    except OSError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Échec de l'enregistrement de l'image"
        ) from None
    return new_rel.as_posix(), hashlib.sha256(payload).hexdigest(), perceptual_hash


# --------------------------------------------------------------------------- #
# Suppression et maintenance
# --------------------------------------------------------------------------- #
def delete_files(*rel_paths: str | None) -> None:
    """Supprime des fichiers du dossier uploads (garde-fou anti path traversal)."""
    for rel in rel_paths:
        if not rel:
            continue
        target = (UPLOAD_DIR / rel).resolve()
        if target.is_relative_to(UPLOAD_DIR) and target.is_file():
            target.unlink(missing_ok=True)


def delete_photo_files(photo) -> None:
    """Supprime l'image d'une photo, sa vignette héritée et ses variantes en cache."""
    delete_files(photo.file_path, photo.thumb_path, *cached_variants(photo.file_path))


def backfill_hashes(db: Session) -> int:
    """Calcule les empreintes manquantes (exacte et perceptuelle)."""
    from . import models  # import tardif : évite un cycle au chargement

    updated = 0
    photos = db.scalars(
        select(models.ItemPhoto).where(
            or_(
                models.ItemPhoto.content_hash.is_(None),
                models.ItemPhoto.perceptual_hash.is_(None),
            )
        )
    ).all()
    for photo in photos:
        target = resolve_upload(photo.file_path)
        if target is None:
            continue
        data = target.read_bytes()
        if photo.content_hash is None:
            photo.content_hash = hashlib.sha256(data).hexdigest()
        if photo.perceptual_hash is None:
            try:
                with Image.open(io.BytesIO(data)) as img:
                    img.load()
                    photo.perceptual_hash = _perceptual_hash(img)
            except (UnidentifiedImageError, OSError):
                continue
        updated += 1
    if updated:
        db.commit()
    return updated


def find_duplicate(
    db: Session,
    content_hash: str,
    perceptual_hash: str,
    *,
    threshold: int | None = None,
) -> tuple[int, int, int] | None:
    """Cherche une image identique ou perceptuellement proche.

    La comparaison est **globale** (tous les objets). Renvoie
    `(photo_id, item_id, distance)` ou `None` ; une empreinte exacte est
    prioritaire (distance 0).
    """
    from . import models  # import tardif : évite un cycle au chargement

    limit = DUPLICATE_DISTANCE if threshold is None else threshold
    rows = db.execute(
        select(
            models.ItemPhoto.id,
            models.ItemPhoto.item_id,
            models.ItemPhoto.content_hash,
            models.ItemPhoto.perceptual_hash,
        )
    ).all()

    best: tuple[int, int, int] | None = None
    best_distance = limit + 1
    for photo_id, item_id, stored_content, stored_perceptual in rows:
        if content_hash and stored_content == content_hash:
            return photo_id, item_id, 0
        if perceptual_hash and stored_perceptual:
            distance = perceptual_distance(perceptual_hash, stored_perceptual)
            if distance <= limit and distance < best_distance:
                best = (photo_id, item_id, distance)
                best_distance = distance
    return best


def drop_legacy_thumbnails(db: Session) -> int:
    """Supprime une fois les vignettes historiquement stockées (`_thumb.webp`).

    Les vignettes sont désormais générées à la volée : les anciens fichiers
    deviennent inutiles. L'image principale n'est pas touchée.
    """
    from . import models  # import tardif : évite un cycle au chargement

    removed = 0
    photos = db.scalars(
        select(models.ItemPhoto).where(models.ItemPhoto.thumb_path.isnot(None))
    ).all()
    for photo in photos:
        delete_files(photo.thumb_path)
        photo.thumb_path = None
        removed += 1
    if removed:
        db.commit()
    return removed


def cleanup_orphans(db: Session, *, min_age_seconds: int = 3600) -> int:
    """Supprime les fichiers non référencés en base, plus vieux que `min_age`.

    Renvoie le nombre de fichiers supprimés. `min_age_seconds` protège les
    téléversements en cours (fichier écrit mais ligne pas encore validée).
    """
    from . import models  # import tardif : évite un cycle au chargement

    referenced: set[str] = set()
    rows = db.execute(
        select(models.ItemPhoto.file_path, models.ItemPhoto.thumb_path)
    ).all()
    for file_path, thumb_path in rows:
        if file_path:
            referenced.add(Path(file_path).as_posix())
            referenced.update(cached_variants(file_path))
        if thumb_path:
            referenced.add(Path(thumb_path).as_posix())

    items_dir = UPLOAD_DIR / "items"
    if not items_dir.is_dir():
        return 0

    now = datetime.now(UTC).timestamp()
    removed = 0
    for path in items_dir.rglob("*.webp"):
        relative = path.relative_to(UPLOAD_DIR).as_posix()
        if relative in referenced:
            continue
        try:
            if now - path.stat().st_mtime < min_age_seconds:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue

    # Dossiers d'objets devenus vides (du plus profond au plus haut).
    for folder in sorted(items_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if folder.is_dir():
            try:
                folder.rmdir()  # échoue si non vide
            except OSError:
                continue
    return removed
