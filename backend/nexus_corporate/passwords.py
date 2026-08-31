"""Strong password hashing for Corporate admin/owner accounts.

Uses PBKDF2-HMAC-SHA256 with a per-account random salt and a high iteration
count. Secret material (password, salt, hash) is never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

ALGO = "pbkdf2_sha256"
ITERATIONS = 240_000
SALT_BYTES = 16
MIN_PASSWORD_LEN = 12


def hash_password(password: str) -> tuple[str, str, str]:
    """Return (algo, salt_hex, hash_hex)."""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise ValueError("password_too_short")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return ALGO, salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, ITERATIONS)
    return hmac.compare_digest(digest, expected)
