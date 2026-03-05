"""create channels table

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-01 00:00:04.000000+00:00

Creates the ``channels`` table for multi-channel management (Feature 1).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False, server_default="youtube"),
        sa.Column("youtube_channel_id", sa.String(50), nullable=True),
        sa.Column("oauth_token_id", sa.String(36), sa.ForeignKey("oauth_tokens.id"), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "youtube_channel_id", name="uq_user_yt_channel"),
    )
    op.create_index("ix_channel_user", "channels", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_user", table_name="channels")
    op.drop_table("channels")
