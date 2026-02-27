# filepath: backend/services/email_service.py
"""
Transactional email service via Resend.

Provides a simple ``send_email()`` helper and pre-built templates
for password reset, welcome, and billing notifications.

Setup
-----
1. Sign up at https://resend.com (free: 3,000 emails/month)
2. Add + verify your domain (tubevo.us) in the Resend dashboard
3. Create an API key and set ``RESEND_API_KEY`` in Railway env vars
4. Set ``EMAIL_FROM`` to your verified sender (e.g. noreply@tubevo.us)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.config import get_settings

logger = logging.getLogger("tubevo.backend.email")

RESEND_API_URL = "https://api.resend.com/emails"


async def send_email(
    *,
    to: str | list[str],
    subject: str,
    html: str,
    reply_to: str | None = None,
) -> dict[str, Any] | None:
    """Send a transactional email via Resend.

    Returns the Resend API response dict on success, or None if email
    is not configured (gracefully degrades in dev).
    """
    settings = get_settings()
    api_key = settings.resend_api_key
    from_addr = settings.email_from

    if not api_key:
        logger.warning("Email not sent — RESEND_API_KEY not configured. Subject: %s, To: %s", subject, to)
        return None

    payload: dict[str, Any] = {
        "from": from_addr,
        "to": [to] if isinstance(to, str) else to,
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                RESEND_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )

        if resp.status_code in (200, 201):
            data = resp.json()
            logger.info("Email sent to %s — id=%s, subject='%s'", to, data.get("id"), subject)
            return data
        else:
            logger.error("Resend API error %d: %s", resp.status_code, resp.text)
            return None

    except Exception:
        logger.exception("Failed to send email to %s", to)
        return None


# ── Pre-built email templates ────────────────────────────────────────

def _base_template(content: str) -> str:
    """Wrap content in a styled email template."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0; padding:0; background-color:#0c0c14; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#0c0c14; padding:40px 20px;">
        <tr>
          <td align="center">
            <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px; background-color:#1c1c28; border-radius:16px; border:1px solid rgba(99,102,241,0.15); overflow:hidden;">
              <!-- Header -->
              <tr>
                <td style="background:linear-gradient(135deg,#6366f1,#4f46e5); padding:24px 32px;">
                  <h1 style="margin:0; color:#fff; font-size:20px; font-weight:700; letter-spacing:-0.02em;">Tubevo</h1>
                </td>
              </tr>
              <!-- Content -->
              <tr>
                <td style="padding:32px;">
                  {content}
                </td>
              </tr>
              <!-- Footer -->
              <tr>
                <td style="padding:20px 32px; border-top:1px solid rgba(255,255,255,0.06);">
                  <p style="margin:0; color:#5c5c78; font-size:12px; text-align:center;">
                    Tubevo · YouTube Automation Platform<br>
                    <a href="https://tubevo.us" style="color:#6366f1; text-decoration:none;">tubevo.us</a>
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


async def send_password_reset_email(*, to: str, token: str, reset_url: str) -> dict | None:
    """Send a password reset email."""
    html = _base_template(f"""
        <h2 style="margin:0 0 12px; color:#fff; font-size:18px; font-weight:600;">Reset your password</h2>
        <p style="margin:0 0 24px; color:#8e8eaa; font-size:14px; line-height:1.6;">
          We received a request to reset the password for your Tubevo account.
          Click the button below to choose a new password. This link expires in 30 minutes.
        </p>
        <a href="{reset_url}" style="display:inline-block; padding:12px 28px; background:linear-gradient(135deg,#6366f1,#4f46e5); color:#fff; text-decoration:none; border-radius:10px; font-size:14px; font-weight:600; letter-spacing:0.01em;">
          Reset Password
        </a>
        <p style="margin:24px 0 0; color:#5c5c78; font-size:12px; line-height:1.5;">
          If you didn't request this, you can safely ignore this email. Your password will remain unchanged.
        </p>
    """)

    return await send_email(
        to=to,
        subject="Reset your Tubevo password",
        html=html,
    )


