"""program official domain aliases

Revision ID: 20260903_0003
Revises: 20260902_0002
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260903_0003"
down_revision = "20260902_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "programs",
        sa.Column(
            "official_domain_aliases",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("programs", "official_domain_aliases")
