# filepath: backend/schemas.py
"""
Pydantic schemas for request/response validation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


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
    """PUT /api/keys body — any field left None is not changed."""
    openai_api_key: str | None = Field(None, max_length=200)
    elevenlabs_api_key: str | None = Field(None, max_length=200)
    elevenlabs_voice_id: str | None = Field(None, max_length=100)
    pexels_api_key: str | None = Field(None, max_length=200)


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
