"""Deterministic multi-symbol / multi-volatility synthetic universe.

System-correctness fixtures only — no edge, no profitability, no OOS.
"""
from __future__ import annotations

from typing import Any

SYMBOLS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
)

VOL_REGIMES: tuple[str, ...] = (
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRISIS",
)

# Relative spread / path width multipliers by regime (synthetic only).
REGIME_SPREAD_MULT: dict[str, float] = {
    "LOW": 1.0,
    "MEDIUM": 2.0,
    "HIGH": 4.0,
    "CRISIS": 8.0,
}

# Liquidity collapse: extreme spread + blocked new entries (fail-closed).
LIQUIDITY_COLLAPSE_SPREAD_MULT = 50.0


def day_index(step: int, total_steps: int, logical_days: int = 365) -> int:
    """Map candidate step → logical day [0, logical_days)."""
    if total_steps <= 0:
        return 0
    return min(logical_days - 1, int(step * logical_days / total_steps))


def symbol_for_day(day: int) -> str:
    return SYMBOLS[day % len(SYMBOLS)]


def regime_for_day(day: int) -> str:
    # Rotate regimes in 30-day blocks with a crisis spike every 90th day.
    if day > 0 and day % 90 == 0:
        return "CRISIS"
    block = (day // 30) % (len(VOL_REGIMES) - 1)  # LOW/MED/HIGH cycling
    return VOL_REGIMES[block]


def build_lifecycle_candidates(
    count: int,
    *,
    seed: int,
    logical_days: int = 365,
) -> list[dict[str, Any]]:
    """Build multi-symbol multi-regime candidates for the accelerated session."""
    out: list[dict[str, Any]] = []
    for i in range(count):
        day = day_index(i, count, logical_days)
        symbol = symbol_for_day(day)
        regime = regime_for_day(day)
        base = 100.0 + ((i * 7 + seed) % 200) * 0.5
        collapse = i % 61 == 0  # periodic liquidity collapse days
        spread_mult = (
            LIQUIDITY_COLLAPSE_SPREAD_MULT if collapse else REGIME_SPREAD_MULT[regime]
        )
        cand: dict[str, Any] = {
            "candidate_id": f"LC365_{i:06d}",
            "idempotency_key": f"LC365K_{seed}_{i:06d}",
            "symbol": symbol,
            "side": "BUY" if i % 2 == 0 else "SELL",
            "mark_price": base,
            "order_type": "market",
            "lose": i % 3 == 0,
            "logical_day": day,
            "vol_regime": regime,
            "spread_mult": spread_mult,
            "liquidity_collapse": collapse,
            # System correctness only — never claim edge / PnL as signal.
            "system_correctness_only": True,
            "edge_claim": False,
            "profitability_measured": False,
        }
        # Provider traffic so outage injections fire.
        if i % 17 == 0:
            cand["uses_provider"] = True
            cand["provider"] = "GROQ"
        elif i % 19 == 0:
            cand["uses_provider"] = True
            cand["provider"] = "SAMBANOVA"
        # Liquidity collapse: skip live fill path by marking blocked entry.
        if collapse:
            cand["liquidity_status"] = "COLLAPSED"
            cand["block_new_entry"] = True
        out.append(cand)
    return out


def universe_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    symbols = sorted({c.get("symbol") for c in candidates})
    regimes = sorted({c.get("vol_regime") for c in candidates})
    collapses = sum(1 for c in candidates if c.get("liquidity_collapse"))
    days = sorted({int(c.get("logical_day", 0)) for c in candidates})
    return {
        "symbol_count": len(symbols),
        "symbols": symbols,
        "vol_regimes": regimes,
        "vol_regime_count": len(regimes),
        "liquidity_collapse_events": collapses,
        "logical_day_span": {
            "min": days[0] if days else 0,
            "max": days[-1] if days else 0,
            "distinct_days": len(days),
        },
    }


__all__ = [
    "LIQUIDITY_COLLAPSE_SPREAD_MULT",
    "REGIME_SPREAD_MULT",
    "SYMBOLS",
    "VOL_REGIMES",
    "build_lifecycle_candidates",
    "day_index",
    "regime_for_day",
    "symbol_for_day",
    "universe_summary",
]
