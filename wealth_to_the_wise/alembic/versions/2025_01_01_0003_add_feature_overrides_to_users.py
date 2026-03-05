"""add feature_overrides_json to users

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-01 00:00:03.000000+00:00

Adds the ``feature_overrides_json`` column to ``users`` so per-user
feature flag overrides can be stored as a JSON string.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("feature_overrides_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("feature_overrides_json")
