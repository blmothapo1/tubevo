"""
Referral / Affiliate System — /api/referrals/*

Phase 5: Users share a unique referral link.  When a referred user
signs up and converts to a paid plan, the referrer earns 20% recurring
commission for 12 months.

Endpoints
---------
GET    /api/referrals/dashboard   — Referral stats (total referred, converted, earnings)
GET    /api/referrals/code        — Get or generate the user's referral code
GET    /api/referrals/referred    — List of referred users with status
GET    /api/referrals/payouts     — Payout history
POST   /api/referrals/validate    — Validate a referral code (public-ish, rate-limited)
"""

from __future__ import annotations

import logging
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import Referral, ReferralPayout, User
from backend.rate_limit import limiter
from backend.utils import (
    REFERRAL_COMMISSION_PCT,
    REFERRAL_COMMISSION_MONTHS,
    PLAN_MONTHLY_PRICE_CENTS,
)

logger = logging.getLogger("tubevo.backend.referrals")

router = APIRouter(prefix="/api/referrals", tags=["Referrals"])


# ── Helpers ──────────────────────────────────────────────────────────

def _generate_referral_code(length: int = 8) -> str:
    """Generate a short, URL-safe referral code (e.g. TBV-A3K9M2)."""
    chars = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(chars) for _ in range(length))
    return f"TBV-{code}"


# ── Schemas ──────────────────────────────────────────────────────────

class ReferralDashboard(BaseModel):
    referral_code: str
    share_url: str
    total_referred: int
    total_converted: int
    total_earned_cents: int
    total_pending_cents: int
    commission_pct: int
    commission_months: int


class ReferralCodeResponse(BaseModel):
    referral_code: str
    share_url: str


class ReferredUserItem(BaseModel):
    email_masked: str
    full_name: str | None
    status: str           # signup | converted | churned
    plan: str
    signed_up_at: str
    converted_at: str | None
    earned_cents: int


class PayoutItem(BaseModel):
    id: str
    amount_cents: int
    trigger: str          # checkout | renewal | manual
    status: str           # pending | paid | failed
    referred_email_masked: str
    created_at: str
    paid_at: str | None


class ValidateCodeRequest(BaseModel):
    code: str


class ValidateCodeResponse(BaseModel):
    valid: bool
    referrer_name: str | None = None


# ── GET /api/referrals/code — Get or generate referral code ─────────

