# filepath: backend/models.py
"""
SQLAlchemy ORM models.

Item 2: User model
Items 3-6 will add: OAuthToken, VideoHistory, PostingSchedule, etc.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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

    # ── Empire OS feature flags (Phase 0) ────────────────────────────
    # JSON dict of per-user flag overrides, e.g. {"empire.multi_channel": true}
    feature_overrides_json: Mapped[str | None] = mapped_column(
        Text, nullable=True,
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
    __table_args__ = (
        # Composite index for the hot quota query:
        #   SELECT count(*) WHERE user_id = ? AND created_at >= ? AND status NOT IN (?)
        # Also speeds up history listing and stale-job sweeps.
        Index("ix_video_user_created_status", "user_id", "created_at", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
    )

    # ── Empire OS: multi-channel (Phase 0) ───────────────────────────
    # NULL = legacy / default channel (backward-compat)
    channel_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True, index=True,
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

    # ── Error classification (Phase 2 — typed pipeline errors) ───────
    # One of: api_quota, api_auth, external_service, render, upload, timeout, unknown
    error_category: Mapped[str | None] = mapped_column(String(30), nullable=True)

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
    Tokens are encrypted at rest via Fernet (see ``backend.encryption``).
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
    Keys are encrypted at rest via Fernet (see ``backend.encryption``).
    """

    __tablename__ = "user_api_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True,
    )

    # ── API Keys (encrypted via Fernet before storage) ────────────────
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

    # ── Empire OS: multi-channel (Phase 0) ───────────────────────────
    channel_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True, index=True,
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

    # ── Empire OS: multi-channel (Phase 0) ───────────────────────────
    channel_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True, index=True,
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

    # ── Empire OS: multi-channel (Phase 0) ───────────────────────────
    # NULL = legacy / default channel preferences
    channel_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True,
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

    # ── Empire OS: multi-channel (Phase 0) ───────────────────────────
    channel_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True, index=True,
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


# ══════════════════════════════════════════════════════════════════════
# EMPIRE OS — New tables (Phase 0 scaffolding)
#
# All tables below are created by Alembic migrations 0003-0009.
# They are fully isolated — no existing table is dropped or renamed.
# ══════════════════════════════════════════════════════════════════════


class Channel(Base):
    """A YouTube channel managed by a user (Feature 1: Multi-Channel).

    Users can have multiple channels, each connected to a different
    YouTube account.  The ``is_default`` flag marks the channel used
    when no explicit channel_id is provided in API calls.
    """

    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("user_id", "youtube_channel_id", name="uq_user_yt_channel"),
        Index("ix_channel_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="youtube")

    # YouTube channel identity (nullable until connected)
    youtube_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Link to the OAuth token used for this channel
    oauth_token_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("oauth_tokens.id"), nullable=True,
    )

    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<Channel {self.name} user={self.user_id} yt={self.youtube_channel_id}>"


class NicheSnapshot(Base):
    """Periodic snapshot of niche health metrics (Feature 2: Niche Intel).

    One row per (channel, niche, date) — populated by the niche worker.
    """

    __tablename__ = "niche_snapshots"
    __table_args__ = (
        UniqueConstraint("channel_id", "niche", "snapshot_date", name="uq_niche_snap"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=False, index=True,
    )
    niche: Mapped[str] = mapped_column(String(200), nullable=False)
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD

    saturation_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trending_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    search_volume_est: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    competitor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Raw API response cache (JSON)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<NicheSnapshot {self.niche} date={self.snapshot_date} channel={self.channel_id}>"


class NicheTopic(Base):
    """Individual topic discovered during niche analysis (Feature 2)."""

    __tablename__ = "niche_topics"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("niche_snapshots.id"), nullable=False, index=True,
    )
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    estimated_demand: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    competition_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium",
    )
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="youtube_search",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<NicheTopic '{self.topic[:40]}' demand={self.estimated_demand}>"


class RevenueEvent(Base):
    """A single revenue event attributed to a channel/video (Feature 3).

    Dedup via UniqueConstraint on (source, external_id).
    """

    __tablename__ = "revenue_events"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_revenue_dedup"),
        Index("ix_revenue_channel_date", "channel_id", "event_date"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=False,
    )
    video_record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("video_records.id"), nullable=True, index=True,
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    event_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<RevenueEvent {self.source} ${self.amount_cents/100:.2f} channel={self.channel_id}>"


