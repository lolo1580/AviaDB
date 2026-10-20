"""Exécution des migrations Alembic au démarrage.

Une base existante créée avant Alembic est d'abord **estampillée** à la
révision de référence (0001) : on ne rejoue pas la création des tables, puis
les migrations suivantes (dont `perceptual_hash`) sont appliquées normalement.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .database import engine

logger = logging.getLogger("aviadb.migrations")

BASELINE_REVISION = "0001"
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def run_migrations() -> None:
    config = _config()
    tables = set(inspect(engine).get_table_names())

    if "items" in tables and "alembic_version" not in tables:
        logger.info("Base existante : estampillage à la révision %s", BASELINE_REVISION)
        command.stamp(config, BASELINE_REVISION)

    command.upgrade(config, "head")
