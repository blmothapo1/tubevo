# filepath: backend/schemas.py
"""
Pydantic schemas for request/response validation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Generic ──────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error envelope returned by all endpoints."""
    detail: str


class HealthResponse(BaseModel):
    """Response from GET /health."""
    status: str = "ok"
    version: str
    environment: str


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str


# ── Auth: Sign-up ────────────────────────────────────────────────────

class SignUpRequest(BaseModel):
    """POST /auth/signup body."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(None, max_length=120)


class SignUpResponse(BaseModel):
    """Returned after successful registration."""
    id: str
    email: str
    full_name: str | None
    plan: str
    message: str = "Account created successfully."


# ── Auth: Login ──────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """POST /auth/login body (JSON alternative to OAuth2 form)."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Returned on successful login or token refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ── Auth: Token refresh ─────────────────────────────────────────────

class RefreshRequest(BaseModel):
    """POST /auth/refresh body."""
    refresh_token: str


# ── Auth: User profile ──────────────────────────────────────────────

class UserProfile(BaseModel):
    """Returned by GET /auth/me."""
    id: str
    email: str
    full_name: str | None
    plan: str
    role: str = "user"
    is_active: bool
    is_verified: bool
    is_beta: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    """PATCH /auth/me body."""
    full_name: str | None = Field(None, max_length=120)


# ── Auth: Forgot / Reset password ───────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    """POST /auth/forgot-password body."""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """POST /auth/reset-password body."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


# ── YouTube / Google OAuth ───────────────────────────────────────────

class YouTubeAuthURLResponse(BaseModel):
    """Returned by GET /oauth/youtube/authorize."""
    auth_url: str


class YouTubeCallbackRequest(BaseModel):
    """POST /oauth/youtube/callback body — sent by the frontend after Google redirects back."""
    code: str
    state: str | None = None


class YouTubeConnectionResponse(BaseModel):
    """Current YouTube connection status."""
    connected: bool
    provider_email: str | None = None
    channel_title: str | None = None
    channel_id: str | None = None
    scopes: str | None = None
    connected_at: datetime | None = None


# ── Apple OAuth ─────────────────────────────────────────────────────

class AppleLoginRequest(BaseModel):
    code: str


# ── User API Keys (BYOK) ────────────────────────────────────────────

class UserApiKeysResponse(BaseModel):
    """Returned by GET /api/keys — masks secret keys for display."""
    has_openai_key: bool
    has_elevenlabs_key: bool
    has_pexels_key: bool
    elevenlabs_voice_id: str | None = None
    # Show last 4 chars so user knows which key is saved
    openai_key_hint: str | None = None
    elevenlabs_key_hint: str | None = None
    pexels_key_hint: str | None = None


class UpdateApiKeysRequest(BaseModel):
    """PUT /api/keys body — any field left None is not changed.

    Basic format validation prevents users from accidentally saving
    garbage strings.  Send an empty string ``""`` to clear a key.
    """
    openai_api_key: str | None = Field(None, max_length=200)
    elevenlabs_api_key: str | None = Field(None, max_length=200)
    elevenlabs_voice_id: str | None = Field(None, max_length=100)
    pexels_api_key: str | None = Field(None, max_length=200)

    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_key(cls, v: str | None) -> str | None:
        if v is not None and v != "":
            # OpenAI keys start with "sk-" and are 20+ chars
            if not v.startswith("sk-") or len(v) < 20:
                raise ValueError(
                    "OpenAI API key should start with 'sk-' and be at least 20 characters."
                )
        return v

    @field_validator("elevenlabs_api_key")
    @classmethod
    def validate_elevenlabs_key(cls, v: str | None) -> str | None:
        if v is not None and v != "":
            # ElevenLabs keys are hex-like, at least 20 chars
            if len(v) < 20:
                raise ValueError(
                    "ElevenLabs API key should be at least 20 characters."
                )
        return v

    @field_validator("pexels_api_key")
    @classmethod
    def validate_pexels_key(cls, v: str | None) -> str | None:
        if v is not None and v != "":
            # Pexels keys are alphanumeric, at least 20 chars
            if len(v) < 20:
                raise ValueError(
                    "Pexels API key should be at least 20 characters."
                )
        return v


# ── User Preferences (Channel Intelligence) ─────────────────────────

class UserPreferencesRequest(BaseModel):
    """PUT /api/preferences body — onboarding + settings."""
    niches: list[str] = Field(default_factory=list, max_length=15)
    tone_style: str = Field("confident, direct, no-fluff educator", max_length=300)
    target_audience: str = Field("general audience", max_length=300)
    channel_goal: str = Field("growth", pattern=r"^(growth|monetization|authority|entertainment)$")
    posting_frequency: str = Field("weekly", pattern=r"^(daily|every_2_days|weekly)$")


