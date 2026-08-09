"""Secure password hashing for public member identity (stdlib PBKDF2)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Tuple

# OWASP-aligned PBKDF2 parameters for non-production paid-beta identity.
_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 310_000
_SALT_BYTES = 16
_DK_LEN = 32


def hash_password(password: str) -> str:
    """Return storable hash string: pbkdf2_sha256$iterations$salt_hex$digest_hex."""
    raw = (password or "").encode("utf-8")
    if len(raw) < 8:
        raise ValueError("password must be at least 8 characters")
    if len(raw) > 256:
        raise ValueError("password too long")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGO, raw, salt, _PBKDF2_ITERATIONS, dklen=_DK_LEN
    )
    return (
        f"pbkdf2_{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify against stored PBKDF2 hash. Never logs plaintext."""
    try:
        scheme, iters_s, salt_hex, digest_hex = (stored or "").split("$", 3)
    except ValueError:
        return False
    if not scheme.startswith("pbkdf2_"):
        return False
    algo = scheme.removeprefix("pbkdf2_")
    try:
        iterations = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac(
        algo, (password or "").encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    return hmac.compare_digest(candidate, expected)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def split_hash_meta(stored: str) -> Tuple[str, int]:
    """Return (scheme, iterations) for diagnostics — never the digest."""
    parts = (stored or "").split("$")
    if len(parts) < 2:
        return ("unknown", 0)
    try:
        return (parts[0], int(parts[1]))
    except ValueError:
        return (parts[0], 0)
