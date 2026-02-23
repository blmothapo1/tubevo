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
    is_active: bool
    is_verified: bool
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
