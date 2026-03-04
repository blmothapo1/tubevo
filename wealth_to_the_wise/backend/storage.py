# filepath: backend/storage.py
"""
Durable artifact storage abstraction.

Two implementations:
  1. LocalStorage  — development (writes to output/)
  2. S3Storage     — production (S3, Cloudflare R2, GCS via S3 API)

Usage:
    from backend.storage import get_storage

    store = get_storage()
    url   = store.upload("videos/abc.mp4", Path("output/abc/final_video.mp4"))
    store.upload("thumbnails/abc.jpg", Path("output/abc/thumbnail.jpg"))

Environment variables (S3 mode):
    STORAGE_PROVIDER   — "local" or "s3" (required)
    STORAGE_BUCKET     — bucket name
    STORAGE_ENDPOINT   — custom endpoint URL (R2, MinIO, etc.)
    STORAGE_ACCESS_KEY — access key id
    STORAGE_SECRET_KEY — secret access key
    STORAGE_REGION     — region (default: "auto")
"""

from __future__ import annotations

import abc
import logging
import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("tubevo.backend.storage")


# ── Error type for storage failures ──────────────────────────────────

class StorageUploadError(RuntimeError):
    """Raised when an artifact cannot be persisted to durable storage."""
    pass


# ── Abstract base ────────────────────────────────────────────────────

class BaseStorage(abc.ABC):
    """Minimal interface for artifact persistence."""

    @abc.abstractmethod
    def upload(self, key: str, local_path: Path) -> str:
        """Upload a local file.  Returns a URL / pointer to the stored object."""

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        """Check whether an object exists in the store."""

    @abc.abstractmethod
    def provider_name(self) -> str:
        """Human-readable label for logging."""


# ── LocalStorage (development) ───────────────────────────────────────

class LocalStorage(BaseStorage):
    """Persist files on the local filesystem.  Fine for dev, NOT for prod."""

    def __init__(self, root: str = "output") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def upload(self, key: str, local_path: Path) -> str:
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(local_path), str(dest))
        except Exception as exc:
            raise StorageUploadError(f"Local copy failed: {exc}") from exc
        logger.info("LocalStorage: stored %s → %s", key, dest)
        return str(dest)

    def exists(self, key: str) -> bool:
        return (self._root / key).is_file()

    def provider_name(self) -> str:
        return "local"


# ── S3-compatible storage (production) ───────────────────────────────

class S3Storage(BaseStorage):
    """Upload artifacts to S3 / Cloudflare R2 / GCS via boto3."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str = "",
        secret_key: str = "",
        region: str = "auto",
    ) -> None:
        import boto3

        self._bucket = bucket
        kwargs: dict = {
            "service_name": "s3",
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region,
        }
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url

        self._client = boto3.client(**kwargs)
        logger.info(
            "S3Storage: bucket=%s endpoint=%s region=%s",
            bucket,
            endpoint_url or "(default AWS)",
            region,
        )

    def upload(self, key: str, local_path: Path) -> str:
        try:
            self._client.upload_file(str(local_path), self._bucket, key)
        except Exception as exc:
            raise StorageUploadError(
                f"S3 upload failed for {key}: {exc}"
            ) from exc

        url = f"s3://{self._bucket}/{key}"
        logger.info("S3Storage: uploaded %s → %s", local_path.name, url)
        return url

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def provider_name(self) -> str:
        return "s3"


# ── Factory ──────────────────────────────────────────────────────────

def _guard_local_storage_in_production() -> None:
    """Warn if production is running with local storage.

    Ephemeral filesystems (Railway, Heroku, Fly.io) lose data on every
    deploy — artifacts SHOULD go to durable object storage.

    Logs a loud warning rather than crashing, because videos are uploaded
    to YouTube immediately and local files only need to survive within a
    single deployment cycle.

    Only checks when ``ENV`` (or ``APP_ENV``) is explicitly
    ``"production"``.  Skipped entirely during pytest runs.
    """
    # Allow local storage inside tests
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    env = (
        os.environ.get("ENV", "")
        or os.environ.get("APP_ENV", "")
    ).strip().lower()

    is_production = env == "production"
    provider = os.environ.get("STORAGE_PROVIDER", "local").lower()

    if is_production and provider == "local":
        logger.warning(
            "⚠️  STORAGE_PROVIDER=local in production. Artifacts live on the "
            "ephemeral filesystem and will be lost on redeploy. "
            "Set STORAGE_PROVIDER=s3 + STORAGE_BUCKET for durable storage."
        )


@lru_cache
def get_storage() -> BaseStorage:
    """Return the configured storage backend (cached singleton)."""
    _guard_local_storage_in_production()

    provider = os.environ.get("STORAGE_PROVIDER", "local").lower()

    if provider == "local":
        logger.info("Using LocalStorage (development mode)")
        return LocalStorage()

    if provider == "s3":
        bucket = os.environ.get("STORAGE_BUCKET", "")
        if not bucket:
            raise RuntimeError("STORAGE_BUCKET must be set when STORAGE_PROVIDER=s3")
        return S3Storage(
            bucket=bucket,
            endpoint_url=os.environ.get("STORAGE_ENDPOINT"),
            access_key=os.environ.get("STORAGE_ACCESS_KEY", ""),
            secret_key=os.environ.get("STORAGE_SECRET_KEY", ""),
            region=os.environ.get("STORAGE_REGION", "auto"),
        )

    raise RuntimeError(
        f"Unknown STORAGE_PROVIDER='{provider}'. Use 'local' or 's3'."
    )
