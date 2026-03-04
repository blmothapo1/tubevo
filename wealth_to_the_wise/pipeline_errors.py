# filepath: pipeline_errors.py
"""
Typed exception hierarchy for the video generation pipeline.

Phase 2 — Typed Pipeline Errors
-------------------------------
These replace the generic ``RuntimeError`` raised throughout the
pipeline modules (script_generator, voiceover, stock_footage,
video_builder) so the backend can classify failures for the admin
error dashboard and give users actionable error messages.

Every subclass carries a ``category`` string that maps 1-to-1 with
the ``VideoRecord.error_category`` column.
"""

from __future__ import annotations


class PipelineError(RuntimeError):
    """Base class for all pipeline errors.

    Attributes
    ----------
    category : str
        Short machine-readable tag stored in ``VideoRecord.error_category``.
        One of: api_quota, api_auth, external_service, render, upload,
        timeout, unknown.
    user_hint : str
        A short, non-technical message safe to show in the frontend UI.
    """

    category: str = "unknown"
    user_hint: str = "Something went wrong during video generation. Please try again."

    def __init__(self, message: str, *, user_hint: str | None = None) -> None:
        super().__init__(message)
        if user_hint:
            self.user_hint = user_hint


class ApiQuotaError(PipelineError):
    """An external API's usage quota / billing limit has been exceeded."""

    category = "api_quota"
    user_hint = (
        "Your API quota has been exceeded. "
        "Please check your billing on the provider's dashboard."
    )


class ApiAuthError(PipelineError):
    """An API key is missing, invalid, or revoked."""

    category = "api_auth"
    user_hint = (
        "Your API key appears to be invalid or expired. "
        "Please update it in Settings → API Keys."
    )


class ExternalServiceError(PipelineError):
    """A transient error from an external service (rate limit retries
    exhausted, 5xx responses, network failures)."""

    category = "external_service"
    user_hint = (
        "An external service is temporarily unavailable. "
        "Please try again in a few minutes."
    )


class RenderError(PipelineError):
    """FFmpeg / video assembly failure."""

    category = "render"
    user_hint = (
        "Video rendering failed. This is usually a temporary issue — "
        "please try again."
    )


class UploadError(PipelineError):
    """YouTube upload failure (auth expired, quota, network)."""

    category = "upload"
    user_hint = (
        "YouTube upload failed. Please check that your YouTube account "
        "is still connected in Settings."
    )