@router.get("/code", response_model=ReferralCodeResponse)
async def get_referral_code(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's referral code, generating one if it doesn't exist."""
    if not current_user.referral_code:
        # Generate a unique code with retry
        for _ in range(10):
            code = _generate_referral_code()
            existing = await db.execute(
                select(User.id).where(User.referral_code == code)
            )
            if not existing.scalar_one_or_none():
                current_user.referral_code = code
                db.add(current_user)
                await db.commit()
                await db.refresh(current_user)
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate unique referral code.")

    return ReferralCodeResponse(
        referral_code=current_user.referral_code,
        share_url=f"https://tubevo.us/signup?ref={current_user.referral_code}",
    )


# ── GET /api/referrals/dashboard — Full referral stats ──────────────

@router.get("/dashboard", response_model=ReferralDashboard)
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return comprehensive referral statistics."""
    # Ensure code exists
    if not current_user.referral_code:
        code_resp = await get_referral_code(current_user, db)
    else:
        code_resp = ReferralCodeResponse(
            referral_code=current_user.referral_code,
            share_url=f"https://tubevo.us/signup?ref={current_user.referral_code}",
        )

    # Total referred users
    total_referred = (await db.execute(
        select(func.count()).select_from(Referral).where(
            Referral.referrer_id == current_user.id
        )
    )).scalar() or 0

    # Total converted
    total_converted = (await db.execute(
        select(func.count()).select_from(Referral).where(
            Referral.referrer_id == current_user.id,
            Referral.status == "converted",
        )
    )).scalar() or 0

    # Total earned (paid payouts)
    total_earned = (await db.execute(
        select(func.coalesce(func.sum(ReferralPayout.amount_cents), 0)).where(
            ReferralPayout.referrer_id == current_user.id,
            ReferralPayout.status == "paid",
        )
    )).scalar() or 0

    # Total pending
    total_pending = (await db.execute(
        select(func.coalesce(func.sum(ReferralPayout.amount_cents), 0)).where(
            ReferralPayout.referrer_id == current_user.id,
            ReferralPayout.status == "pending",
        )
    )).scalar() or 0

    return ReferralDashboard(
        referral_code=code_resp.referral_code,
        share_url=code_resp.share_url,
        total_referred=total_referred,
        total_converted=total_converted,
        total_earned_cents=total_earned,
        total_pending_cents=total_pending,
        commission_pct=REFERRAL_COMMISSION_PCT,
        commission_months=REFERRAL_COMMISSION_MONTHS,
    )


# ── GET /api/referrals/referred — List referred users ───────────────

@router.get("/referred", response_model=list[ReferredUserItem])
async def list_referred(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users this user has referred, with their conversion status."""
    stmt = (
        select(Referral, User)
        .join(User, User.id == Referral.referred_user_id)
        .where(Referral.referrer_id == current_user.id)
        .order_by(Referral.created_at.desc())
    )
    results = (await db.execute(stmt)).all()

    items = []
    for ref, user in results:
        # Mask email: jo***@example.com
        parts = user.email.split("@")
        masked = parts[0][:2] + "***@" + parts[1] if len(parts) == 2 else "***"

        items.append(ReferredUserItem(
            email_masked=masked,
            full_name=user.full_name,
            status=ref.status,
            plan=user.plan,
            signed_up_at=ref.created_at.isoformat(),
            converted_at=ref.converted_at.isoformat() if ref.converted_at else None,
            earned_cents=ref.total_earned_cents,
        ))

    return items


# ── GET /api/referrals/payouts — Payout history ────────────────────

@router.get("/payouts", response_model=list[PayoutItem])
async def list_payouts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all commission payouts for this referrer."""
    stmt = (
        select(ReferralPayout, Referral, User)
        .join(Referral, Referral.id == ReferralPayout.referral_id)
        .join(User, User.id == Referral.referred_user_id)
        .where(ReferralPayout.referrer_id == current_user.id)
        .order_by(ReferralPayout.created_at.desc())
        .limit(100)
    )
    results = (await db.execute(stmt)).all()

    items = []
    for payout, _ref, user in results:
        parts = user.email.split("@")
        masked = parts[0][:2] + "***@" + parts[1] if len(parts) == 2 else "***"

        items.append(PayoutItem(
            id=payout.id,
            amount_cents=payout.amount_cents,
            trigger=payout.trigger,
            status=payout.status,
            referred_email_masked=masked,
            created_at=payout.created_at.isoformat(),
            paid_at=payout.paid_at.isoformat() if payout.paid_at else None,
        ))

    return items


# ── POST /api/referrals/validate — Validate a code (for signup) ────

@router.post("/validate", response_model=ValidateCodeResponse)
async def validate_code(
    body: ValidateCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Validate a referral code. Used by the signup page to show referrer info."""
    code = body.code.strip().upper()
    result = await db.execute(
        select(User).where(User.referral_code == code)
    )
    referrer = result.scalar_one_or_none()
    if not referrer:
        return ValidateCodeResponse(valid=False)

    # Show first name only
    name = referrer.full_name.split()[0] if referrer.full_name else None
    return ValidateCodeResponse(valid=True, referrer_name=name)


# ── Internal helper: record a referral on signup ────────────────────

async def record_referral_signup(
    referrer_code: str,
    new_user: User,
    db: AsyncSession,
) -> Referral | None:
    """Called from the signup endpoint when a ``ref`` code is provided.

    Creates the Referral record and sets ``new_user.referred_by``.
    Returns the Referral or None if the code is invalid.
    """
    code = referrer_code.strip().upper()
    result = await db.execute(
        select(User).where(User.referral_code == code)
    )
    referrer = result.scalar_one_or_none()
    if not referrer:
        logger.warning("Invalid referral code on signup: %s", code)
        return None

    # Don't allow self-referral
    if referrer.id == new_user.id:
        return None

    # Check if referral already exists (shouldn't happen, but be safe)
    existing = await db.execute(
        select(Referral).where(Referral.referred_user_id == new_user.id)
    )
    if existing.scalar_one_or_none():
        return None

    referral = Referral(
        referrer_id=referrer.id,
        referred_user_id=new_user.id,
        status="signup",
    )
    new_user.referred_by = referrer.id
    db.add(referral)
    db.add(new_user)

    logger.info(
        "Referral recorded: %s referred %s (code=%s)",
        referrer.email, new_user.email, code,
    )
    return referral


# ── Internal helper: convert referral on paid plan upgrade ──────────

async def convert_referral_on_upgrade(
    user: User,
    new_plan: str,
    db: AsyncSession,
    stripe_invoice_id: str | None = None,
) -> ReferralPayout | None:
    """Called from the billing webhook when a referred user upgrades.

    Marks the referral as converted and creates the first commission payout.
    """
    if not user.referred_by:
        return None

    # Find the referral record
    result = await db.execute(
        select(Referral).where(Referral.referred_user_id == user.id)
    )
    referral = result.scalar_one_or_none()
    if not referral:
        return None

    # Calculate commission
    plan_price = PLAN_MONTHLY_PRICE_CENTS.get(new_plan, 0)
    if plan_price == 0:
        return None

    commission = int(plan_price * REFERRAL_COMMISSION_PCT / 100)

    # Update referral status
    from datetime import datetime, timezone
    if referral.status != "converted":
        referral.status = "converted"
        referral.converted_plan = new_plan
        referral.converted_at = datetime.now(timezone.utc)

    referral.total_earned_cents += commission
    db.add(referral)

    # Create payout record
    payout = ReferralPayout(
        referral_id=referral.id,
        referrer_id=referral.referrer_id,
        amount_cents=commission,
        trigger="checkout",
        status="pending",
        stripe_invoice_id=stripe_invoice_id,
    )
    db.add(payout)

    # Add credit to referrer's account
    referrer_result = await db.execute(
        select(User).where(User.id == referral.referrer_id)
    )
    referrer = referrer_result.scalar_one_or_none()
    if referrer:
        referrer.credit_balance += commission
        db.add(referrer)

    logger.info(
        "Referral converted: referrer=%s earned %d¢ from %s upgrading to %s",
        referral.referrer_id, commission, user.email, new_plan,
    )
    return payout
