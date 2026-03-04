"""baseline: stamp existing schema

Revision ID: 0001
Revises: None
Create Date: 2025-01-01 00:00:00.000000+00:00

This is an empty baseline migration.  It tells Alembic that the
current state of the database already matches the ORM models (all
13 tables + the hand-rolled ALTER TABLE columns).

Existing deployments should run:
    alembic stamp 0001
to mark themselves at this revision without re-running CREATE TABLE.

Fresh deployments will have the schema created by create_all() + this
stamp, so subsequent migrations apply cleanly.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline — nothing to do.  The schema already exists.
    pass


def downgrade() -> None:
    # Cannot downgrade from baseline.
    pass
