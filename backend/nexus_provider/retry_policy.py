"""Canonical provider retry authority.

Owns Retry-After / quota-reset parsing, jittered exponential backoff,
max-retry bounds, and next-resume timestamp formatting.

Provider-specific VALUES (bucket sizes, default waits, cooldown seconds)
may differ by profile. Algorithm AUTHORITY must not — all lanes import here.
"""
from __future__ import annotations

import email.utils
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Canonical policy constants (values may be overridden per-provider at call site)
# ---------------------------------------------------------------------------
DEFAULT_RETRY_AFTER_S = 900.0
MAX_BACKOFF_S = 300.0
MAX_PROVIDER_RETRIES = 5
DEFAULT_BACKOFF_BASE_S = 1.0
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_JITTER_RATIO = 0.25

_HTTP_DATE_RE = re.compile(r"^[A-Za-z]{3},")
_BODY_RETRY_MARKERS = (
    "try again in ",
    "retry after ",
    "please retry after ",
    "please try again in ",
)


def _as_epoch(now: float | datetime | None) -> float:
    if now is None:
        return time.time()
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.timestamp()
    return float(now)


def _as_datetime(now: float | datetime | None) -> datetime:
    if isinstance(now, datetime):
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now
    return datetime.fromtimestamp(_as_epoch(now), tz=timezone.utc)


