# filepath: backend/models.py
"""
SQLAlchemy ORM models.

Item 2: User model
Items 3-6 will add: OAuthToken, VideoHistory, PostingSchedule, etc.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True,
    )

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


class VideoRecord(Base):
    """A generated / uploaded video belonging to a user."""

    __tablename__ = "video_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
    )

    # ── Content ──────────────────────────────────────────────────────
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="Untitled")

    # ── Pipeline status: pending | generating | completed | failed | posted
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # ── File / upload info ───────────────────────────────────────────
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<VideoRecord {self.id} user={self.user_id} status={self.status}>"


class OAuthToken(Base):
    """Stored OAuth2 credentials for a user's connected provider (e.g. YouTube/Google).

    Each user can have at most one connection per provider.
    The refresh_token is encrypted at rest (handled at the application layer
    before writing; for now stored as-is — encryption TODO).
    """

    __tablename__ = "oauth_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_provider"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
    )

    # Provider identifier, e.g. "google" / "youtube"
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="google")

    # Google user info
    provider_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    provider_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    channel_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Tokens
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_type: Mapped[str] = mapped_column(String(20), nullable=False, default="Bearer")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Scopes granted (space-separated)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<OAuthToken {self.provider} user={self.user_id} channel={self.channel_id}>"


class UserApiKeys(Base):
    """Per-user API keys for external services (BYOK model).

    Users provide their own OpenAI, ElevenLabs, and Pexels keys.
    Keys are stored in the DB (encrypted at rest via DB-level encryption
    in production; application-layer encryption TODO).
    """

    __tablename__ = "user_api_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True,
    )

    # ── API Keys (stored as-is; encryption TODO) ─────────────────────
    openai_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    elevenlabs_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    elevenlabs_voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pexels_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<UserApiKeys user={self.user_id}>"


class PostingSchedule(Base):
    """A recurring automation schedule for a user.

    Users can queue up topics and set a posting frequency (e.g. daily, weekly).
    The scheduler worker picks up active schedules and triggers video generation
    when `next_run_at` is in the past.
    """

    __tablename__ = "posting_schedules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
    )

    # Human-readable label, e.g. "Daily Finance Shorts"
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="My Schedule")

    # ── Frequency ────────────────────────────────────────────────────
    # One of: daily, every_other_day, twice_weekly, weekly
    frequency: Mapped[str] = mapped_column(String(30), nullable=False, default="weekly")

    # Preferred hour (0-23, UTC) for the next run
    preferred_hour_utc: Mapped[int] = mapped_column(Integer, nullable=False, default=14)

    # ── Topic queue — JSON array of strings ──────────────────────────
    # e.g. '["compound interest", "index funds", "budgeting tips"]'
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Index into topics_json — cycles back to 0 when exhausted
    topic_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── State ────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<PostingSchedule {self.id} user={self.user_id} freq={self.frequency} active={self.is_active}>"
