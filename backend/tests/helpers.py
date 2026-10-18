"""Constantes et petites fonctions partagées par les tests."""

from __future__ import annotations

SETTINGS_URL = "/api/meta/settings"
BASE_URL = "/api/admin/settings"
RATES_URL = "/api/admin/rates"
REFRESH_URL = "/api/admin/rates/refresh"
BACKUP_URL = "/api/admin/backup"
RESTORE_URL = "/api/admin/restore"

ADMIN_LOGIN = {"username": "admin", "password": "test-password"}


def set_rates(client, rates):
    """Fixe les taux courants (convention BCE : 1 EUR = X)."""
    response = client.put(RATES_URL, json={"rates": rates})
    assert response.status_code == 200, response.text
    return response.json()


def restore(client, archive: bytes, mode: str = "merge"):
    """Restaure une archive ZIP de sauvegarde."""
    return client.post(
        RESTORE_URL,
        files={"file": ("backup.zip", archive, "application/zip")},
        data={"mode": mode},
    )
