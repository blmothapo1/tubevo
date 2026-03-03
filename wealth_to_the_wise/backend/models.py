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
    is_beta: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Role (admin support) ─────────────────────────────────────────
    role: Mapped[str] = mapped_column(String(20), default="user")

    # ── Billing / plan (Item 6 will expand) ──────────────────────────
    plan: Mapped[str] = mapped_column(String(20), default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True,
    )
    credit_balance: Mapped[int] = mapped_column(Integer, default=0)

    # ── Password-reset token ─────────────────────────────────────────
    reset_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_token_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Login tracking ───────────────────────────────────────────────
    last_login_at: Mapped[datetime | None] = mapped_column(
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

    # ── Pipeline progress (Phase 6 — UX polish) ─────────────────────
    progress_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Admin-visible artefacts ──────────────────────────────────────
    script_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pipeline_log_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Phase 5 — Subtitle artefacts ─────────────────────────────────
    srt_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Analytics — when the video was published to YouTube ──────────
    published_at: Mapped[datetime | None] = mapped_column(
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

    # ── Phase 4 & 5 — Video production preferences ──────────────────
    subtitle_style: Mapped[str] = mapped_column(String(30), nullable=False, default="bold_pop")
    burn_captions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    speech_speed: Mapped[str | None] = mapped_column(String(10), nullable=True)  # e.g. "1.0"

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


class ContentMemory(Base):
    """Phase 7 — Content Memory: stores fingerprints of past video topics
    so the AI can avoid repeating the same hooks, angles, and structures.

    Each row = one generated video's content fingerprint.
    Queried at the start of each pipeline run to build avoidance prompts.
    """

    __tablename__ = "content_memory"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
    )

    # The topic string used for generation
    topic: Mapped[str] = mapped_column(String(300), nullable=False)

    # SHA-256 fingerprint of the normalised topic (for dedup lookups)
    topic_fingerprint: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # The final video title (used in avoidance prompts)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    # The script temperature used (for analytics/debugging)
    temperature_used: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # The music mood label (for analytics/debugging)
    music_mood: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<ContentMemory user={self.user_id} topic='{self.topic[:40]}' fp={self.topic_fingerprint}>"


class UserPreferences(Base):
    """Per-user channel preferences collected during onboarding.

    Persists niche selection, tone/style, target audience, and channel goal
    so the AI pipeline can generate content tailored to each user's channel
    instead of using a hardcoded persona.
    """

    __tablename__ = "user_preferences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True,
    )

    # ── Channel identity ─────────────────────────────────────────────
    # JSON array of niche strings, e.g. '["Personal Finance","Investing / Stocks"]'
    niches_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Free-text tone descriptor, e.g. "confident, no-fluff educator"
    tone_style: Mapped[str] = mapped_column(
        String(300), nullable=False,
        default="confident, direct, no-fluff educator",
    )

    # Target audience descriptor, e.g. "young professionals 25-35"
    target_audience: Mapped[str] = mapped_column(
        String(300), nullable=False,
        default="general audience",
    )

    # Channel goal: growth | monetization | authority | entertainment
    channel_goal: Mapped[str] = mapped_column(
        String(30), nullable=False, default="growth",
    )

    # Posting frequency: daily | every_2_days | weekly
    posting_frequency: Mapped[str] = mapped_column(
        String(30), nullable=False, default="weekly",
    )

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<UserPreferences user={self.user_id} goal={self.channel_goal}>"


class ContentPerformance(Base):
    """Track performance of generated content for weighted preference learning.

    Stores which title variant and thumbnail concept were used, along with
    early engagement signals so the system can learn which styles work best
    for each user's audience.
    """

    __tablename__ = "content_performance"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
    )
    video_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("video_records.id"), nullable=False, index=True,
    )

    # ── What was used ────────────────────────────────────────────────
    title_variant_used: Mapped[str | None] = mapped_column(String(300), nullable=True)
    thumbnail_concept_used: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Title style category: curiosity | direct_benefit | contrarian | question | data_driven
    title_style_used: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Hook mode used for this generation: conservative | balanced | aggressive
    hook_mode_used: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Engagement signals (updated asynchronously) ──────────────────
    views_48h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    likes_48h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_48h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ctr_pct: Mapped[str | None] = mapped_column(String(10), nullable=True)  # e.g. "4.2"
    avg_view_duration_pct: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Composite engagement score (0-100, computed by the system)
    engagement_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Analytics ingestion timestamp ────────────────────────────────
    # Set when the analytics worker fetches real YouTube metrics.
    # NULL = metrics not yet fetched (eligible for ingestion).
    metrics_fetched_at: Mapped[datetime | None] = mapped_column(
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
        return f"<ContentPerformance user={self.user_id} video={self.video_record_id} score={self.engagement_score}>"


class WaitlistSignup(Base):
    """Landing-page waitlist email capture.

    Emails are always persisted here first, then optionally synced to Kit
    (ConvertKit).  This ensures no leads are lost even if the Kit API is
    down or the key is invalid.
    """

    __tablename__ = "waitlist_signups"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True,
    )
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Kit sync state: pending | synced | failed
    kit_sync_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
    )
    kit_subscriber_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<WaitlistSignup {self.email} kit={self.kit_sync_status}>"


class AdminEvent(Base):
    """Lightweight event log for the admin activity feed.

    Event types:
      user_signup, video_started, video_completed, video_failed,
      upload_success, upload_failed
    """

    __tablename__ = "admin_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True,
    )
    video_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("video_records.id"), nullable=True,
    )
    # Arbitrary JSON payload (user email, error message, etc.)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )

    def __repr__(self) -> str:
        return f"<AdminEvent {self.type} user={self.user_id} at={self.created_at}>"


class AdminAuditLog(Base):
    """Immutable audit trail for every admin action.

    Rows are INSERT-only — never updated or deleted.
    """

    __tablename__ = "admin_audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    # The admin who performed the action
    admin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
    )
    # The user who was the target of the action (if applicable)
    target_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True,
    )
    # Action performed: change_role, grant_credits, disable_user, enable_user
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # JSON details: {"old_role": "user", "new_role": "admin"} etc.
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )

    def __repr__(self) -> str:
        return f"<AdminAuditLog admin={self.admin_id} action={self.action} target={self.target_user_id}>"


class PlatformError(Base):
    """Centralised error log for pipeline failures, API errors, and system issues.

    Provides a single table admins can browse, filter, resolve, and link
    back to users/videos.
    """

    __tablename__ = "platform_errors"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True,
    )
    video_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("video_records.id"), nullable=True, index=True,
    )

    # Category: pipeline | upload | auth | api | system
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    # Human-readable one-liner (first 500 chars of the exception message)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Full stack trace (sanitised — no API keys)
    stack: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Admin triage
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )

    def __repr__(self) -> str:
        return f"<PlatformError {self.type} resolved={self.resolved} at={self.created_at}>"
