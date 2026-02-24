# filepath: backend/routers/billing.py
"""
Billing router — /billing/*

Stripe integration for subscription management.

Endpoints
---------
POST /billing/create-checkout-session  — Start a Stripe Checkout for plan upgrade
POST /billing/webhook                  — Stripe webhook receiver
GET  /billing/portal                   — Redirect to Stripe Customer Portal
"""

from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.config import get_settings
from backend.database import get_db
from backend.models import User

logger = logging.getLogger("tubevo.backend.billing")

router = APIRouter(prefix="/billing", tags=["Billing"])

# Price IDs — set these in Stripe Dashboard → Products → Pricing
# For now, map plan names to placeholder price IDs.
# Replace these with your real Stripe Price IDs.
PLAN_PRICE_MAP: dict[str, str] = {
    "starter": "price_1T48StEi8DhCMyZZVtmPJevL",   # $29/mo
    "pro":     "price_1T48X6Ei8DhCMyZZyCAgEIg4",   # $79/mo
    "agency":  "price_1T48XlEi8DhCMyZZcQIy50R6",   # $199/mo
}


def _get_stripe() -> None:
    """Configure the stripe module with the secret key."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured.",
        )
    stripe.api_key = settings.stripe_secret_key


# ── POST /billing/create-checkout-session ────────────────────────────

@router.post("/create-checkout-session")
async def create_checkout_session(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Create a Stripe Checkout Session for upgrading the user's plan."""
    _get_stripe()

    body = await request.json()
    plan = body.get("plan", "pro")

    price_id = PLAN_PRICE_MAP.get(plan)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")

    settings = get_settings()

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=current_user.email,
            client_reference_id=current_user.id,
            success_url=f"{settings.cors_origins.split(',')[0].strip()}/settings?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.cors_origins.split(',')[0].strip()}/settings",
            metadata={"user_id": current_user.id, "plan": plan},
        )
    except stripe.StripeError as e:
        logger.error("Stripe checkout error: %s", e)
        raise HTTPException(status_code=502, detail="Payment provider error.")

    return {"checkout_url": session.url}


# ── POST /billing/webhook ────────────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive Stripe webhook events.

    Key events handled:
    - checkout.session.completed  →  upgrade user plan
    - customer.subscription.deleted  →  downgrade to free
    """
    _get_stripe()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    settings = get_settings()
    endpoint_secret = settings.stripe_webhook_secret or ""

    if endpoint_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except (ValueError, stripe.SignatureVerificationError) as e:
            logger.warning("Webhook signature verification failed: %s", e)
            raise HTTPException(status_code=400, detail="Invalid signature.")
    else:
        import json
        event = json.loads(payload)
        logger.warning("⚠️  Webhook signature verification skipped (no STRIPE_WEBHOOK_SECRET configured)")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})
    logger.info("Stripe webhook received: %s", event_type)

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id") or data.get("metadata", {}).get("user_id")
        plan = data.get("metadata", {}).get("plan", "pro")
        customer_id = data.get("customer")
        if user_id:
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                user.plan = plan
                # Store the Stripe customer ID for future webhook lookups
                if customer_id:
                    user.stripe_customer_id = customer_id
                db.add(user)
                await db.commit()
                logger.info("User %s upgraded to %s plan (stripe_customer=%s).", user.email, plan, customer_id)
                # Send plan upgrade email
                try:
                    from backend.services.email_service import send_plan_upgrade_email
                    await send_plan_upgrade_email(to=user.email, plan=plan)
                except Exception:
                    logger.warning("Failed to send plan upgrade email to %s", user.email, exc_info=True)
            else:
                logger.warning("Webhook: user_id %s not found in DB.", user_id)

    elif event_type == "customer.subscription.deleted":
        # Subscription cancelled — look up user via stored Stripe customer ID
        customer_id = data.get("customer")
        user = await _find_user_by_customer_id(db, customer_id)
        if user:
            user.plan = "free"
            db.add(user)
            await db.commit()
            logger.info("User %s downgraded to free (subscription cancelled).", user.email)
        else:
            logger.warning("Webhook subscription.deleted: no user found for customer %s", customer_id)

    elif event_type == "customer.subscription.updated":
        # Handle plan changes (upgrade/downgrade) via the portal
        customer_id = data.get("customer")
        sub_status = data.get("status")
        if customer_id and sub_status == "active":
            # Determine the new plan from the price ID
            items = data.get("items", {}).get("data", [])
            price_id = items[0]["price"]["id"] if items else None
            if price_id:
                # Reverse-lookup the plan name from the price ID
                plan_name = None
                for pname, pid in PLAN_PRICE_MAP.items():
                    if pid == price_id:
                        plan_name = pname
                        break
                if plan_name:
                    user = await _find_user_by_customer_id(db, customer_id)
                    if user:
                        user.plan = plan_name
                        db.add(user)
                        await db.commit()
                        logger.info("User %s changed plan to %s.", user.email, plan_name)

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        if customer_id:
            logger.warning("Payment failed for Stripe customer %s.", customer_id)

    return JSONResponse(content={"received": True})


async def _find_user_by_customer_id(db: AsyncSession, customer_id: str | None) -> User | None:
    """Look up a user by their stored Stripe customer ID.

    Falls back to email lookup via the Stripe API if the customer ID
    isn't stored yet (backwards compat for pre-migration users).
    """
    if not customer_id:
        return None

    from sqlalchemy import select

    # Primary lookup: by stored stripe_customer_id
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if user:
        return user

    # Fallback: resolve email via Stripe API, then look up by email
    try:
        customer = stripe.Customer.retrieve(customer_id)
        customer_email = customer.get("email")
    except Exception as e:
        logger.error("Failed to retrieve Stripe customer %s: %s", customer_id, e)
        return None

    if not customer_email:
        return None

    result = await db.execute(select(User).where(User.email == customer_email))
    user = result.scalar_one_or_none()
    if user:
        # Backfill the stripe_customer_id for future lookups
        user.stripe_customer_id = customer_id
        db.add(user)
        logger.info("Backfilled stripe_customer_id for user %s", user.email)
    return user


# ── GET /billing/portal ──────────────────────────────────────────────

@router.get("/portal")
async def customer_portal(
    current_user: User = Depends(get_current_user),
):
    """Create a Stripe Customer Portal session for managing subscriptions."""
    _get_stripe()
    settings = get_settings()

    # Use stored customer ID if available, otherwise search by email
    customer_id = current_user.stripe_customer_id
    if not customer_id:
        customers = stripe.Customer.list(email=current_user.email, limit=1)
        if not customers.data:
            raise HTTPException(status_code=404, detail="No billing account found. Please subscribe first.")
        customer_id = customers.data[0].id

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.cors_origins.split(',')[0].strip()}/settings",
    )

    return {"portal_url": session.url}
