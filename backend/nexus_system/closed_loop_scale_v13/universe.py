"""Multi-symbol / multi-regime synthetic universe for V13-G closed-loop scale.

System correctness only — no edge, no profitability, no OOS.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

SYMBOLS: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
)

# Lot-compliant qty per symbol (see backend.nexus_execution.instrument.DEFAULT_INSTRUMENTS).
# Sized to clear min_notional=5 at synthetic mark≈100.
SYMBOL_QTY: dict[str, str] = {
    "BTCUSDT": "0.1",
    "ETHUSDT": "0.1",
    "SOLUSDT": "0.1",
    "XRPUSDT": "1",
}

VOL_REGIMES: tuple[str, ...] = (
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRISIS",
)

REGIME_SPREAD_MULT: dict[str, float] = {
    "LOW": 1.0,
    "MEDIUM": 2.0,
    "HIGH": 4.0,
    "CRISIS": 8.0,
}

HISTORICAL_START = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _day_index(step: int, total_steps: int, logical_days: int = 365) -> int:
    if total_steps <= 0:
        return 0
    return min(logical_days - 1, int(step * logical_days / total_steps))


def _symbol_for(day: int, index: int) -> str:
    return SYMBOLS[(day + index) % len(SYMBOLS)]


def _regime_for(day: int) -> str:
    if day > 0 and day % 90 == 0:
        return "CRISIS"
    block = (day // 30) % (len(VOL_REGIMES) - 1)
    return VOL_REGIMES[block]


def build_scale_candidates(
    count: int,
    *,
    seed: int,
    complete_quota: int,
    logical_days: int = 365,
) -> list[dict[str, Any]]:
    """Deterministic multi-symbol multi-regime closed-loop candidates."""
    out: list[dict[str, Any]] = []
    for i in range(count):
        day = _day_index(i, count, logical_days)
        symbol = _symbol_for(day, i)
        regime = _regime_for(day)
        pit = HISTORICAL_START + timedelta(hours=i)
        mode = "COMPLETE" if i < complete_quota else (
            "REJECT" if (i + seed) % 2 == 0 else "ADVISORY_REJECT"
        )
        # Periodic fault-tagged candidates (handled by campaign loop).
        # Moduli keep coverage dense enough for smoke (count>=48) and full scale.
        fault_tag = None
        if i > 0 and i % 37 == 0:
            fault_tag = "provider_outage"
        elif i > 0 and i % 41 == 0:
            fault_tag = "reflection_interrupt"
        elif i > 0 and i % 43 == 0:
            fault_tag = "lesson_interrupt"
        elif i > 0 and i % 47 == 0:
            fault_tag = "partial_fill"
        elif i > 0 and i % 53 == 0:
            fault_tag = "duplicate_observe"

        out.append(
            {
                "candidate_id": f"v13g_cand_{seed}_{i:05d}",
                "market_context_id": f"v13g_mctx_{seed}_{symbol}_{regime}",
                "point_in_time_timestamp": pit.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "symbol": symbol,
                "side": "BUY" if i % 2 == 0 else "SELL",
                "mark_price": Decimal("100") + Decimal((i * 7 + seed) % 97),
                "qty": Decimal(SYMBOL_QTY[symbol]),
                "mode": mode,
                "replay_index": i,
                "historical": True,
                "seed": seed,
                "logical_day": day,
                "vol_regime": regime,
                "spread_mult": REGIME_SPREAD_MULT[regime],
                "fault_tag": fault_tag,
                "system_correctness_only": True,
                "edge_claim": False,
                "profitability_measured": False,
            }
        )
    return out


def universe_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    symbols = sorted({str(c.get("symbol")) for c in candidates})
    regimes = sorted({str(c.get("vol_regime")) for c in candidates})
    fault_tags = sorted({str(c.get("fault_tag")) for c in candidates if c.get("fault_tag")})
    days = sorted({int(c.get("logical_day", 0)) for c in candidates})
    return {
        "symbol_count": len(symbols),
        "symbols": symbols,
        "vol_regimes": regimes,
        "vol_regime_count": len(regimes),
        "fault_tags": fault_tags,
        "logical_day_span": {
            "min": days[0] if days else 0,
            "max": days[-1] if days else 0,
            "distinct_days": len(days),
        },
    }


__all__ = [
    "HISTORICAL_START",
    "REGIME_SPREAD_MULT",
    "SYMBOLS",
    "SYMBOL_QTY",
    "VOL_REGIMES",
    "build_scale_candidates",
    "universe_summary",
]
