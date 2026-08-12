"""Founder-approved Bybit Demo conservative fee policy + expiry."""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


FEE_RATE_LIVE = "FEE_RATE_LIVE"
FEE_RATE_CACHED_FRESH = "FEE_RATE_CACHED_FRESH"
FEE_RATE_CONFIGURED_CONSERVATIVE = "FEE_RATE_CONFIGURED_CONSERVATIVE"
FEE_RATE_CONFIG_EXPIRED = "FEE_RATE_CONFIG_EXPIRED"
FEE_RATE_CONFIG_REVIEW_REQUIRED = "FEE_RATE_CONFIG_REVIEW_REQUIRED"
FEE_RATE_UNAVAILABLE = "FEE_RATE_UNAVAILABLE"
FEE_RATE_AUTH_FAILED = "FEE_RATE_AUTH_FAILED"
FEE_RATE_SCHEMA_MISMATCH = "FEE_RATE_SCHEMA_MISMATCH"
DEMO_FEE_ENDPOINT_UNSUPPORTED = "DEMO_FEE_ENDPOINT_UNSUPPORTED"
REPLAY_CONFIGURED_CONSERVATIVE = "REPLAY_CONFIGURED_CONSERVATIVE"

# Pretrade always assumes taker both sides (Founder policy).
PRETRADE_ENTRY_LIQUIDITY_ASSUMPTION = "TAKER"
PRETRADE_EXIT_LIQUIDITY_ASSUMPTION = "TAKER"

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
    fee_account_specific: bool = False
    fee_live_private_api: bool = False
    fee_endpoint_supported: bool | None = None
    pretrade_entry_fee_rate: float | None = None
    pretrade_exit_fee_rate: float | None = None
    pretrade_round_trip_fee_rate: float | None = None
    pretrade_entry_liquidity_assumption: str = PRETRADE_ENTRY_LIQUIDITY_ASSUMPTION
    pretrade_exit_liquidity_assumption: str = PRETRADE_EXIT_LIQUIDITY_ASSUMPTION

    @property
    def usable_taker(self) -> float | None:
        if self.status in _USABLE_STATUSES:
            if self.taker_fee_rate is not None and self.taker_fee_rate > 0:
                return float(self.taker_fee_rate)
        return None

    @property
    def pretrade_fee_rate(self) -> float | None:
        """Rate used for pretrade cost gate — always taker when usable."""
        return self.usable_taker

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    return None


def review_by_date() -> date | None:
    return _parse_date(os.environ.get("NEXUS_FEE_RATE_REVIEW_BY") or "2026-08-31")


def config_is_expired(*, today: date | None = None) -> bool:
    rb = review_by_date()
    if rb is None:
        return False
    return (today or date.today()) > rb


def _apply_pretrade_taker_both_sides(quote: FeeRateQuote) -> FeeRateQuote:
    taker = quote.usable_taker
    if taker is None:
        quote.pretrade_entry_fee_rate = None
        quote.pretrade_exit_fee_rate = None
        quote.pretrade_round_trip_fee_rate = None
        return quote
    quote.pretrade_entry_fee_rate = taker
    quote.pretrade_exit_fee_rate = taker
    quote.pretrade_round_trip_fee_rate = taker * 2.0
    quote.pretrade_entry_liquidity_assumption = PRETRADE_ENTRY_LIQUIDITY_ASSUMPTION
    quote.pretrade_exit_liquidity_assumption = PRETRADE_EXIT_LIQUIDITY_ASSUMPTION
    return quote


def configured_conservative_quote(symbol: str) -> FeeRateQuote | None:
    """Founder-gated conservative fallback — never claim LIVE / account-specific."""
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
    source = (os.environ.get("NEXUS_FEE_RATE_SOURCE") or "FOUNDER_APPROVED_CONFIG").strip()
    review = review_by_date()
    expiry_ts = time.mktime(datetime.combine(review, datetime.min.time()).timetuple()) if review else None

    if config_is_expired():
        return FeeRateQuote(
            status=FEE_RATE_CONFIG_EXPIRED,
            symbol=symbol.upper(),
            maker_fee_rate=maker if maker is not None and maker > 0 else None,
            taker_fee_rate=taker,
            fee_source=source,
            fee_fetch_error="fee_config_expired_review_required",
            fee_fetched_at=now,
            fee_freshness_sec=0.0,
            fail_closed=True,
            new_entry_blocked=True,
            fee_rate_version=version,
            fee_rate_effective_at=now,
            fee_rate_reviewed_at=now,
            fee_rate_expiry=expiry_ts,
            fee_account_specific=False,
            fee_live_private_api=False,
            fee_endpoint_supported=False,
        )

    quote = FeeRateQuote(
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
        fee_rate_expiry=expiry_ts,
        fee_account_specific=False,
        fee_live_private_api=False,
        fee_endpoint_supported=False,
    )
    return _apply_pretrade_taker_both_sides(quote)


def fee_policy_public_status() -> dict[str, Any]:
    """UI-facing fee policy — never claim LIVE when using conservative config."""
    q = configured_conservative_quote("BTCUSDT")
    if q is None:
        return {
            "fee_endpoint_supported": False,
            "fee_rate_status": DEMO_FEE_ENDPOINT_UNSUPPORTED,
            "fee_source": "UNAVAILABLE",
            "fee_account_specific": False,
            "fee_live_private_api": False,
            "fee_version": os.environ.get("NEXUS_FEE_RATE_VERSION") or "UNAVAILABLE",
            "new_entry_blocked": True,
            "note": "founder_conservative_not_enabled_or_not_approved",
        }
    return {
        "fee_endpoint_supported": False,
        "fee_rate_status": q.status,
        "fee_source": q.fee_source,
        "fee_account_specific": False,
        "fee_live_private_api": False,
        "fee_version": q.fee_rate_version,
        "taker_fee_rate": q.taker_fee_rate,
        "maker_fee_rate": q.maker_fee_rate,
        "pretrade_round_trip_fee_rate": q.pretrade_round_trip_fee_rate,
        "pretrade_entry_liquidity_assumption": q.pretrade_entry_liquidity_assumption,
        "pretrade_exit_liquidity_assumption": q.pretrade_exit_liquidity_assumption,
        "fee_config_expiry": os.environ.get("NEXUS_FEE_RATE_REVIEW_BY") or "2026-08-31",
        "new_entry_blocked": q.new_entry_blocked,
        "ui_label": "Founder 核准保守設定（非帳戶即時費率）",
    }


def replay_conservative_quote(symbol: str, taker: float, *, source: str = "REPLAY_CONFIGURED_CONSERVATIVE") -> FeeRateQuote:
    now = time.time()
    quote = FeeRateQuote(
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
        fee_account_specific=False,
        fee_live_private_api=False,
        fee_endpoint_supported=False,
    )
    return _apply_pretrade_taker_both_sides(quote)


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
        fee_account_specific=False,
        fee_live_private_api=False,
        fee_endpoint_supported=False if status == DEMO_FEE_ENDPOINT_UNSUPPORTED else None,
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
    out = FeeRateQuote(
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
        fee_account_specific=False,
        fee_live_private_api=True,
        fee_endpoint_supported=True,
    )
    return _apply_pretrade_taker_both_sides(out)


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
        fee_account_specific=True,
        fee_live_private_api=True,
        fee_endpoint_supported=True,
    )
    cache_put(quote)
    return _apply_pretrade_taker_both_sides(quote)
