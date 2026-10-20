"""Ajoute l'empreinte perceptuelle des photos (dédoublonnage global).

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "item_photos", sa.Column("perceptual_hash", sa.String(length=16), nullable=True)
    )
    op.create_index(
        op.f("ix_item_photos_perceptual_hash"),
        "item_photos",
        ["perceptual_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_item_photos_perceptual_hash"), table_name="item_photos")
    op.drop_column("item_photos", "perceptual_hash")
