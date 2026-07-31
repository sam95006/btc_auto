"""Honest Bybit Demo fee-rate resolution — never invent silent zeros."""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from typing import Any


FEE_RATE_LIVE = "FEE_RATE_LIVE"
FEE_RATE_CACHED_FRESH = "FEE_RATE_CACHED_FRESH"
FEE_RATE_CONFIGURED_CONSERVATIVE = "FEE_RATE_CONFIGURED_CONSERVATIVE"
FEE_RATE_UNAVAILABLE = "FEE_RATE_UNAVAILABLE"
FEE_RATE_AUTH_FAILED = "FEE_RATE_AUTH_FAILED"
FEE_RATE_SCHEMA_MISMATCH = "FEE_RATE_SCHEMA_MISMATCH"
DEMO_FEE_ENDPOINT_UNSUPPORTED = "DEMO_FEE_ENDPOINT_UNSUPPORTED"
REPLAY_CONFIGURED_CONSERVATIVE = "REPLAY_CONFIGURED_CONSERVATIVE"

_USABLE_STATUSES = {
    FEE_RATE_LIVE,
    FEE_RATE_CACHED_FRESH,
    FEE_RATE_CONFIGURED_CONSERVATIVE,
    REPLAY_CONFIGURED_CONSERVATIVE,
}

_CACHE_TTL_SEC = 300.0
_cache: dict[str, tuple[float, "FeeRateQuote"]] = {}


@dataclass
class FeeRateQuote:
    status: str
    symbol: str
    maker_fee_rate: float | None
    taker_fee_rate: float | None
    fee_source: str
    fee_fetch_error: str | None
    fee_fetched_at: float | None
    fee_freshness_sec: float | None = None
    fail_closed: bool = True
    new_entry_blocked: bool = True
    fee_rate_version: str | None = None
    fee_rate_effective_at: float | None = None
    fee_rate_reviewed_at: float | None = None
    fee_rate_expiry: float | None = None

    @property
    def usable_taker(self) -> float | None:
        if self.status in _USABLE_STATUSES:
            if self.taker_fee_rate is not None and self.taker_fee_rate > 0:
                return float(self.taker_fee_rate)
        return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def configured_conservative_quote(symbol: str) -> FeeRateQuote | None:
    """Founder-gated conservative fallback only — never silent default / never claim LIVE."""
    if not _env_flag("NEXUS_FEE_RATE_CONSERVATIVE_ENABLED"):
        return None
    if not _env_flag("NEXUS_FEE_RATE_CONSERVATIVE_FOUNDER_APPROVED"):
        return None
    try:
        taker = float(os.environ.get("NEXUS_FEE_RATE_CONSERVATIVE_TAKER") or "")
        maker_raw = (os.environ.get("NEXUS_FEE_RATE_CONSERVATIVE_MAKER") or "").strip()
        maker = float(maker_raw) if maker_raw else None
    except ValueError:
        return None
    if taker <= 0:
        return None
    now = time.time()
    version = (os.environ.get("NEXUS_FEE_RATE_VERSION") or "founder-conservative-v1").strip()
    return FeeRateQuote(
        status=FEE_RATE_CONFIGURED_CONSERVATIVE,
        symbol=symbol.upper(),
        maker_fee_rate=maker if maker is not None and maker > 0 else None,
        taker_fee_rate=taker,
        fee_source="FOUNDER_APPROVED_CONFIG",
        fee_fetch_error=None,
        fee_fetched_at=now,
        fee_freshness_sec=0.0,
        fail_closed=False,
        new_entry_blocked=False,
        fee_rate_version=version,
        fee_rate_effective_at=now,
        fee_rate_reviewed_at=now,
        fee_rate_expiry=None,
    )


def replay_conservative_quote(symbol: str, taker: float, *, source: str = "REPLAY_CONFIGURED_CONSERVATIVE") -> FeeRateQuote:
    """Offline replay only — must not become runtime production constant."""
    now = time.time()
    return FeeRateQuote(
        status=REPLAY_CONFIGURED_CONSERVATIVE,
        symbol=symbol.upper(),
        maker_fee_rate=None,
        taker_fee_rate=taker,
        fee_source=source,
        fee_fetch_error=None,
        fee_fetched_at=now,
        fee_freshness_sec=0.0,
        fail_closed=False,
        new_entry_blocked=False,
        fee_rate_version="replay-only",
    )


