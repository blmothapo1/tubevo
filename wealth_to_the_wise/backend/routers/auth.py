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
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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
from backend.config import get_settings
from backend.database import get_db
from backend.events import emit_event
from backend.models import User, WaitlistSignup
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

# ── Cookie name for the httpOnly refresh token ───────────────────────
_REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set the refresh token as an httpOnly, Secure, SameSite=None cookie.

    SameSite=None is required because the frontend (tubevo.us) talks to a
    separate backend origin (api.tubevo.us) — a cross-site request.
    The Secure flag ensures it's only sent over HTTPS.
    """
    settings = get_settings()
    max_age = settings.jwt_refresh_token_expire_days * 86400  # days → seconds
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=True,            # HTTPS only
        samesite="none",        # cross-origin (frontend ≠ backend domain)
        max_age=max_age,
        path="/auth",           # only sent to /auth/* endpoints
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Delete the refresh-token cookie."""
    response.delete_cookie(
        key=_REFRESH_COOKIE,
        httponly=True,
        secure=True,
        samesite="none",
        path="/auth",
    )


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

    # Auto-grant beta access if this email is on the waitlist
    waitlist_entry = (await db.execute(
        select(WaitlistSignup).where(WaitlistSignup.email == body.email.strip().lower())
    )).scalar_one_or_none()
    if waitlist_entry:
        user.is_beta = True
        logger.info("Auto-granting beta access to waitlist email: %s", body.email)

    db.add(user)
    await db.flush()           # populate user.id before response
    await db.refresh(user)

    logger.info("New user registered: %s (id=%s)", user.email, user.id)

    # ── Phase 5: Record referral if a code was provided ──────────────
    if body.referral_code:
        try:
            from backend.routers.referrals import record_referral_signup
            await record_referral_signup(body.referral_code, user, db)
        except Exception:
            logger.warning("Referral recording failed for %s (non-fatal)", user.email, exc_info=True)

    # ── Admin event: user_signup ─────────────────────────────────────
    await emit_event(db, "user_signup", user_id=user.id, meta={"email": user.email})

    # Send welcome email (fire-and-forget, don't block signup)
    try:
        from backend.services.email_service import send_welcome_email
        await send_welcome_email(to=user.email, name=user.full_name)
    except Exception:
        logger.warning("Failed to send welcome email to %s", user.email, exc_info=True)

    return SignUpResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plan=user.plan,
    )


# ── POST /auth/login ────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit("30/minute")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email + password.

    Returns the access token in the JSON body and sets the refresh token
    as an httpOnly cookie — never exposed to JavaScript.
    """
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

    # ── Auto-promote admin emails ────────────────────────────────────
    settings = get_settings()
    if user.email.lower() in settings.admin_email_list and user.role != "admin":
        user.role = "admin"
        db.add(user)
        logger.info("Auto-promoted %s to admin role.", user.email)

    # ── Track last login ─────────────────────────────────────────────
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)

    logger.info("User logged in: %s", user.email)

    refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
    )


# ── POST /auth/logout ───────────────────────────────────────────────

@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response) -> MessageResponse:
    """Clear the httpOnly refresh-token cookie."""
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out.")


# ── POST /auth/refresh ──────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_tokens(
    request: Request,
    response: Response,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh pair.

    The refresh token is read from the httpOnly cookie first.  Falls back
    to the JSON body for backward compatibility with older clients.
    """
    # Prefer the httpOnly cookie; fall back to JSON body (legacy clients)
    raw_token = request.cookies.get(_REFRESH_COOKIE) or body.refresh_token
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided.",
        )

    payload = decode_token(raw_token)

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

    # Rotate refresh token and set the new one as a cookie
    new_refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, new_refresh)

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
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

        # Build the reset URL pointing to the frontend
        settings = get_settings()
        frontend_origin = settings.cors_origins.split(",")[0].strip()
        reset_url = f"{frontend_origin}/reset-password?token={token}"

        # Send the password reset email (gracefully degrades if Resend not configured)
        from backend.services.email_service import send_password_reset_email
        await send_password_reset_email(to=user.email, token=token, reset_url=reset_url)

        logger.info(
            "Password reset requested for %s (expires in %d min)",
            user.email, RESET_TOKEN_LIFETIME_MINUTES,
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
    response: Response,
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
    now_utc = datetime.now(timezone.utc)
    claims = {
        "iss": team_id,
        "iat": int(now_utc.timestamp()),
        "exp": int((now_utc + timedelta(days=180)).timestamp()),
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

    # Decode Apple's id_token.
    # NOTE: Full JWKS signature verification requires fetching Apple's public
    # keys from https://appleid.apple.com/auth/keys and matching by 'kid'.
    # For now we skip signature verification (token came directly from Apple
    # over HTTPS in the server-to-server exchange above), but we DO validate
    # the issuer and audience claims to prevent token misuse.
    apple_info = jwt.decode(
        id_token,
        key="",
        options={"verify_signature": False},
    )
    if apple_info.get("iss") != "https://appleid.apple.com":
        raise HTTPException(status_code=400, detail="Invalid Apple id_token issuer.")
    if apple_info.get("aud") != client_id:
        raise HTTPException(status_code=400, detail="Invalid Apple id_token audience.")

    email = apple_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email from Apple.")

    # Find or create user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        # OAuth-only accounts get a sentinel password hash that can never
        # match any real password — prevents login via the email/password
        # endpoint while the account has no password set.
        _OAUTH_NO_PASSWORD = "!oauth-only-no-password-set"
        user = User(
            email=email,
            hashed_password=_OAUTH_NO_PASSWORD,
            full_name=apple_info.get("name", ""),
            is_verified=True,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    # ── Auto-promote admin emails (Apple login) ─────────────────────
    if user.email.lower() in get_settings().admin_email_list and user.role != "admin":
        user.role = "admin"
        db.add(user)
        logger.info("Auto-promoted %s to admin role (Apple login).", user.email)

    refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh)

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        token_type="bearer",
    )
