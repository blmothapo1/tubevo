"""create competitor monitoring and voice clone tables

Revision ID: 0009
Revises: 0008
Create Date: 2025-01-01 00:00:09.000000+00:00

Creates ``competitor_channels``, ``competitor_snapshots`` (Feature 5)
and ``voice_clones`` (Feature 6) tables.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Feature 5: Competitor Monitoring ──
    op.create_table(
        "competitor_channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("youtube_channel_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("subscriber_count", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("channel_id", "youtube_channel_id", name="uq_comp_yt_channel"),
    )
    op.create_index("ix_competitor_channels_channel_id", "competitor_channels", ["channel_id"])

    op.create_table(
        "competitor_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("competitor_id", sa.String(36), sa.ForeignKey("competitor_channels.id"), nullable=False),
        sa.Column("snapshot_date", sa.String(10), nullable=False),
        sa.Column("subscriber_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recent_videos_json", sa.Text(), nullable=True),
        sa.Column("avg_views_per_video", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_tags_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("competitor_id", "snapshot_date", name="uq_comp_snap_date"),
    )
    op.create_index("ix_competitor_snapshots_competitor_id", "competitor_snapshots", ["competitor_id"])

    # ── Feature 6: Voice Cloning ──
    op.create_table(
        "voice_clones",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("elevenlabs_voice_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("sample_file_key", sa.Text(), nullable=True),
        sa.Column("sample_duration_secs", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("labels_json", sa.Text(), nullable=True),
        sa.Column("preview_url", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_clones_user_id", "voice_clones", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_clones_user_id", table_name="voice_clones")
    op.drop_table("voice_clones")
    op.drop_index("ix_competitor_snapshots_competitor_id", table_name="competitor_snapshots")
    op.drop_table("competitor_snapshots")
    op.drop_index("ix_competitor_channels_channel_id", table_name="competitor_channels")
    op.drop_table("competitor_channels")
