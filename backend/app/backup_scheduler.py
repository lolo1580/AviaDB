"""Sauvegardes ZIP automatiques, avec rétention.

Lancé par le service Compose `backup` (même image que le backend) :
toutes les `BACKUP_INTERVAL` secondes, une archive complète (objets, réglages,
comptes et images) est écrite dans `BACKUP_DIR`, puis les plus anciennes
au-delà de `BACKUP_KEEP` sont supprimées.

    python -m app.backup_scheduler
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from . import backup
from .database import SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("aviadb.backup")


def backup_dir() -> Path:
    path = Path(os.getenv("BACKUP_DIR", "/app/backups"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def keep_count() -> int:
    return max(1, int(os.getenv("BACKUP_KEEP", "7")))


def interval_seconds() -> int:
    return max(60, int(os.getenv("BACKUP_INTERVAL", str(24 * 3600))))


def prune() -> list[Path]:
    """Supprime les archives au-delà de la rétention. Renvoie celles retirées."""
    archives = sorted(backup_dir().glob("aviadb-*.zip"))
    removed = archives[: max(0, len(archives) - keep_count())]
    for path in removed:
        path.unlink(missing_ok=True)
        logger.info("Ancienne sauvegarde supprimée : %s", path.name)
    return removed


def run_once() -> Path:
    """Construit une archive et la déplace dans le dossier de sauvegardes."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = backup_dir() / f"aviadb-{stamp}.zip"

    with SessionLocal() as db:
        temporary = backup.build_backup_file(db)
    shutil.move(str(temporary), target)

    logger.info("Sauvegarde écrite : %s", target.name)
    prune()
    return target


def main() -> None:
    interval = interval_seconds()
    logger.info(
        "Planificateur de sauvegarde démarré (toutes les %s s, %s archives conservées)",
        interval,
        keep_count(),
    )
    while True:
        try:
            run_once()
        except Exception:  # pragma: no cover - une itération ne doit pas arrêter la boucle
            logger.exception("Échec de la sauvegarde planifiée")
        time.sleep(interval)


if __name__ == "__main__":
    main()
