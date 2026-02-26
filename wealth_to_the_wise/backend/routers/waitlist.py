# filepath: backend/routers/waitlist.py
"""
Public waitlist endpoint — /api/waitlist/*

Accepts email sign-ups from the landing page and forwards them to Kit
(formerly ConvertKit) via the kit_service. No authentication required.
"""

from __future__ import annotations

import logging

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.rate_limit import limiter
from backend.services.kit_service import subscribe_to_waitlist

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


# ── POST /api/waitlist/subscribe ─────────────────────────────────────

@router.post("/subscribe", response_model=WaitlistResponse)
@limiter.limit("10/hour")
async def waitlist_subscribe(
    request: Request,
    body: WaitlistRequest,
):
    """Subscribe an email to the Tubevo waitlist.

    Public endpoint — no authentication required.
    Rate-limited to 10 requests per hour per IP.
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

    # ── Subscribe via Kit ────────────────────────────────────────────
    kit_result = await subscribe_to_waitlist(
        email=clean_email,
        name=body.name,
    )

    if kit_result["success"]:
        logger.info("Waitlist signup: %s", clean_email)
        return WaitlistResponse(
            success=True,
            message="You're on the list! We'll notify you at launch.",
            subscriber_id=kit_result.get("subscriber_id"),
        )

    # Kit returned an error — log it but give the user a friendly message
    logger.warning("Waitlist signup failed for %s: %s", clean_email, kit_result.get("error"))
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=kit_result.get("error", "Failed to join the waitlist. Please try again."),
    )
