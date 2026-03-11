"""add portrait_path and square_path to video_records

Revision ID: 0011
Revises: 0010
Create Date: 2025-01-01 00:00:11.000000+00:00

Adds ``portrait_path`` and ``square_path`` columns to ``video_records``
to store file paths for multi-format video exports (Shorts / Reels / TikTok).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("video_records") as batch_op:
        batch_op.add_column(sa.Column("portrait_path", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("square_path", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("video_records") as batch_op:
        batch_op.drop_column("square_path")
        batch_op.drop_column("portrait_path")