class UserPreferencesResponse(BaseModel):
    """GET /api/preferences response."""
    niches: list[str] = []
    tone_style: str = "confident, direct, no-fluff educator"
    target_audience: str = "general audience"
    channel_goal: str = "growth"
    posting_frequency: str = "weekly"
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ContentPerformanceResponse(BaseModel):
    """GET /api/videos/{id}/performance response."""
    video_record_id: str
    title_variant_used: str | None = None
    thumbnail_concept_used: str | None = None
    views_48h: int = 0
    likes_48h: int = 0
    comments_48h: int = 0
    ctr_pct: str | None = None
    avg_view_duration_pct: str | None = None
    engagement_score: int = 0


# ══════════════════════════════════════════════════════════════════════
# Empire OS — Channel Management (Feature 1)
# ══════════════════════════════════════════════════════════════════════


class ChannelCreateRequest(BaseModel):
    """POST /channels body."""
    name: str = Field(..., min_length=1, max_length=200)
    platform: str = Field("youtube", pattern=r"^(youtube)$")

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class ChannelUpdateRequest(BaseModel):
    """PATCH /channels/{id} body."""
    name: str | None = Field(None, min_length=1, max_length=200)
    is_default: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if v else v


class ChannelResponse(BaseModel):
    """Single channel in list/detail responses."""
    id: str
    name: str
    platform: str
    youtube_channel_id: str | None = None
    oauth_token_id: str | None = None
    is_default: bool
    youtube_connected: bool = False
    channel_title: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChannelListResponse(BaseModel):
    """GET /channels response."""
    channels: list[ChannelResponse]
    count: int


# ══════════════════════════════════════════════════════════════════════
# Empire OS — Niche Intelligence (Feature 2)
# ══════════════════════════════════════════════════════════════════════


class NicheScanRequest(BaseModel):
    """POST /niche/scan body."""
    niche: str = Field(..., min_length=2, max_length=200)

    @field_validator("niche")
    @classmethod
    def strip_niche(cls, v: str) -> str:
        return v.strip()


