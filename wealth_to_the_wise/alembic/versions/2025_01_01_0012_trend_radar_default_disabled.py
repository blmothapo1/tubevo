"""change trend_radar_settings.is_enabled default to false (opt-in)

Revision ID: 0012
Revises: 0011
Create Date: 2025-01-01 00:00:12.000000+00:00

Trend Radar should be opt-in — users must explicitly enable it in the UI.
Previously it defaulted to True which caused auto-generation for all users.

This migration:
1. Changes the column default from True to False
2. Flips all existing rows to is_enabled=False (they were auto-created, not user-chosen)
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Flip all existing auto-created rows to disabled
    op.execute(
        "UPDATE trend_radar_settings SET is_enabled = false"
    )

    # 2. Change column default
    with op.batch_alter_table("trend_radar_settings") as batch_op:
        batch_op.alter_column(
            "is_enabled",
            server_default=sa.text("false"),
        )


def downgrade() -> None:
    with op.batch_alter_table("trend_radar_settings") as batch_op:
        batch_op.alter_column(
            "is_enabled",
            server_default=sa.text("true"),
        )
