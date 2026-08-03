"""Research eligibility vs future Demo eligibility — one universe, no fleets."""
from __future__ import annotations

from typing import Any

from backend.nexus_dynamic_universe.symbol_profile import classify_meme


def research_vs_demo_gates() -> dict[str, Any]:
    return {
        "schema": "research_vs_demo_eligibility_v1",
        "fleet_architecture": False,
        "one_dynamic_universe": True,
        "historical_research_eligible_may_include_small_meme": True,
        "future_demo_execution_eligible_stricter": True,
        "demo_gates_not_weakened_for_research_count": True,
        "research_basis": [
            "listing_age",
            "candle_coverage",
            "volume",
            "turnover",
            "spread_history",
            "estimated_slippage",
            "instrument_validity",
            "chronology",
            "data_completeness",
            "capability_requirements",
        ],
        "demo_extra_basis": [
            "current_liquidity",
            "current_spread",
            "current_slippage",
            "current_open_interest",
            "current_instrument_status",
            "current_execution_quality_proof",
        ],
        "eligibility_not_based_on_backtest_results": True,
    }


def classify_coverage_counts(profiles: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"mainstream": 0, "mid_size": 0, "small": 0, "meme": 0, "total": 0}
    for p in profiles:
        counts["total"] += 1
        size = str(p.get("market_size_class") or p.get("size_class") or "UNKNOWN").upper()
        base = str(p.get("base_coin") or p.get("symbol", "")).replace("USDT", "")
        is_meme = bool(p.get("is_meme")) or classify_meme(base)
        if is_meme or size == "MEME":
            counts["meme"] += 1
        elif size in {"MAINSTREAM", "LARGE"}:
            counts["mainstream"] += 1
        elif size in {"MID_SIZE", "MID"}:
            counts["mid_size"] += 1
        elif size in {"SMALL"}:
            counts["small"] += 1
        else:
            # unknown size → count via turnover heuristic already in profile if present
            if float(p.get("turnover24h") or 0) >= 50_000_000:
                counts["mainstream"] += 1
            elif float(p.get("turnover24h") or 0) >= 5_000_000:
                counts["mid_size"] += 1
            else:
                counts["small"] += 1
    return counts


def enrichment_targets() -> dict[str, int]:
    return {
        "historical_research_eligible_count": 150,
        "mid_size_research_eligible_count": 25,
        "small_research_eligible_count": 15,
        "meme_research_eligible_count": 8,
    }