def _header_map(headers: Mapping[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not headers:
        return out
    for k, v in headers.items():
        if k is None or v is None or v == "":
            continue
        out[str(k).lower()] = str(v).strip()
    return out


def _parse_body_retry_seconds(body: str | None) -> float | None:
    if not body:
        return None
    low = body.lower()
    for marker in _BODY_RETRY_MARKERS:
        idx = low.find(marker)
        if idx < 0:
            continue
        frag = low[idx + len(marker) : idx + len(marker) + 32]
        num = ""
        for ch in frag:
            if ch.isdigit() or ch == ".":
                num += ch
            elif num:
                break
        if num:
            try:
                return max(0.0, float(num))
            except ValueError:
                continue
    return None


def parse_retry_after(
    headers: Mapping[str, Any] | None,
    *,
    body: str | None = None,
    now: float | datetime | None = None,
    default_s: float | None = DEFAULT_RETRY_AFTER_S,
    max_s: float = 3600.0,
) -> float | None:
    """Parse Retry-After (seconds or HTTP-date) into seconds until resume.

    Also accepts ``x-retry-after``. When Retry-After is absent, falls through
    to rate-limit reset headers and common provider body phrases.
    """
    hdrs = _header_map(headers)
    base = _as_epoch(now)

    for key in ("retry-after", "x-retry-after"):
        raw = hdrs.get(key)
        if not raw:
            continue
        try:
            return max(0.0, min(max_s, float(raw)))
        except (TypeError, ValueError):
            pass
        if _HTTP_DATE_RE.match(raw) or "-" in raw:
            try:
                dt = email.utils.parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                delta = dt.timestamp() - base
                if delta < 0:
                    return 0.0 if default_s is None else min(float(default_s), max_s)
                return max(0.0, min(max_s, delta))
            except (TypeError, ValueError, OverflowError):
                continue

    reset = parse_rate_limit_reset(headers, now=base, max_s=max_s)
    if reset is not None:
        return reset

    body_wait = _parse_body_retry_seconds(body)
    if body_wait is not None:
        return max(0.0, min(max_s, body_wait))

    return None if default_s is None else max(0.0, min(max_s, float(default_s)))


def parse_rate_limit_reset(
    headers: Mapping[str, Any] | None,
    *,
    now: float | datetime | None = None,
    max_s: float = 3600.0,
) -> float | None:
    """Parse x-ratelimit-reset(-requests|-tokens) as unix epoch or relative seconds."""
    hdrs = _header_map(headers)
    if not hdrs:
        return None
    candidates = (
        "x-ratelimit-reset",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "ratelimit-reset",
    )
    raw = None
    for c in candidates:
        if c in hdrs and hdrs[c] not in (None, ""):
            raw = hdrs[c]
            break
    if raw is None:
        return None
    try:
        val = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    base = _as_epoch(now)
    # Epoch vs relative: epochs are >> 1e9
    if val > 1_000_000_000:
        delta = val - base
        if delta < 0:
            return 0.0
        return min(max_s, delta)
    return max(0.0, min(max_s, val))


def parse_quota_reset_at(
    headers: Mapping[str, Any] | None,
    *,
    now: float | datetime | None = None,
) -> datetime | None:
    """Return absolute UTC datetime when provider quota resets, if advertised."""
    now_dt = _as_datetime(now)
    hdrs = _header_map(headers)
    if not hdrs:
        return None
    for key in (
        "x-ratelimit-reset",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "ratelimit-reset",
    ):
        raw = hdrs.get(key)
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        if val > 1_000_000_000:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        return now_dt + timedelta(seconds=val)
    raw = hdrs.get("retry-after") or hdrs.get("x-retry-after")
    if raw:
        try:
            return now_dt + timedelta(seconds=float(raw))
        except ValueError:
            try:
                dt = email.utils.parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError, OverflowError):
                return None
    return None


def backoff_with_jitter(
    attempt: int,
    *,
    base_s: float = DEFAULT_BACKOFF_BASE_S,
    factor: float = DEFAULT_BACKOFF_FACTOR,
    max_s: float = MAX_BACKOFF_S,
    jitter_ratio: float = DEFAULT_JITTER_RATIO,
    rng: random.Random | None = None,
    # Compatibility alias used by edge-discovery callers
    cap_s: float | None = None,
) -> float:
    """Exponential backoff with bounded symmetric jitter. attempt is 0-indexed."""
    if cap_s is not None:
        max_s = float(cap_s)
    a = max(0, int(attempt))
    raw = min(max_s, base_s * (factor ** a))
    jr = max(0.0, min(1.0, float(jitter_ratio)))
    if jr <= 0:
        return raw
    r = rng or random
    delta = raw * jr
    return max(0.0, min(max_s, raw + r.uniform(-delta, delta)))


def exponential_backoff_with_jitter(
    attempt: int,
    *,
    base_s: float = DEFAULT_BACKOFF_BASE_S,
    factor: float = DEFAULT_BACKOFF_FACTOR,
    max_s: float = MAX_BACKOFF_S,
    jitter_ratio: float = DEFAULT_JITTER_RATIO,
    rng: random.Random | None = None,
    cap_s: float | None = None,
) -> float:
    """Canonical alias — same algorithm as ``backoff_with_jitter``."""
    return backoff_with_jitter(
        attempt,
        base_s=base_s,
        factor=factor,
        max_s=max_s,
        jitter_ratio=jitter_ratio,
        rng=rng,
        cap_s=cap_s,
    )


def compute_resume_wait_s(
    headers: Mapping[str, Any] | None = None,
    *,
    body: str | None = None,
    now: float | datetime | None = None,
    default_s: float = DEFAULT_RETRY_AFTER_S,
    max_s: float = 3600.0,
) -> float:
    """Combine Retry-After + quota reset into a single wait (seconds)."""
    now_dt = _as_datetime(now)
    wait = parse_retry_after(
        headers, body=body, now=now_dt, default_s=default_s, max_s=max_s
    )
    wait_f = float(wait if wait is not None else default_s)
    reset_at = parse_quota_reset_at(headers, now=now_dt)
    if reset_at is not None:
        wait_f = max(wait_f, (reset_at - now_dt).total_seconds())
    return max(0.0, min(max_s, wait_f))


def next_resume_iso(
    delay_s: float,
    *,
    now_dt: datetime | None = None,
) -> str:
    now_dt = now_dt or datetime.now(timezone.utc)
    return (now_dt + timedelta(seconds=max(0.0, float(delay_s)))).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def retries_exhausted(attempt: int, *, max_retries: int = MAX_PROVIDER_RETRIES) -> bool:
    """True when attempt count (0-indexed failures so far) has hit the ceiling."""
    return int(attempt) >= int(max_retries)
