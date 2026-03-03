# filepath: backend/auth.py
"""
Authentication & authorization helpers.

- Password hashing: bcrypt (directly, no passlib — passlib is unmaintained
  and broken with bcrypt>=4.1)
- JWT tokens: access (short-lived) + refresh (long-lived)
- FastAPI dependency: ``get_current_user``
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database import get_db
from backend.models import User

logger = logging.getLogger("tubevo.backend.auth")

# ── Password hashing ────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT helpers ──────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT.  Raises HTTPException on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# ── Password-reset token (opaque, stored in DB) ─────────────────────

def generate_reset_token() -> str:
    """Generate a cryptographically secure reset token."""
    return secrets.token_urlsafe(48)


# ── OAuth2 scheme ────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── FastAPI dependency: current authenticated user ───────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the Bearer token to a User object.

    Raises 401 if the token is invalid, expired, or belongs to
    a deactivated account.
    """
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected an access token.",
        )

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing subject.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    return user


# ── FastAPI dependency: current admin user ───────────────────────────

async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Resolve the Bearer token to an admin User object.

    Raises 403 if the authenticated user does not have role='admin'.
    """
    if getattr(current_user, "role", "user") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user
