"""Ajout idempotent des colonnes manquantes (PostgreSQL).

`Base.metadata.create_all` crée les tables absentes mais ne modifie jamais une
table existante. Comme une base peut déjà contenir des données, on complète le
schéma au démarrage : chaque colonne manquante est ajoutée par
`ALTER TABLE ... ADD COLUMN`, sans rien détruire ni perdre de données.

Pour des évolutions plus lourdes (renommage, contrainte, index), passer à un
outil de migration dédié type Alembic.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from .database import engine

logger = logging.getLogger("aviadb.migrations")

# Colonnes ajoutées après coup : {table: {colonne: définition SQL}}
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "item_photos": {
        "position": "INTEGER NOT NULL DEFAULT 0",
    },
    "items": {
        "loaned_to": "VARCHAR(120)",
        "loan_date": "DATE",
        "loan_due_date": "DATE",
        "currency": "VARCHAR(3)",
        "purchase_eur_value": "DOUBLE PRECISION",
        "purchase_rate_date": "DATE",
        "class_id": "INTEGER REFERENCES classes(id) ON DELETE SET NULL",
    },
}


def ensure_schema() -> list[str]:
    """Ajoute les colonnes manquantes. Renvoie la liste des colonnes ajoutées."""
    applied: list[str] = []
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        for table, columns in _ADDED_COLUMNS.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name in existing:
                    continue
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
                applied.append(f"{table}.{name}")

    if applied:
        logger.info("Colonnes ajoutées : %s", ", ".join(applied))
    return applied
