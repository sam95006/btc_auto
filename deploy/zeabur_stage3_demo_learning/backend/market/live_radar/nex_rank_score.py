"""Port of frontend nex_rank_score_v1 + RADAR_ELIGIBILITY_CONTRACT_V1.

Deterministic public display score (0–100). Does not alter Risk Gate / trading.
"""
from __future__ import annotations

from typing import Any

NEX_RANK_SCORE_VERSION = "nex_rank_score_v1"
RADAR_ELIGIBILITY_CONTRACT = "RADAR_ELIGIBILITY_CONTRACT_V1"
FIXED_SYMBOL_DEPENDENCY_COUNT = 0
RANK_HYSTERESIS_SCORE = 2.5
NEX_RANK_RAW_MIN = -78.0
NEX_RANK_RAW_MAX = 90.6

_RADAR_STAGES = frozenset(
    {
        "WATCHING",
        "BUILDING",
        "AWAITING_CONFIRMATION",
        "CONFIRMED",
        "OVEREXTENDED",
        "COOLING",
    }
)

_NON_CRYPTO_TYPES = frozenset({"stock", "commodity"})
_KNOWN_NON_CRYPTO_BASES = frozenset(
    {
        "SOXL",
        "SPCX",
        "SOXS",
        "AAPL",
        "TSLA",
        "NVDA",
        "AMDSTOCK",
        "AMZN",
        "META",
        "GOOGL",
        "MSFT",
        "ARKK",
        "SPY",
        "QQQ",
    }
)


def clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def _base_of(symbol: str) -> str:
    s = str(symbol or "").upper().strip()
    return s[:-4] if s.endswith("USDT") else s


def is_crypto_opportunity(c: dict[str, Any]) -> bool:
    st = str(c.get("symbolType") or "").strip().lower()
    if st in _NON_CRYPTO_TYPES:
        return False
    disp = str(c.get("assetDisposition") or "")
    if disp == "CROSS_ASSET_CONTEXT_ONLY":
        return False
    if _base_of(str(c.get("symbol") or "")) in _KNOWN_NON_CRYPTO_BASES:
        return False
    return True


def is_scanner_visible(c: dict[str, Any]) -> bool:
    return bool(c.get("symbol"))


def count_ready_metrics(c: dict[str, Any]) -> int:
    n = 0
    if c.get("currentPrice") is not None or c.get("markPrice") is not None:
        n += 1
    if c.get("change24hPct") is not None:
        n += 1
    if c.get("priceChange5mPct") is not None:
        n += 1
    if c.get("oiChange5mPct") is not None:
        n += 1
    if c.get("fundingRate") is not None:
        n += 1
    if c.get("turnoverPace") is not None:
        n += 1
    if float(c.get("opportunityScore") or 0) > 0:
        n += 1
    if float(c.get("confirmationScore") or 0) > 0:
        n += 1
    return n


def is_radar_eligible(c: dict[str, Any]) -> bool:
    """RADAR_ELIGIBILITY_CONTRACT_V1 — exclude INSUFFICIENT_DATA/EXPIRED/STALE/UNAVAILABLE."""
    stage = str(c.get("stage") or "")
    if stage in ("INSUFFICIENT_DATA", "EXPIRED"):
        return False
    fresh = str(c.get("freshness") or "").upper()
    if fresh in ("STALE", "UNAVAILABLE"):
        return False
    if stage not in _RADAR_STAGES:
        return False
    warming = bool(c.get("collecting")) or stage == "WATCHING"
    metrics = count_ready_metrics(c)
    if warming and metrics < 3:
        return False
    if metrics < 2:
        return False
    return True


def is_trade_eligible(c: dict[str, Any]) -> bool:
    return (
        str(c.get("stage") or "") == "CONFIRMED"
        and str(c.get("side") or "") != "NEUTRAL"
        and not c.get("collecting")
    )


def compute_nex_rank_score_v1(c: dict[str, Any]) -> dict[str, Any]:
    opportunity = float(c.get("opportunityScore") or 0)
    confirmation = float(c.get("confirmationScore") or 0)
    risk = float(c.get("riskScore") or 0)
    activity = clamp(
        abs(float(c.get("priceChange5mPct") or 0)) * 8 + float(c.get("turnoverPace") or 0) * 0.02,
        0,
        40,
    )
    oi = clamp(abs(float(c.get("oiChange5mPct") or 0)) * 6, 0, 30)
    funding = clamp(abs(float(c.get("fundingRate") or 0)) * 10000, 0, 20)

    raw = (
        opportunity * 0.45
        + confirmation * 0.4
        - risk * 0.25
        + activity * 0.08
        + oi * 0.06
        + funding * 0.03
    )
    if str(c.get("side") or "") == "NEUTRAL":
        raw -= 20
    stage = str(c.get("stage") or "")
    if stage in ("OVEREXTENDED", "EXPIRED", "COOLING"):
        raw -= 8
    if c.get("collecting") or stage == "INSUFFICIENT_DATA":
        raw -= 25

    span = NEX_RANK_RAW_MAX - NEX_RANK_RAW_MIN
    normalized = clamp(((raw - NEX_RANK_RAW_MIN) / span) * 100, 0, 100)
    return {
        "score": round(normalized * 10) / 10,
        "raw": round(raw * 100) / 100,
        "components": {
            "opportunity": opportunity,
            "confirmation": confirmation,
            "risk": risk,
            "activity": round(activity * 10) / 10,
            "oi": round(oi * 10) / 10,
            "funding": round(funding * 10) / 10,
        },
    }


def derive_rank_event(
    rank: int | None,
    previous_rank: int | None,
    still_active: bool,
) -> str:
    if not still_active and previous_rank is not None:
        return "OUT"
    if rank is None:
        return "OUT" if previous_rank is not None else "UNCHANGED"
    if previous_rank is None:
        return "NEW"
    if rank < previous_rank:
        return "UP"
    if rank > previous_rank:
        return "DOWN"
    return "UNCHANGED"


def activity_state(c: dict[str, Any]) -> str:
    if c.get("collecting") or str(c.get("stage") or "") == "INSUFFICIENT_DATA":
        return "WARMING"
    pace = float(c.get("turnoverPace") or 0)
    px = abs(float(c.get("priceChange5mPct") or 0))
    if pace >= 50 or px >= 1.5:
        return "HOT"
    if pace >= 15 or px >= 0.4:
        return "ACTIVE"
    return "QUIET"
