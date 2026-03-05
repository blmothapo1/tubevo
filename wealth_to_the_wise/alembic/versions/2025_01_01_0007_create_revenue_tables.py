"""create revenue attribution tables

Revision ID: 0007
Revises: 0006
Create Date: 2025-01-01 00:00:07.000000+00:00

Creates ``revenue_events`` and ``revenue_daily_agg`` tables for Revenue
Attribution (Feature 3).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revenue_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("video_record_id", sa.String(36), sa.ForeignKey("video_records.id"), nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("event_date", sa.String(10), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source", "external_id", name="uq_revenue_dedup"),
    )
    op.create_index("ix_revenue_channel_date", "revenue_events", ["channel_id", "event_date"])
    op.create_index("ix_revenue_events_video_record_id", "revenue_events", ["video_record_id"])

    op.create_table(
        "revenue_daily_agg",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("agg_date", sa.String(10), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("adsense_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("affiliate_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stripe_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("channel_id", "agg_date", name="uq_rev_agg_date"),
    )
    op.create_index("ix_revenue_daily_agg_channel_id", "revenue_daily_agg", ["channel_id"])


def downgrade() -> None:
    op.drop_index("ix_revenue_daily_agg_channel_id", table_name="revenue_daily_agg")
    op.drop_table("revenue_daily_agg")
    op.drop_index("ix_revenue_events_video_record_id", table_name="revenue_events")
    op.drop_index("ix_revenue_channel_date", table_name="revenue_events")
    op.drop_table("revenue_events")
