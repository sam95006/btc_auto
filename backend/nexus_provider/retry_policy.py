"""Retry-After / rate-limit reset parsing and jittered exponential backoff."""
from __future__ import annotations

import email.utils
import random
import re
import time
from datetime import datetime, timezone
from typing import Any, Mapping


_HTTP_DATE_RE = re.compile(r"^[A-Za-z]{3},")


def parse_retry_after(
    headers: Mapping[str, Any] | None,
    *,
    now: float | None = None,
    default_s: float | None = None,
    max_s: float = 3600.0,
) -> float | None:
    """Parse Retry-After as seconds or HTTP-date. Returns seconds until resume."""
    if not headers:
        return default_s
    raw = None
    for k, v in headers.items():
        if str(k).lower() == "retry-after":
            raw = v
            break
    if raw is None or raw == "":
        return default_s
    s = str(raw).strip()
    try:
        seconds = float(s)
        return max(0.0, min(max_s, seconds))
    except (TypeError, ValueError):
        pass
    if _HTTP_DATE_RE.match(s) or "-" in s:
        try:
            dt = email.utils.parsedate_to_datetime(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            base = time.time() if now is None else now
            delta = dt.timestamp() - base
            if delta < 0:
                # Stale Retry-After → treat as immediate-but-bounded floor
                return 0.0 if default_s is None else min(default_s, max_s)
            return max(0.0, min(max_s, delta))
        except (TypeError, ValueError, OverflowError):
            return default_s
    return default_s


def parse_rate_limit_reset(
    headers: Mapping[str, Any] | None,
    *,
    now: float | None = None,
    max_s: float = 3600.0,
) -> float | None:
    """Parse x-ratelimit-reset(-requests|-tokens) as unix epoch or relative seconds."""
    if not headers:
        return None
    candidates = (
        "x-ratelimit-reset",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "ratelimit-reset",
    )
    lower = {str(k).lower(): v for k, v in headers.items()}
    raw = None
    for c in candidates:
        if c in lower and lower[c] not in (None, ""):
            raw = lower[c]
            break
    if raw is None:
        return None
    try:
        val = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    base = time.time() if now is None else now
    # Epoch vs relative: epochs are >> 1e9
    if val > 1_000_000_000:
        delta = val - base
        if delta < 0:
            return 0.0
        return min(max_s, delta)
    return max(0.0, min(max_s, val))


def backoff_with_jitter(
    attempt: int,
    *,
    base_s: float = 1.0,
    factor: float = 2.0,
    max_s: float = 300.0,
    jitter_ratio: float = 0.25,
    rng: random.Random | None = None,
) -> float:
    """Exponential backoff with bounded symmetric jitter. attempt is 0-indexed."""
    a = max(0, int(attempt))
    raw = min(max_s, base_s * (factor ** a))
    jr = max(0.0, min(1.0, float(jitter_ratio)))
    if jr <= 0:
        return raw
    r = rng or random
    delta = raw * jr
    return max(0.0, min(max_s, raw + r.uniform(-delta, delta)))


def next_resume_iso(
    delay_s: float,
    *,
    now_dt: datetime | None = None,
) -> str:
    now_dt = now_dt or datetime.now(timezone.utc)
    from datetime import timedelta

    return (now_dt + timedelta(seconds=max(0.0, float(delay_s)))).strftime("%Y-%m-%dT%H:%M:%SZ")