def unavailable(
    symbol: str,
    *,
    status: str = FEE_RATE_UNAVAILABLE,
    error: str | None = None,
    source: str = "bybit_demo:/v5/account/fee-rate",
) -> FeeRateQuote:
    return FeeRateQuote(
        status=status,
        symbol=symbol.upper(),
        maker_fee_rate=None,
        taker_fee_rate=None,
        fee_source=source,
        fee_fetch_error=error,
        fee_fetched_at=time.time(),
        fee_freshness_sec=None,
        fail_closed=True,
        new_entry_blocked=True,
    )


def classify_demo_fee_error(code: str, detail: str) -> str:
    msg = f"{code} {detail}".lower()
    unsupported = (
        "not support",
        "not supported",
        "unsupported",
        "demo trading does not support",
        "not available for demo",
        "invalid request path",
    )
    auth = ("credentials_missing", "10003", "10004", "10005", "invalid api", "unauthorized", "sign error")
    if any(t in msg for t in unsupported):
        return DEMO_FEE_ENDPOINT_UNSUPPORTED
    if any(t in msg for t in auth):
        return FEE_RATE_AUTH_FAILED
    # Non-zero API error on demo fee-rate without clear auth → unsupported pending docs
    if code == "api_error":
        return DEMO_FEE_ENDPOINT_UNSUPPORTED
    return FEE_RATE_UNAVAILABLE


def cache_get(symbol: str) -> FeeRateQuote | None:
    key = symbol.upper()
    hit = _cache.get(key)
    if not hit:
        return None
    ts, quote = hit
    age = time.time() - ts
    if age > _CACHE_TTL_SEC:
        return None
    if quote.usable_taker is None:
        return None
    return FeeRateQuote(
        status=FEE_RATE_CACHED_FRESH,
        symbol=quote.symbol,
        maker_fee_rate=quote.maker_fee_rate,
        taker_fee_rate=quote.taker_fee_rate,
        fee_source=f"cache:{quote.fee_source}",
        fee_fetch_error=None,
        fee_fetched_at=quote.fee_fetched_at,
        fee_freshness_sec=age,
        fail_closed=False,
        new_entry_blocked=False,
        fee_rate_version=quote.fee_rate_version,
    )


def cache_put(quote: FeeRateQuote) -> None:
    if quote.usable_taker is None or quote.status != FEE_RATE_LIVE:
        return
    _cache[quote.symbol.upper()] = (time.time(), quote)


def clear_fee_cache() -> None:
    _cache.clear()


def parse_fee_rows(rows: list[dict[str, Any]], symbol: str) -> FeeRateQuote:
    if not rows:
        return unavailable(symbol, status=FEE_RATE_SCHEMA_MISMATCH, error="empty_fee_list")
    row = rows[0] if isinstance(rows[0], dict) else {}
    maker_raw = row.get("makerFeeRate")
    taker_raw = row.get("takerFeeRate")
    try:
        maker = float(maker_raw) if maker_raw is not None and str(maker_raw).strip() != "" else None
        taker = float(taker_raw) if taker_raw is not None and str(taker_raw).strip() != "" else None
    except (TypeError, ValueError):
        return unavailable(
            symbol,
            status=FEE_RATE_SCHEMA_MISMATCH,
            error=f"parse_error maker={maker_raw!r} taker={taker_raw!r}",
        )
    if taker is None or taker <= 0:
        return unavailable(
            symbol,
            status=FEE_RATE_SCHEMA_MISMATCH,
            error=f"taker_nonpositive value={taker_raw!r}",
        )
    now = time.time()
    quote = FeeRateQuote(
        status=FEE_RATE_LIVE,
        symbol=symbol.upper(),
        maker_fee_rate=maker if maker is not None and maker >= 0 else None,
        taker_fee_rate=taker,
        fee_source="bybit_demo:/v5/account/fee-rate",
        fee_fetch_error=None,
        fee_fetched_at=now,
        fee_freshness_sec=0.0,
        fail_closed=False,
        new_entry_blocked=False,
    )
    cache_put(quote)
    return quote
