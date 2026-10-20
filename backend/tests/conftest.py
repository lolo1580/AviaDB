"""Fixtures partagées.

Les variables d'environnement sont positionnées **avant** l'import de
l'application, car `database.py` et `media.py` lisent leur configuration à
l'import. Chaque test repart d'une base et d'un dossier d'images vides.
"""

from __future__ import annotations

import io
import os
import random
import shutil
import tempfile

import pytest

TMP_DIR = tempfile.mkdtemp(prefix="aviadb-tests-")

# L'application est adossée à PostgreSQL : la suite s'exécute donc sur une vraie
# base. Par défaut celle du conteneur de test (port 55432, cf. README) ;
# l'intégration continue fournit la sienne via DATABASE_URL.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://aviadb:test@localhost:55432/aviadb_test"
)
os.environ.setdefault("UPLOAD_DIR", f"{TMP_DIR}/uploads")
# La suite gère son propre schéma (drop_all/create_all) : inutile de rejouer
# les migrations Alembic à chaque démarrage du client de test.
os.environ.setdefault("AVIADB_SKIP_MIGRATIONS", "1")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["ADMIN_USERNAME"] = "admin"
# Évite les blocages anti brute-force pendant les tests (testé explicitement ailleurs).
os.environ["ADMIN_MAX_FAILURES"] = "1000"

from fastapi.testclient import TestClient  # noqa: E402
from helpers import ADMIN_LOGIN  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app import auth, currency, media  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Interdit tout appel réseau réel depuis les tests.

    Les taux passent normalement par `currency._http_json` ; on le remplace par
    une erreur franche. Les tests qui simulent le fournisseur patchent une
    fonction de plus haut niveau (`fetch_current_rates`,
    `fetch_historical_per_eur`), donc ce garde-fou ne les gêne pas.
    """

    def _blocked(url):  # pragma: no cover - déclenché seulement en cas d'oubli
        raise AssertionError(f"appel réseau inattendu pendant les tests : {url}")

    monkeypatch.setattr(currency, "_http_json", _blocked)
    yield


@pytest.fixture(autouse=True)
def clean_state():
    """Base vide + dossier d'images vide + compte admin initial."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    auth.reset_failures()
    with SessionLocal() as db:
        auth.bootstrap_admin(db)
    shutil.rmtree(media.UPLOAD_DIR, ignore_errors=True)
    media.ensure_upload_dir()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_client(client):
    """Client authentifié avec le rôle ADMIN."""
    response = client.post("/api/admin/login", json=ADMIN_LOGIN)
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def create_item(admin_client):
    """Crée un objet via l'API et renvoie sa représentation."""

    def _create(**overrides):
        payload = {"name": "Objet", "item_type": "DIECAST", "status": "STORED_BOX"}
        payload.update(overrides)
        response = admin_client.post("/api/items", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _create


@pytest.fixture
def png_bytes():
    """Petite image PNG valide, en mémoire.

    `seed` dessine un motif déterministe (pour obtenir des images distinctes) et
    `brightness` décale la luminosité (pour fabriquer un quasi-doublon).
    """

    def _png(size=(2400, 1800), color=(30, 90, 200), seed=None, brightness=0):
        image = Image.new("RGB", size, color)
        if seed is not None:
            draw = ImageDraw.Draw(image)
            rng = random.Random(seed)
            width = max(2, size[0] // 6)
            height = max(2, size[1] // 6)
            for _ in range(12):
                x0 = rng.randrange(0, max(1, size[0] - width))
                y0 = rng.randrange(0, max(1, size[1] - height))
                shade = tuple((channel + rng.randrange(128)) % 256 for channel in color)
                draw.rectangle([x0, y0, x0 + width, y0 + height], fill=shade)
        if brightness:
            image = Image.eval(image, lambda value: min(255, value + brightness))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    return _png


@pytest.fixture
def upload_photo(admin_client, png_bytes):
    """Téléverse une image sur un objet.

    La couleur varie à chaque appel : deux uploads de test ne sont donc pas
    considérés comme des doublons (le dédoublonnage est testé séparément).
    """
    counter = {"n": 0}

    def _upload(item_id, caption=None, size=(1200, 900)):
        counter["n"] += 1
        color = ((counter["n"] * 37) % 256, 90, 200)
        data = {"caption": caption} if caption else {}
        response = admin_client.post(
            f"/api/items/{item_id}/photos",
            files={
                "file": (
                    "photo.png",
                    png_bytes(size=size, color=color, seed=counter["n"]),
                    "image/png",
                )
            },
            data=data,
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _upload
