"""Engine SQLAlchemy (PostgreSQL), session factory et Base déclarative.

L'application est adossée à PostgreSQL. L'URL est fournie par la variable
d'environnement `DATABASE_URL` (voir `.env.example`) ; la valeur par défaut
correspond au conteneur `db` de `docker-compose.yml`, publié sur le port 5434.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://aviadb:change-me@localhost:5434/aviadb",
)

engine = create_engine(
    DATABASE_URL,
    future=True,
    # Évite les connexions mortes après un redémarrage du serveur PostgreSQL.
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Base déclarative commune à tous les modèles."""


def get_db():
    """Dépendance FastAPI : une session par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
