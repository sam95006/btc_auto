"""In-memory auth API rate limiter for the public identity realm."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from backend.nexus_public_auth.constants import RATE_LIMIT_DEFAULTS, RATE_LIMIT_WINDOW_SECONDS
from backend.nexus_public_auth.hard_bans import HardBanViolation


class RateLimitExceeded(HardBanViolation):
    """Raised when an auth endpoint exceeds its configured rate limit."""


class AuthRateLimiter:
    """Sliding-window style counter keyed by (bucket, subject)."""

    def __init__(
        self,
        *,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
        limits: Optional[dict[str, int]] = None,
    ):
        self.window_seconds = int(window_seconds)
        self.limits = dict(limits or RATE_LIMIT_DEFAULTS)
        self._lock = threading.RLock()
        self._hits: dict[tuple[str, str], list[float]] = {}

    def check(self, bucket: str, subject: str) -> dict[str, Any]:
        limit = int(self.limits.get(bucket, 30))
        now = time.monotonic()
        normalized_subject = (subject or "").strip().lower() or "anonymous"
        # Collapse whitespace-only / empty subjects so they cannot bypass limits.
        key = (bucket, normalized_subject)
        with self._lock:
            stamps = [t for t in self._hits.get(key, []) if now - t < self.window_seconds]
            if len(stamps) >= limit:
                self._hits[key] = stamps
                raise RateLimitExceeded(
                    f"rate limit exceeded: bucket={bucket} subject={normalized_subject} "
                    f"limit={limit}/{self.window_seconds}s"
                )
            stamps.append(now)
            self._hits[key] = stamps
            remaining = max(0, limit - len(stamps))
            return {
                "bucket": bucket,
                "subject": normalized_subject,
                "limit": limit,
                "window_seconds": self.window_seconds,
                "used": len(stamps),
                "remaining": remaining,
                "ok": True,
            }

    def reset(self, bucket: Optional[str] = None, subject: Optional[str] = None) -> None:
        with self._lock:
            if bucket is None and subject is None:
                self._hits.clear()
                return
            for key in list(self._hits.keys()):
                b, s = key
                if bucket is not None and b != bucket:
                    continue
                if subject is not None and s != subject:
                    continue
                del self._hits[key]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "window_seconds": self.window_seconds,
                "limits": dict(self.limits),
                "tracked_keys": len(self._hits),
            }


_DEFAULT_LIMITER: Optional[AuthRateLimiter] = None
_DEFAULT_LOCK = threading.Lock()


def get_default_rate_limiter() -> AuthRateLimiter:
    global _DEFAULT_LIMITER
    with _DEFAULT_LOCK:
        if _DEFAULT_LIMITER is None:
            _DEFAULT_LIMITER = AuthRateLimiter()
        return _DEFAULT_LIMITER


def reset_default_rate_limiter() -> AuthRateLimiter:
    global _DEFAULT_LIMITER
    with _DEFAULT_LOCK:
        _DEFAULT_LIMITER = AuthRateLimiter()
        return _DEFAULT_LIMITER