async def send_welcome_email(*, to: str, name: str | None = None) -> dict | None:
    """Send a welcome email after signup."""
    greeting = f"Hi {name}," if name else "Welcome!"
    html = _base_template(f"""
        <h2 style="margin:0 0 12px; color:#fff; font-size:18px; font-weight:600;">{greeting}</h2>
        <p style="margin:0 0 24px; color:#8e8eaa; font-size:14px; line-height:1.6;">
          Welcome to Tubevo! Your account is all set. Here's how to get started:
        </p>
        <ol style="margin:0 0 24px; padding-left:20px; color:#b5b5ce; font-size:14px; line-height:2;">
          <li>Add your API keys in <strong style="color:#fff;">Settings → API Keys</strong></li>
          <li>Connect your YouTube channel in <strong style="color:#fff;">Settings → YouTube</strong></li>
          <li>Generate your first video in <strong style="color:#fff;">Videos → Generate</strong></li>
          <li>Set up automation in <strong style="color:#fff;">Schedule</strong></li>
        </ol>
        <a href="https://tubevo.us/dashboard" style="display:inline-block; padding:12px 28px; background:linear-gradient(135deg,#6366f1,#4f46e5); color:#fff; text-decoration:none; border-radius:10px; font-size:14px; font-weight:600;">
          Go to Dashboard
        </a>
    """)

    return await send_email(
        to=to,
        subject="Welcome to Tubevo 🎬",
        html=html,
    )


async def send_plan_upgrade_email(*, to: str, plan: str) -> dict | None:
    """Notify user of a successful plan upgrade."""
    html = _base_template(f"""
        <h2 style="margin:0 0 12px; color:#fff; font-size:18px; font-weight:600;">Plan upgraded! 🎉</h2>
        <p style="margin:0 0 24px; color:#8e8eaa; font-size:14px; line-height:1.6;">
          Your Tubevo account has been upgraded to the <strong style="color:#fbbf24;">{plan.title()}</strong> plan.
          Your new video limits and features are active immediately.
        </p>
        <a href="https://tubevo.us/settings?tab=plan" style="display:inline-block; padding:12px 28px; background:linear-gradient(135deg,#6366f1,#4f46e5); color:#fff; text-decoration:none; border-radius:10px; font-size:14px; font-weight:600;">
          View your plan
        </a>
    """)

    return await send_email(
        to=to,
        subject=f"You're now on the {plan.title()} plan",
        html=html,
    )


async def send_waitlist_confirmation_email(*, to: str, name: str | None = None) -> dict | None:
    """Send a confirmation email when someone joins the waitlist."""
    greeting = f"Hey {name}!" if name else "Hey there!"
    html = _base_template(f"""
        <h2 style="margin:0 0 12px; color:#fff; font-size:18px; font-weight:600;">{greeting}</h2>
        <p style="margin:0 0 20px; color:#8e8eaa; font-size:14px; line-height:1.7;">
          You're officially on the Tubevo waitlist! 🎉
        </p>
        <p style="margin:0 0 20px; color:#8e8eaa; font-size:14px; line-height:1.7;">
          We're building the easiest way to run a YouTube channel on autopilot — AI-generated
          scripts, voiceovers, video assembly, and auto-uploads. Zero manual work.
        </p>
        <p style="margin:0 0 24px; color:#8e8eaa; font-size:14px; line-height:1.7;">
          We'll email you the moment Tubevo is ready for you. In the meantime, here's what to expect:
        </p>
        <ul style="margin:0 0 24px; padding-left:20px; color:#b5b5ce; font-size:14px; line-height:2.2;">
          <li><strong style="color:#fff;">Early access</strong> — waitlist members get in first</li>
          <li><strong style="color:#fff;">Launch pricing</strong> — exclusive discounts at launch</li>
          <li><strong style="color:#fff;">No spam</strong> — we only email when it matters</li>
        </ul>
        <a href="https://tubevo.us" style="display:inline-block; padding:12px 28px; background:linear-gradient(135deg,#6366f1,#4f46e5); color:#fff; text-decoration:none; border-radius:10px; font-size:14px; font-weight:600;">
          Visit Tubevo
        </a>
        <p style="margin:24px 0 0; color:#5c5c78; font-size:12px; line-height:1.5;">
          Thanks for believing in us early. We won't let you down.
        </p>
    """)

    return await send_email(
        to=to,
        subject="You're on the Tubevo waitlist! 🚀",
        html=html,
    )
