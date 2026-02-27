# filepath: backend/routers/waitlist.py
"""
Public waitlist endpoint — /api/waitlist/*

Accepts email sign-ups from the landing page, persists them in the
local database (so no leads are ever lost), and then attempts to
forward them to Kit (formerly ConvertKit) as a best-effort sync.

No authentication required.
"""

from __future__ import annotations

import logging

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import WaitlistSignup
from backend.rate_limit import limiter
from backend.services.kit_service import subscribe_to_waitlist
from backend.services.email_service import send_waitlist_confirmation_email

logger = logging.getLogger("tubevo.backend.waitlist")

router = APIRouter(prefix="/api/waitlist", tags=["Waitlist"])


# ── Schemas ──────────────────────────────────────────────────────────

class WaitlistRequest(BaseModel):
    email: str
    name: str | None = None


class WaitlistResponse(BaseModel):
    success: bool
    message: str
    subscriber_id: str | None = None


class WaitlistCountResponse(BaseModel):
    count: int


# ── POST /api/waitlist/subscribe ─────────────────────────────────────

@router.post("/subscribe", response_model=WaitlistResponse)
@limiter.limit("10/hour")
async def waitlist_subscribe(
    request: Request,
    body: WaitlistRequest,
    db: AsyncSession = Depends(get_db),
):
    """Subscribe an email to the Tubevo waitlist.

    Public endpoint — no authentication required.
    Rate-limited to 10 requests per hour per IP.

    Flow:
    1. Validate the email
    2. Save to local DB (idempotent — duplicates return success)
    3. Best-effort sync to Kit (non-blocking on failure)
    """
    # ── Validate email ───────────────────────────────────────────────
    try:
        result = validate_email(body.email, check_deliverability=False)
        clean_email = result.normalized
    except EmailNotValidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid email address: {exc}",
        )

    # ── Check for duplicate ──────────────────────────────────────────
    existing = await db.execute(
        select(WaitlistSignup).where(WaitlistSignup.email == clean_email)
    )
    signup = existing.scalar_one_or_none()

    if signup:
        logger.info("Waitlist duplicate (already signed up): %s", clean_email)
        return WaitlistResponse(
            success=True,
            message="You're already on the list! We'll notify you at launch.",
            subscriber_id=signup.kit_subscriber_id,
        )

    # ── Save to DB first (never lose a lead) ─────────────────────────
    signup = WaitlistSignup(
        email=clean_email,
        name=body.name,
        kit_sync_status="pending",
    )
    db.add(signup)
    await db.flush()  # get the ID before Kit call
    logger.info("Waitlist signup saved to DB: %s", clean_email)

    # ── Best-effort Kit sync ─────────────────────────────────────────
    kit_result = await subscribe_to_waitlist(email=clean_email, name=body.name)

    if kit_result["success"]:
        signup.kit_sync_status = "synced"
        signup.kit_subscriber_id = kit_result.get("subscriber_id")
        logger.info("Waitlist Kit sync OK: %s → id=%s", clean_email, signup.kit_subscriber_id)
    else:
        signup.kit_sync_status = "failed"
        logger.warning(
            "Waitlist Kit sync failed for %s: %s (email saved locally)",
            clean_email,
            kit_result.get("error"),
        )

    # ── Send confirmation email via Resend (best-effort) ─────────────
    try:
        await send_waitlist_confirmation_email(to=clean_email, name=body.name)
    except Exception:
        logger.warning("Waitlist confirmation email failed for %s (non-blocking)", clean_email)

    # Commit happens automatically via get_db dependency
    return WaitlistResponse(
        success=True,
        message="You're on the list! We'll notify you at launch.",
        subscriber_id=signup.kit_subscriber_id,
    )


# ── GET /api/waitlist/count ──────────────────────────────────────────

@router.get("/count", response_model=WaitlistCountResponse)
async def waitlist_count(
    db: AsyncSession = Depends(get_db),
):
    """Return the total number of waitlist signups.

    Public endpoint — used by the landing page to show a live count.
    """
    result = await db.execute(
        select(func.count()).select_from(WaitlistSignup)
    )
    count = result.scalar() or 0
    return WaitlistCountResponse(count=count)
