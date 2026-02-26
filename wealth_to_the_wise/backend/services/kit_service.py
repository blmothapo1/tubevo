# filepath: backend/services/kit_service.py
"""
Kit (formerly ConvertKit) email subscriber service.

Subscribes emails to the Tubevo waitlist via Kit's v4 API.

Setup
-----
1. Get your API key from https://app.kit.com/account/developer
2. Set ``KIT_API_KEY`` in your backend .env / Railway env vars
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.config import get_settings

logger = logging.getLogger("tubevo.backend.kit")

KIT_API_URL = "https://api.kit.com/v4/subscribers"


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
    Kit returns HTTP 200 for both new and existing subscribers, so
    duplicate emails are handled gracefully — no special-casing needed.
    """
    settings = get_settings()
    api_key = settings.kit_api_key

    if not api_key:
        logger.warning("Kit API key not configured — skipping subscriber: %s", email)
        return {"success": False, "error": "Email service not configured."}

    payload: dict[str, Any] = {
        "email_address": email,
    }
    if name:
        payload["first_name"] = name

    # Kit v4 uses tag names; the API will auto-create the tag if it doesn't exist.
    payload["tags"] = ["tubevo_waitlist"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                KIT_API_URL,
                json=payload,
                headers=headers,
            )

        data = response.json()

        if response.status_code in (200, 201):
            subscriber_id = data.get("subscriber", {}).get("id", "unknown")
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