class NicheTopicResponse(BaseModel):
    """A single topic suggestion within a snapshot."""
    id: str
    topic: str
    estimated_demand: int
    competition_level: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NicheSnapshotResponse(BaseModel):
    """A niche analysis snapshot."""
    id: str
    channel_id: str
    niche: str
    snapshot_date: str
    saturation_score: int
    trending_score: int
    search_volume_est: int
    competitor_count: int
    topics: list[NicheTopicResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class NicheSnapshotListResponse(BaseModel):
    """GET /niche/snapshots response."""
    snapshots: list[NicheSnapshotResponse]
    count: int


class NicheTopicListResponse(BaseModel):
    """GET /niche/topics response — flat list across recent snapshots."""
    topics: list[NicheTopicResponse]
    count: int


# ══════════════════════════════════════════════════════════════════════
# Empire OS — Revenue Attribution (Feature 3)
# ══════════════════════════════════════════════════════════════════════


class RevenueEventCreateRequest(BaseModel):
    """POST /revenue/events body."""
    source: str = Field(..., pattern=r"^(adsense|affiliate|stripe|manual)$")
    amount_cents: int = Field(..., ge=0)
    event_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    video_record_id: str | None = None
    external_id: str | None = None
    metadata: dict | None = None

    @field_validator("event_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        from datetime import datetime as dt
        try:
            dt.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("event_date must be a valid YYYY-MM-DD date")
        return v


class RevenueEventResponse(BaseModel):
    """A single revenue event."""
    id: str
    channel_id: str
    video_record_id: str | None = None
    source: str
    amount_cents: int
    currency: str
    event_date: str
    external_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RevenueEventListResponse(BaseModel):
    """GET /revenue/events response."""
    events: list[RevenueEventResponse]
    count: int


class RevenueDailyAggResponse(BaseModel):
    """A single daily aggregation row."""
    id: str
    channel_id: str
    agg_date: str
    total_cents: int
    adsense_cents: int
    affiliate_cents: int
    stripe_cents: int
    video_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RevenueDailyListResponse(BaseModel):
    """GET /revenue/daily response."""
    daily: list[RevenueDailyAggResponse]
    count: int


class RevenueTopVideoResponse(BaseModel):
    """A top-earning video in the summary."""
    video_record_id: str
    total_cents: int
    event_count: int


class RevenueSummaryResponse(BaseModel):
    """GET /revenue/summary response."""
    total_cents: int
    adsense_cents: int
    affiliate_cents: int
    stripe_cents: int
    manual_cents: int
    days_covered: int
    daily_average_cents: int
    top_videos: list[RevenueTopVideoResponse]
    period_days: int


# ══════════════════════════════════════════════════════════════════════
# Empire OS — Thumbnail A/B Testing (Feature 4)
# ══════════════════════════════════════════════════════════════════════


class ThumbVariantInput(BaseModel):
    """A single variant in a create-experiment request."""
    concept: str = Field(..., min_length=1, max_length=50)
    file_path: str = Field(..., min_length=1, max_length=2000)


class ThumbExperimentCreateRequest(BaseModel):
    """POST /thumbnails/experiments body."""
    video_record_id: str = Field(..., min_length=1)
    variants: list[ThumbVariantInput] = Field(..., min_length=2, max_length=5)


class ThumbVariantResponse(BaseModel):
    """A single thumbnail variant."""
    id: str
    experiment_id: str
    concept: str
    file_path: str
    impressions: int
    clicks: int
    ctr_pct: str | None = None
    is_active: bool
    deployed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ThumbExperimentResponse(BaseModel):
    """A thumbnail A/B experiment."""
    id: str
    channel_id: str
    video_record_id: str
    status: str
    started_at: datetime
    concluded_at: datetime | None = None
    winner_variant_id: str | None = None
    rotation_count: int
    variants: list[ThumbVariantResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class ThumbExperimentListResponse(BaseModel):
    """GET /thumbnails/experiments response."""
    experiments: list[ThumbExperimentResponse]
    count: int


class ThumbConcludeRequest(BaseModel):
    """POST /thumbnails/experiments/{id}/conclude body."""
    force: bool = False


# ══════════════════════════════════════════════════════════════════════
# Empire OS — Competitor Monitoring (Feature 5: Spy Mode)
# ══════════════════════════════════════════════════════════════════════


class CompetitorAddRequest(BaseModel):
    """POST /competitors body."""
    youtube_channel_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    subscriber_count: int | None = None


class CompetitorResponse(BaseModel):
    """A tracked competitor channel."""
    id: str
    channel_id: str
    youtube_channel_id: str
    name: str
    subscriber_count: int | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CompetitorListResponse(BaseModel):
    """GET /competitors response."""
    competitors: list[CompetitorResponse]
    count: int


class CompetitorSnapshotResponse(BaseModel):
    """A point-in-time snapshot of competitor metrics."""
    id: str
    competitor_id: str
    snapshot_date: str
    subscriber_count: int
    total_views: int
    video_count: int
    avg_views_per_video: int
    recent_videos_json: str | None = None
    top_tags_json: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompetitorSnapshotListResponse(BaseModel):
    """GET /competitors/{id}/snapshots response."""
    snapshots: list[CompetitorSnapshotResponse]
    count: int


class CompetitorSnapshotCreateRequest(BaseModel):
    """POST /competitors/{id}/snapshots body (manual ingestion)."""
    snapshot_date: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")
    subscriber_count: int = Field(0, ge=0)
    total_views: int = Field(0, ge=0)
    video_count: int = Field(0, ge=0)
    avg_views_per_video: int = Field(0, ge=0)
    recent_videos: list[dict] | None = None
    top_tags: list[str] | None = None


class CompetitorGrowthResponse(BaseModel):
    """Growth summary comparing two most recent snapshots."""
    has_data: bool
    subscriber_change: int
    view_change: int
    video_change: int
    period_start: str | None = None
    period_end: str | None = None


# ══════════════════════════════════════════════════════════════════════
# Empire OS — Voice Cloning Workflow (Feature 6)
# ══════════════════════════════════════════════════════════════════════


class VoiceCloneCreateRequest(BaseModel):
    """POST /voice-clones body."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    sample_file_key: str | None = Field(None, max_length=2000)
    sample_duration_secs: int | None = Field(None, ge=1, le=600)
    labels: dict | None = None


class VoiceCloneResponse(BaseModel):
    """A voice clone record."""
    id: str
    user_id: str
    name: str
    elevenlabs_voice_id: str | None = None
    status: str
    sample_file_key: str | None = None
    sample_duration_secs: int | None = None
    description: str | None = None
    labels_json: str | None = None
    preview_url: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VoiceCloneListResponse(BaseModel):
    """GET /voice-clones response."""
    voice_clones: list[VoiceCloneResponse]
    count: int

