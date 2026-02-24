# filepath: backend/encryption.py
"""
Application-layer encryption for sensitive data (API keys, tokens).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the ``cryptography`` library.
The encryption key is derived from ``JWT_SECRET_KEY`` via PBKDF2-HMAC-SHA256
so there's no additional secret to manage.

Usage::

    from backend.encryption import encrypt, decrypt

    ciphertext = encrypt("sk-live-abc123")
    plaintext  = decrypt(ciphertext)
"""

from __future__ import annotations

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from backend.config import get_settings

logger = logging.getLogger("tubevo.backend.encryption")

# Fixed salt — changing this invalidates all encrypted data.
# In a perfect world this would be a separate env var, but deriving
# the Fernet key from JWT_SECRET_KEY + a fixed salt is already a
# massive improvement over storing API keys as plaintext.
_SALT = b"tubevo-api-key-encryption-v1"


def _derive_fernet_key() -> bytes:
    """Derive a 32-byte Fernet key from the JWT secret."""
    secret = get_settings().jwt_secret_key
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY must be set for encryption.")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance."""
    global _fernet_instance
    if _fernet_instance is None:
        _fernet_instance = Fernet(_derive_fernet_key())
    return _fernet_instance


_fernet_instance: Fernet | None = None


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string and return a URL-safe base64 ciphertext."""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext string back to plaintext.

    Returns an empty string if decryption fails (e.g. key rotation,
    corrupted data, or the value was stored before encryption was enabled).
    """
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as e:
        # If we can't decrypt, the value may be a legacy plaintext key.
        # Log a warning and return the raw value so existing users aren't locked out.
        logger.warning("Decryption failed (legacy plaintext key?): %s", type(e).__name__)
        return ciphertext
