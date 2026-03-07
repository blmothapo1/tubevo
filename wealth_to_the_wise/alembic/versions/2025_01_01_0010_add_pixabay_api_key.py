"""add pixabay_api_key to user_api_keys

Revision ID: 0010
Revises: 0009
Create Date: 2025-01-01 00:00:10.000000+00:00

Adds ``pixabay_api_key`` column to the ``user_api_keys`` table to support
dual-provider stock footage (Pexels primary, Pixabay fallback).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable TEXT column — encrypted Pixabay API key (Fernet)
    with op.batch_alter_table("user_api_keys") as batch_op:
        batch_op.add_column(sa.Column("pixabay_api_key", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_api_keys") as batch_op:
        batch_op.drop_column("pixabay_api_key")
