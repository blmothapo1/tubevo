# filepath: backend/services/kit_service.py
"""
Kit (formerly ConvertKit) email subscriber service.

Subscribes emails to the Tubevo waitlist via Kit's **v3 API**.

Uses the "TubeVo Waitlist" form (ID 9138848) and applies the
``tubevo_waitlist`` tag (ID 16565194) for filtering.

Setup
-----
1. Get your API Secret from https://app.kit.com/account/developer
2. Set ``KIT_API_KEY`` in your backend .env / Railway env vars
   (this is the v3 api_secret, NOT the v4 kit_ prefixed key)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.config import get_settings

logger = logging.getLogger("tubevo.backend.kit")

# Kit v3 endpoints
KIT_V3_BASE = "https://api.convertkit.com/v3"
KIT_FORM_ID = "9138848"            # "TubeVo Waitlist" form
KIT_TAG_ID = "16565194"            # "tubevo_waitlist" tag
KIT_SUBSCRIBE_URL = f"{KIT_V3_BASE}/forms/{KIT_FORM_ID}/subscribe"


async def subscribe_to_waitlist(
    email: str,
    name: str | None = None,
) -> dict[str, Any]:
    """Subscribe an email to the Tubevo waitlist on Kit.

    Parameters
    ----------
    email:
        The subscriber's email address (already validated by the caller).
    name:
        Optional first name for personalisation.

    Returns
    -------
    dict
        ``{"success": True, "subscriber_id": "..."}`` on success, or
        ``{"success": False, "error": "..."}`` on failure.

    Notes
    -----
    Kit v3 returns HTTP 200 for both new and existing subscribers, so
    duplicate emails are handled gracefully — no special-casing needed.
    The subscriber is added to the "TubeVo Waitlist" form and tagged
    with ``tubevo_waitlist`` for easy segmentation.
    """
    settings = get_settings()
    api_secret = settings.kit_api_key

    if not api_secret:
        logger.warning("Kit API secret not configured — skipping subscriber: %s", email)
        return {"success": False, "error": "Email service not configured."}

    payload: dict[str, Any] = {
        "api_secret": api_secret,
        "email": email,
        "tags": [KIT_TAG_ID],
    }
    if name:
        payload["first_name"] = name

    headers = {
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                KIT_SUBSCRIBE_URL,
                json=payload,
                headers=headers,
            )

        data = response.json()

        if response.status_code in (200, 201):
            subscriber_id = (
                data.get("subscription", {}).get("subscriber", {}).get("id", "unknown")
            )
            logger.info("Kit subscriber created/updated: %s → id=%s", email, subscriber_id)
            return {"success": True, "subscriber_id": str(subscriber_id)}

        # Kit returned an error
        error_msg = data.get("message") or data.get("error") or f"HTTP {response.status_code}"
        logger.warning("Kit API error for %s: %s (status=%d)", email, error_msg, response.status_code)
        return {"success": False, "error": error_msg}

    except httpx.TimeoutException:
        logger.error("Kit API timeout for %s", email)
        return {"success": False, "error": "Email service timed out. Please try again."}
    except Exception as exc:
        logger.exception("Kit API unexpected error for %s: %s", email, exc)
        return {"success": False, "error": "Email service error. Please try again."}
