"""
storage_service.py — Cloudflare R2 temporary video storage.

Uses boto3 with the S3-compatible R2 endpoint.  Videos are uploaded with
a unique key, and deleted immediately after YouTube upload completes
(or fails).  This keeps R2 costs near-zero — it's just a transient buffer.

Required env vars (see .env.example):
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig

logger = logging.getLogger("wealth_to_the_wise.storage")


def _get_env(name: str) -> str:
    """Read a required env var or raise immediately with a clear message."""
    value = os.getenv(name, "").strip()
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value


def _get_client():
    """Build a boto3 S3 client pointed at the Cloudflare R2 endpoint."""
    account_id = _get_env("R2_ACCOUNT_ID")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=_get_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_get_env("R2_SECRET_ACCESS_KEY"),
        config=BotoConfig(
            region_name="auto",
            signature_version="s3v4",
        ),
    )


def upload_to_r2(local_path: str | Path) -> tuple[str, str]:
    """Upload a file to Cloudflare R2.

    Args:
        local_path: Path to the local file to upload.

    Returns:
        A tuple of ``(object_key, public_url)`` so the caller can reference
        or delete the object later.

    Raises:
        FileNotFoundError: If *local_path* doesn't exist.
        EnvironmentError: If any R2 credential is missing.
        botocore.exceptions.ClientError: On S3/R2 API errors.
    """
    local_path = Path(local_path)
    if not local_path.is_file():
        raise FileNotFoundError(f"File not found: {local_path}")

    bucket = _get_env("R2_BUCKET_NAME")
    account_id = _get_env("R2_ACCOUNT_ID")

    # Unique key: uuid + original extension  →  "videos/a3b1c2d4.mp4"
    ext = local_path.suffix or ".mp4"
    object_key = f"videos/{uuid.uuid4().hex}{ext}"

    client = _get_client()
    logger.info("Uploading %s → r2://%s/%s", local_path.name, bucket, object_key)

    client.upload_file(
        Filename=str(local_path),
        Bucket=bucket,
        Key=object_key,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    # R2 public URL (requires bucket to have public access enabled, or use
    # a presigned URL).  The URL format follows the R2 public bucket pattern.
    public_url = f"https://{bucket}.{account_id}.r2.cloudflarestorage.com/{object_key}"
    logger.info("Upload complete → %s", public_url)

    return object_key, public_url


def delete_from_r2(object_key: str) -> None:
    """Delete an object from Cloudflare R2.

    Args:
        object_key: The key returned by :func:`upload_to_r2`.

    Silently succeeds if the key doesn't exist (R2/S3 delete is idempotent).
    """
    bucket = _get_env("R2_BUCKET_NAME")
    client = _get_client()

    logger.info("Deleting r2://%s/%s", bucket, object_key)
    client.delete_object(Bucket=bucket, Key=object_key)
    logger.info("Deleted from R2: %s", object_key)
