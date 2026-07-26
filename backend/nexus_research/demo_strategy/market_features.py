"""Demo strategy — market feature extraction.

Accepts scanner/candidate-like structures or fixtures and extracts
a normalised feature dict for the strategy evaluator.

Pure local computation. No API calls, no secrets.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

RESEARCH_ONLY: bool = True


@dataclass(frozen=True)
class MarketFeatures:
    """Immutable snapshot of features extracted from market data."""

    symbol: str
    regime: str  # TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE, UNKNOWN
    trend_score: float  # -100..+100
    momentum_score: float  # -100..+100
    rsi_14: float | None  # 0..100
    atr_pct: float | None  # ATR as % of price
    funding_rate_8h_pct: float | None
    open_interest_usd: float | None
    volume_24h_usd: float | None
    spread_bps: float | None
    freshness_ms: int  # age of the underlying data
    source: str  # "live" | "fixture" | "scanner"
    extracted_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def is_stale(self, max_age_ms: int = 120_000) -> bool:
        return self.freshness_ms > max_age_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "regime": self.regime,
            "trendScore": self.trend_score,
            "momentumScore": self.momentum_score,
            "rsi14": self.rsi_14,
            "atrPct": self.atr_pct,
            "fundingRate8hPct": self.funding_rate_8h_pct,
            "openInterestUsd": self.open_interest_usd,
            "volume24hUsd": self.volume_24h_usd,
            "spreadBps": self.spread_bps,
            "freshnessMs": self.freshness_ms,
            "source": self.source,
            "extractedAtMs": self.extracted_at_ms,
            "researchOnly": True,
        }


def _classify_regime(
    trend: float,
    momentum: float,
    rsi: float | None,
    atr_pct: float | None,
) -> str:
    if atr_pct is not None and atr_pct > 3.0:
        return "VOLATILE"
    if trend > 30 and momentum > 20:
        return "TRENDING_UP"
    if trend < -30 and momentum < -20:
        return "TRENDING_DOWN"
    if abs(trend) < 15 and abs(momentum) < 15:
        return "RANGING"
    return "UNKNOWN"


def _safe_float(val: Any, default: float | None = None) -> float | None:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def extract_features(
    data: dict[str, Any],
    *,
    source: str = "scanner",
) -> MarketFeatures:
    """Extract MarketFeatures from a scanner/candidate dict or fixture.

    Expected keys (all optional with sensible defaults):
      symbol, trend_score / trendScore, momentum_score / momentumScore,
      rsi_14 / rsi14 / rsi, atr_pct / atrPct / atr,
      funding_rate / fundingRate8hPct, open_interest / openInterestUsd,
      volume_24h / volume24hUsd, spread_bps / spreadBps,
      data_age_ms / freshnessMs / dataAgeMs
    """
    symbol = str(data.get("symbol", "UNKNOWN"))

    trend = _safe_float(
        data.get("trend_score") or data.get("trendScore"), 0.0
    ) or 0.0
    trend = max(-100.0, min(100.0, trend))

    momentum = _safe_float(
        data.get("momentum_score") or data.get("momentumScore"), 0.0
    ) or 0.0
    momentum = max(-100.0, min(100.0, momentum))

    rsi = _safe_float(
        data.get("rsi_14") or data.get("rsi14") or data.get("rsi")
    )
    if rsi is not None:
        rsi = max(0.0, min(100.0, rsi))

    atr_pct = _safe_float(
        data.get("atr_pct") or data.get("atrPct") or data.get("atr")
    )

    funding = _safe_float(
        data.get("funding_rate") or data.get("fundingRate8hPct")
        or data.get("funding_rate_8h_pct")
    )

    oi = _safe_float(
        data.get("open_interest") or data.get("openInterestUsd")
        or data.get("open_interest_usd")
    )

    volume = _safe_float(
        data.get("volume_24h") or data.get("volume24hUsd")
        or data.get("volume_24h_usd")
    )

    spread = _safe_float(
        data.get("spread_bps") or data.get("spreadBps")
    )

    freshness = int(
        _safe_float(
            data.get("data_age_ms") or data.get("freshnessMs")
            or data.get("dataAgeMs"),
            0.0,
        ) or 0
    )

    regime = data.get("regime") or _classify_regime(trend, momentum, rsi, atr_pct)

    return MarketFeatures(
        symbol=symbol,
        regime=regime,
        trend_score=trend,
        momentum_score=momentum,
        rsi_14=rsi,
        atr_pct=atr_pct,
        funding_rate_8h_pct=funding,
        open_interest_usd=oi,
        volume_24h_usd=volume,
        spread_bps=spread,
        freshness_ms=freshness,
        source=source,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

FIXTURE_BTCUSDT: dict[str, Any] = {
    "symbol": "BTCUSDT",
    "trend_score": 45.0,
    "momentum_score": 32.0,
    "rsi_14": 58.0,
    "atr_pct": 1.8,
    "funding_rate": 0.01,
    "open_interest": 12_500_000_000.0,
    "volume_24h": 28_000_000_000.0,
    "spread_bps": 1.2,
    "data_age_ms": 5000,
}

FIXTURE_ETHUSDT: dict[str, Any] = {
    "symbol": "ETHUSDT",
    "trend_score": 28.0,
    "momentum_score": 18.0,
    "rsi_14": 52.0,
    "atr_pct": 2.3,
    "funding_rate": 0.008,
    "open_interest": 8_200_000_000.0,
    "volume_24h": 15_000_000_000.0,
    "spread_bps": 2.1,
    "data_age_ms": 5500,
}

FIXTURE_SOLUSDT: dict[str, Any] = {
    "symbol": "SOLUSDT",
    "trend_score": 55.0,
    "momentum_score": 48.0,
    "rsi_14": 64.0,
    "atr_pct": 3.5,
    "funding_rate": 0.015,
    "open_interest": 2_800_000_000.0,
    "volume_24h": 5_500_000_000.0,
    "spread_bps": 3.8,
    "data_age_ms": 6000,
}
