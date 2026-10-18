"""Engine SQLAlchemy, session factory et Base déclarative.

La base vit dans un fichier SQLite (`data/aviadb.db` par défaut), monté en
volume Docker. L'URL est surchargeable via la variable d'environnement
`DATABASE_URL`.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, event, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/aviadb.db")

# SQLite + FastAPI : les connexions traversent plusieurs threads.
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    _engine_options = {}
else:
    _connect_args = {}
    # Évite les connexions mortes quand le serveur PostgreSQL a redémarré.
    _engine_options = {"pool_pre_ping": True, "pool_recycle": 1800}

engine = create_engine(
    DATABASE_URL, connect_args=_connect_args, future=True, **_engine_options
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def is_sqlite() -> bool:
    return engine.dialect.name == "sqlite"


def year_expression(column):
    """Extrait l'année d'une colonne date, selon le dialecte SQL.

    SQLite n'a pas `to_char` ; PostgreSQL n'a pas `strftime`.
    """
    if engine.dialect.name == "postgresql":
        return func.to_char(column, "YYYY")
    return func.strftime("%Y", column)


class Base(DeclarativeBase):
    """Base déclarative commune à tous les modèles."""


if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
        """SQLite n'applique pas les clés étrangères par défaut."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db():
    """Dépendance FastAPI : une session par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
