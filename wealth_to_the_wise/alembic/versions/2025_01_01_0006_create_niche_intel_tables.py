"""create niche intelligence tables

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-01 00:00:06.000000+00:00

Creates ``niche_snapshots`` and ``niche_topics`` tables for the Niche
Intelligence Engine (Feature 2).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "niche_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("niche", sa.String(200), nullable=False),
        sa.Column("snapshot_date", sa.String(10), nullable=False),
        sa.Column("saturation_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trending_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_volume_est", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("competitor_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("channel_id", "niche", "snapshot_date", name="uq_niche_snap"),
    )
    op.create_index("ix_niche_snapshots_channel_id", "niche_snapshots", ["channel_id"])

    op.create_table(
        "niche_topics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("niche_snapshots.id"), nullable=False),
        sa.Column("topic", sa.String(300), nullable=False),
        sa.Column("estimated_demand", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("competition_level", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("source", sa.String(30), nullable=False, server_default="youtube_search"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_niche_topics_snapshot_id", "niche_topics", ["snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_niche_topics_snapshot_id", table_name="niche_topics")
    op.drop_table("niche_topics")
    op.drop_index("ix_niche_snapshots_channel_id", table_name="niche_snapshots")
    op.drop_table("niche_snapshots")
