"""Gestion des médias — upload, normalisation et stockage des images.

Chaque image est convertie en WebP et déclinée en deux tailles :
- l'image principale, bornée à `IMAGE_MAX_DIMENSION` (1600px par défaut) ;
- une vignette bornée à `IMAGE_THUMB_DIMENSION` (480px), pour la grille.

Les fichiers sont rangés sous `UPLOAD_DIR/items/<item_id>/<uuid>.webp` et
`..._thumb.webp`. Le dossier est monté en volume Docker et servi en statique
sur `/uploads`.
"""

from __future__ import annotations

import io
import mimetypes
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

# Certaines bases MIME minimales (images slim) ignorent le WebP : on l'enregistre
# pour que les fichiers servis aient le bon Content-Type.
mimetypes.add_type("image/webp", ".webp")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads")).resolve()
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 15 * 1024 * 1024))
MAX_DIMENSION = int(os.getenv("IMAGE_MAX_DIMENSION", 1600))
THUMB_DIMENSION = int(os.getenv("IMAGE_THUMB_DIMENSION", 480))
WEBP_QUALITY = int(os.getenv("IMAGE_WEBP_QUALITY", 85))
THUMB_QUALITY = int(os.getenv("IMAGE_THUMB_QUALITY", 80))

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"}


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _resize(img: Image.Image, max_dim: int) -> Image.Image:
    if max(img.size) <= max_dim:
        return img
    resized = img.copy()
    resized.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    return resized


def save_image(upload: UploadFile, item_id: int) -> tuple[str, str]:
    """Normalise puis enregistre l'image. Renvoie (chemin principal, chemin vignette)."""
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Format d'image non reconnu")

    if img.format not in ALLOWED_FORMATS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Format {img.format} non supporté"
        )

    # Corrige l'orientation EXIF, puis normalise le mode couleur (WebP gère l'alpha).
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")

    rel_dir = Path("items") / str(item_id)
    (UPLOAD_DIR / rel_dir).mkdir(parents=True, exist_ok=True)

    stem = uuid.uuid4().hex
    main_rel = rel_dir / f"{stem}.webp"
    thumb_rel = rel_dir / f"{stem}_thumb.webp"

    try:
        _resize(img, MAX_DIMENSION).save(
            UPLOAD_DIR / main_rel, format="WEBP", quality=WEBP_QUALITY, method=6
        )
        _resize(img, THUMB_DIMENSION).save(
            UPLOAD_DIR / thumb_rel, format="WEBP", quality=THUMB_QUALITY, method=6
        )
    except OSError:
        delete_files(main_rel.as_posix(), thumb_rel.as_posix())
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Échec de l'enregistrement de l'image"
        )

    return main_rel.as_posix(), thumb_rel.as_posix()


def delete_files(*rel_paths: str | None) -> None:
    """Supprime des fichiers du dossier uploads (garde-fou anti path traversal)."""
    for rel in rel_paths:
        if not rel:
            continue
        target = (UPLOAD_DIR / rel).resolve()
        if target.is_relative_to(UPLOAD_DIR) and target.is_file():
            target.unlink(missing_ok=True)