class RevenueDailyAgg(Base):
    """Daily revenue aggregation per channel (Feature 3)."""

    __tablename__ = "revenue_daily_agg"
    __table_args__ = (
        UniqueConstraint("channel_id", "agg_date", name="uq_rev_agg_date"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=False, index=True,
    )
    agg_date: Mapped[str] = mapped_column(String(10), nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    adsense_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affiliate_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stripe_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<RevenueDailyAgg {self.agg_date} ${self.total_cents/100:.2f} channel={self.channel_id}>"


class ThumbExperiment(Base):
    """A thumbnail A/B test for a specific video (Feature 4)."""

    __tablename__ = "thumb_experiments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=False, index=True,
    )
    video_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("video_records.id"), nullable=False, unique=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    concluded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    winner_variant_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
    )
    rotation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<ThumbExperiment {self.id[:8]} status={self.status} video={self.video_record_id}>"


class ThumbVariant(Base):
    """A single thumbnail variant within an A/B experiment (Feature 4)."""

    __tablename__ = "thumb_variants"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    experiment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("thumb_experiments.id"), nullable=False, index=True,
    )
    concept: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ctr_pct: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deployed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<ThumbVariant {self.concept} exp={self.experiment_id[:8]} active={self.is_active}>"


class CompetitorChannel(Base):
    """A competitor channel being tracked (Feature 5: Spy Mode)."""

    __tablename__ = "competitor_channels"
    __table_args__ = (
        UniqueConstraint("channel_id", "youtube_channel_id", name="uq_comp_yt_channel"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=False, index=True,
    )
    youtube_channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    subscriber_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<CompetitorChannel {self.name} yt={self.youtube_channel_id}>"


class CompetitorSnapshot(Base):
    """Point-in-time snapshot of competitor channel metrics (Feature 5)."""

    __tablename__ = "competitor_snapshots"
    __table_args__ = (
        UniqueConstraint("competitor_id", "snapshot_date", name="uq_comp_snap_date"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    competitor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("competitor_channels.id"), nullable=False, index=True,
    )
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False)

    subscriber_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recent_videos_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    avg_views_per_video: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<CompetitorSnapshot comp={self.competitor_id[:8]} date={self.snapshot_date}>"


class TrendAlert(Base):
    """Detected trend + auto-generated video ready for one-tap publish.

    Lifecycle: detected → scanning → generating → ready → published | dismissed | failed
    """

    __tablename__ = "trend_alerts"
    __table_args__ = (
        Index("ix_trend_user_status", "user_id", "status"),
        Index("ix_trend_channel_created", "channel_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
    )
    channel_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True, index=True,
    )

    # ── Trend info ───────────────────────────────────────────────────
    trend_topic: Mapped[str] = mapped_column(String(300), nullable=False)
    trend_source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="niche_analysis",
    )  # niche_analysis | google_trends | competitor_gap | youtube_trending
    confidence_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50,
    )  # 0-100
    estimated_demand: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5,
    )  # 1-10
    competition_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium",
    )  # low | medium | high
    niche: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Generated video reference ────────────────────────────────────
    video_record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("video_records.id"), nullable=True, index=True,
    )

    # ── Generated title / script preview ─────────────────────────────
    generated_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    script_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Status: detected | scanning | generating | ready | published | dismissed | failed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="detected", index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Autopilot ────────────────────────────────────────────────────
    auto_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Timestamps ───────────────────────────────────────────────────
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    generation_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<TrendAlert '{self.trend_topic[:40]}' status={self.status} confidence={self.confidence_score}>"


class TrendRadarSettings(Base):
    """Per-user Trend Radar configuration."""

    __tablename__ = "trend_radar_settings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False, index=True,
    )

    # Master toggle
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Autopilot: auto-publish when confidence >= threshold
    autopilot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    autopilot_min_confidence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=80,
    )  # 0-100
    autopilot_daily_cap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )  # max auto-publishes per day

    # Scan frequency in minutes
    scan_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=360,
    )  # 6 hours default

    # Minimum confidence to show in queue
    min_confidence_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=40,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<TrendRadarSettings user={self.user_id} enabled={self.is_enabled} autopilot={self.autopilot_enabled}>"


class VoiceClone(Base):
    """A cloned voice created via ElevenLabs (Feature 6).

    Lifecycle: pending → processing → ready (or failed) → deleted
    """

    __tablename__ = "voice_clones"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Populated after ElevenLabs clone creation completes
    elevenlabs_voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # pending | processing | ready | failed | deleted
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    # Object storage key for the uploaded audio sample
    sample_file_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_duration_secs: Mapped[int | None] = mapped_column(Integer, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    labels_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )

    def __repr__(self) -> str:
        return f"<VoiceClone {self.name} status={self.status} user={self.user_id}>"
