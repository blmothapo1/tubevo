"""add error_category to video_records

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:01.000000+00:00

Adds the ``error_category`` column to ``video_records`` so the pipeline
can store structured error types (api_quota, api_auth, external_service,
render, upload, timeout, unknown) instead of just free-text messages.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use batch mode for SQLite compatibility.
    with op.batch_alter_table("video_records", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("error_category", sa.String(30), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("video_records", schema=None) as batch_op:
        batch_op.drop_column("error_category")
