# filepath: backend/models.py
"""
SQLAlchemy ORM models.

Item 2: User model
Items 3-6 will add: OAuthToken, VideoHistory, PostingSchedule, etc.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """Registered user account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(128), nullable=False,
    )
    full_name: Mapped[str | None] = mapped_column(
        String(120), nullable=True,
    )

    # ── Account state ────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Billing / plan (Item 6 will expand) ──────────────────────────
    plan: Mapped[str] = mapped_column(String(20), default="free")

    # ── Password-reset token ─────────────────────────────────────────
    reset_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_token_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<User {self.email} plan={self.plan}>"
