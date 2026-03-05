"""create thumbnail A/B experiment tables

Revision ID: 0008
Revises: 0007
Create Date: 2025-01-01 00:00:08.000000+00:00

Creates ``thumb_experiments`` and ``thumb_variants`` tables for Auto
Thumbnail A/B Testing (Feature 4).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "thumb_experiments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("video_record_id", sa.String(36), sa.ForeignKey("video_records.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winner_variant_id", sa.String(36), nullable=True),
        sa.Column("rotation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_thumb_experiments_channel_id", "thumb_experiments", ["channel_id"])

    op.create_table(
        "thumb_variants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experiment_id", sa.String(36), sa.ForeignKey("thumb_experiments.id"), nullable=False),
        sa.Column("concept", sa.String(50), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ctr_pct", sa.String(10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_thumb_variants_experiment_id", "thumb_variants", ["experiment_id"])


def downgrade() -> None:
    op.drop_index("ix_thumb_variants_experiment_id", table_name="thumb_variants")
    op.drop_table("thumb_variants")
    op.drop_index("ix_thumb_experiments_channel_id", table_name="thumb_experiments")
    op.drop_table("thumb_experiments")
