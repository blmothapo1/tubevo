"""add channel_id FK to existing tables

Revision ID: 0005
Revises: 0004
Create Date: 2025-01-01 00:00:05.000000+00:00

Adds nullable ``channel_id`` foreign key to five existing tables:
video_records, posting_schedules, content_memory, user_preferences,
content_performance.  NULL = legacy / default channel.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES_WITH_INDEX = [
    "video_records",
    "posting_schedules",
    "content_memory",
    "content_performance",
]

_TABLES_WITHOUT_INDEX = [
    "user_preferences",
]


def upgrade() -> None:
    for table in _TABLES_WITH_INDEX:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "channel_id",
                    sa.String(36),
                    sa.ForeignKey("channels.id"),
                    nullable=True,
                ),
            )
            batch_op.create_index(f"ix_{table}_channel_id", ["channel_id"])

    for table in _TABLES_WITHOUT_INDEX:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "channel_id",
                    sa.String(36),
                    sa.ForeignKey("channels.id"),
                    nullable=True,
                ),
            )


def downgrade() -> None:
    for table in _TABLES_WITH_INDEX:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(f"ix_{table}_channel_id")
            batch_op.drop_column("channel_id")

    for table in _TABLES_WITHOUT_INDEX:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("channel_id")
