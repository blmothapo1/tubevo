# filepath: backend/routers/auth.py
"""
Authentication router — /auth/*

Endpoints
---------
POST /auth/signup           — Create a new account
POST /auth/login            — Log in, get access + refresh tokens
POST /auth/refresh          — Exchange a refresh token for new tokens
GET  /auth/me               — Get current user profile
PATCH /auth/me              — Update profile (full_name)
POST /auth/forgot-password  — Request a password-reset token
POST /auth/reset-password   — Reset password using the token
POST /auth/apple            — Log in with Apple ID OAuth2
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_reset_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.database import get_db
from backend.models import User
from backend.rate_limit import limiter
from backend.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SignUpRequest,
    SignUpResponse,
    TokenResponse,
    UpdateProfileRequest,
    UserProfile,
    AppleLoginRequest,  # <-- add this import
)

logger = logging.getLogger("tubevo.backend.auth_router")

router = APIRouter(prefix="/auth", tags=["Auth"])

RESET_TOKEN_LIFETIME_MINUTES = 60  # password-reset link valid for 1 hour


# ── POST /auth/signup ────────────────────────────────────────────────

@router.post("/signup", response_model=SignUpResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def signup(
    request: Request,
    body: SignUpRequest,
    db: AsyncSession = Depends(get_db),
) -> SignUpResponse:
    """Register a new user account."""
    # Check for existing email
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()           # populate user.id before response
    await db.refresh(user)

    logger.info("New user registered: %s (id=%s)", user.email, user.id)

    return SignUpResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plan=user.plan,
    )


# ── POST /auth/login ────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email + password. Returns JWT tokens."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    logger.info("User logged in: %s", user.email)

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=create_refresh_token(user.id),
    )


# ── POST /auth/refresh ──────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_tokens(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh pair."""
    payload = decode_token(body.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected a refresh token.",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=create_refresh_token(user.id),
    )


# ── GET /auth/me ─────────────────────────────────────────────────────

@router.get("/me", response_model=UserProfile)
async def get_me(current_user: User = Depends(get_current_user)) -> UserProfile:
    """Return the authenticated user's profile."""
    return UserProfile.model_validate(current_user)


# ── PATCH /auth/me ───────────────────────────────────────────────────

@router.patch("/me", response_model=UserProfile)
async def update_me(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Update the authenticated user's profile."""
    if body.full_name is not None:
        current_user.full_name = body.full_name

    db.add(current_user)
    await db.flush()
    await db.refresh(current_user)

    logger.info("User %s updated profile.", current_user.email)
    return UserProfile.model_validate(current_user)


# ── POST /auth/forgot-password ──────────────────────────────────────

@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Request a password-reset token.

    Always returns 200 to avoid leaking whether the email exists.
    In production, this would send a transactional email via
    SendGrid / Resend with a link containing the token.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user:
        token = generate_reset_token()
        user.reset_token = token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(
            minutes=RESET_TOKEN_LIFETIME_MINUTES
        )
        db.add(user)

        # TODO (Item 2 follow-up): Send email via SendGrid / Resend
        # For now, log the token so it can be used manually in dev.
        logger.info(
            "Password reset requested for %s — token: %s (expires in %d min)",
            user.email, token, RESET_TOKEN_LIFETIME_MINUTES,
        )

    return MessageResponse(
        message="If an account with that email exists, a reset link has been sent.",
    )


# ── POST /auth/reset-password ───────────────────────────────────────

@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("10/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Reset the user's password using a valid reset token."""
    result = await db.execute(
        select(User).where(User.reset_token == body.token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    if (
        user.reset_token_expires is None
        or user.reset_token_expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
    ):
        # Token expired — clear it
        user.reset_token = None
        user.reset_token_expires = None
        db.add(user)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    user.hashed_password = hash_password(body.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.add(user)

    logger.info("Password reset completed for %s.", user.email)

    return MessageResponse(message="Password has been reset successfully.")


# ── POST /auth/apple ────────────────────────────────────────────────

@router.post("/apple", response_model=TokenResponse)
@limiter.limit("20/minute")
async def apple_login(
    request: Request,
    body: AppleLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with Apple ID OAuth2."""
    code = body.code
    if not code:
        raise HTTPException(status_code=400, detail="Missing Apple auth code.")

    # Apple credentials from env
    client_id = os.getenv("APPLE_CLIENT_ID")
    team_id = os.getenv("APPLE_TEAM_ID")
    key_id = os.getenv("APPLE_KEY_ID")
    private_key = os.getenv("APPLE_PRIVATE_KEY")

    if not private_key:
        raise HTTPException(status_code=500, detail="Apple private key not configured.")

    # Create client secret (JWT)
    headers = {"kid": key_id}
    claims = {
        "iss": team_id,
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(days=180)).timestamp()),
        "aud": "https://appleid.apple.com",
        "sub": client_id,
    }
    client_secret = jwt.encode(claims, private_key, algorithm="ES256", headers=headers)

    # Exchange code for tokens
    token_url = "https://appleid.apple.com/auth/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    }
    resp = requests.post(token_url, data=data)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Apple token exchange failed.")
    tokens = resp.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="No id_token from Apple.")
    apple_info = jwt.decode(id_token, key="", options={"verify_signature": False})
    email = apple_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email from Apple.")

    # Find or create user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=email, hashed_password="", full_name=apple_info.get("name", ""), is_verified=True)
        db.add(user)
        await db.flush()
        await db.refresh(user)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=create_refresh_token(user.id),
        token_type="bearer",
    )
