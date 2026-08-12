"""Signal Quality V1 — deterministic scoring, no ML, no fabricated data."""
from __future__ import annotations

import math
from typing import Any

from backend.nexus_research_ai_autonomy.market_state import MarketStateEngine


STRUCTURE_TYPES = (
    "TREND_UP",
    "TREND_DOWN",
    "RANGE",
    "BREAKOUT_UP",
    "BREAKOUT_DOWN",
    "COMPRESSION",
    "UNDETERMINED",
)


def classify_market_structure(enrichment: dict[str, Any]) -> str:
    m5 = enrichment.get("momentum_5m") or {}
    m15 = enrichment.get("momentum_15m") or {}
    vol = enrichment.get("volatility")
    ret5 = m5.get("return")
    ret15 = m15.get("return")
    if ret5 is None and ret15 is None:
        return "UNDETERMINED"
    r5 = float(ret5 or 0)
    r15 = float(ret15 or 0)
    v = float(vol or 0.35)
    if v < 0.15 and abs(r5) < 0.05 and abs(r15) < 0.1:
        return "COMPRESSION"
    if r5 > 0.15 and r15 > 0.1:
        return "BREAKOUT_UP" if abs(r5) > abs(r15) * 1.5 else "TREND_UP"
    if r5 < -0.15 and r15 < -0.1:
        return "BREAKOUT_DOWN" if abs(r5) > abs(r15) * 1.5 else "TREND_DOWN"
    if abs(r5) < 0.08 and abs(r15) < 0.15:
        return "RANGE"
    if r5 > 0:
        return "TREND_UP"
    if r5 < 0:
        return "TREND_DOWN"
    return "UNDETERMINED"


def classify_oi_relationship(enrichment: dict[str, Any], side: str) -> str | None:
    m5 = (enrichment.get("momentum_5m") or {}).get("return")
    oi_d = enrichment.get("oi_delta_short")
    if m5 is None or oi_d is None:
        return None
    price_up = float(m5) > 0
    oi_up = float(oi_d) > 0
    if price_up and oi_up:
        return "price_up_oi_up"
    if price_up and not oi_up:
        return "price_up_oi_down"
    if not price_up and oi_up:
        return "price_down_oi_up"
    return "price_down_oi_down"


def compute_direction_scores(enrichment: dict[str, Any], *, structure: str, regime: str) -> dict[str, float]:
    m1 = (enrichment.get("momentum_1m") or {}).get("return") or 0.0
    m5 = (enrichment.get("momentum_5m") or {}).get("return") or 0.0
    m15 = (enrichment.get("momentum_15m") or {}).get("return") or 0.0
    # Multi-TF momentum — do not let 24h dominate
    long_raw = m1 * 0.2 + m5 * 0.45 + m15 * 0.35
    short_raw = -long_raw
    struct_bias = 0.0
    if structure in {"TREND_UP", "BREAKOUT_UP"}:
        struct_bias = 0.08
    elif structure in {"TREND_DOWN", "BREAKOUT_DOWN"}:
        struct_bias = -0.08
    act = float(enrichment.get("activity_score") or 0.5)
    act_pen = 0.85 if enrichment.get("activity_fallback") else 1.0
    long_score = max(0.0, min(1.0, (0.5 + long_raw * 0.08 + struct_bias) * act_pen * (0.5 + act * 0.5)))
    short_score = max(0.0, min(1.0, (0.5 + short_raw * 0.08 - struct_bias) * act_pen * (0.5 + act * 0.5)))
    return {
        "LONG": round(long_score, 4),
        "SHORT": round(short_score, 4),
        "direction_score_delta": round(long_score - short_score, 4),
    }


def compute_liquidity_quality(enrichment: dict[str, Any]) -> float:
    spread = enrichment.get("spread_bps")
    turnover = float(enrichment.get("turnover") or 0)
    liq = min(1.0, turnover / 50_000_000.0) if turnover > 0 else 0.2
    if spread is not None and spread > 0:
        liq *= max(0.1, 1.0 - min(0.9, float(spread) / 50.0))
    return round(max(0.05, min(1.0, liq)), 4)


def estimate_round_trip_fee(notional: float, *, fee_rate: float = 0.0011) -> float:
    return round(notional * fee_rate, 6)


def compute_expected_net_edge(
    *,
    enrichment: dict[str, Any],
    side: str,
    notional: float = 350.0,
    target_pct: float = 0.55,
    stop_pct: float = 0.40,
) -> dict[str, Any]:
    direction_scores = compute_direction_scores(
        enrichment,
        structure=classify_market_structure(enrichment),
        regime="",
    )
    conf = direction_scores["LONG"] if side.upper() == "LONG" else direction_scores["SHORT"]
    expected_gross = notional * (target_pct / 100.0) * conf
    spread_cost = notional * (float(enrichment.get("spread_bps") or 0) / 10_000.0)
    slip = float(enrichment.get("estimated_slippage") or 0) * 2
    rt_fee = estimate_round_trip_fee(notional)
    fund = abs(float(enrichment.get("funding_rate") or 0)) * notional
    total_cost = rt_fee + spread_cost + slip + fund
    net = expected_gross - total_cost
    ratio = (expected_gross / total_cost) if total_cost > 0 else None
    return {
        "expected_gross_edge": round(expected_gross, 6),
        "estimated_round_trip_fee": rt_fee,
        "estimated_spread_cost": round(spread_cost, 6),
        "estimated_slippage_cost": round(slip, 6),
        "estimated_funding_cost": round(fund, 6),
        "expected_net_edge": round(net, 6),
        "edge_to_cost_ratio": round(ratio, 4) if ratio is not None else None,
    }


def compute_entry_quality(
    enrichment: dict[str, Any],
    *,
    side: str,
    structure: str,
    regime: str,
    edge: dict[str, Any],
) -> dict[str, Any]:
    liq_q = compute_liquidity_quality(enrichment)
    act = float(enrichment.get("activity_score") or 0.5)
    act_q = act * (0.7 if enrichment.get("activity_fallback") else 1.0)
    dirs = compute_direction_scores(enrichment, structure=structure, regime=regime)
    mom_align = dirs["LONG"] if side.upper() == "LONG" else dirs["SHORT"]
    struct_align = 0.8 if (
        (side.upper() == "LONG" and structure in {"TREND_UP", "BREAKOUT_UP"})
        or (side.upper() == "SHORT" and structure in {"TREND_DOWN", "BREAKOUT_DOWN"})
    ) else 0.4 if structure == "RANGE" else 0.5
    regime_align = 0.7 if regime not in {"UNCERTAIN", "UNDETERMINED"} else 0.4
    deriv_q = 0.6
    oi_rel = classify_oi_relationship(enrichment, side)
    if oi_rel in {"price_up_oi_up", "price_down_oi_down"} and side.upper() == "LONG":
        deriv_q = 0.75
    elif oi_rel in {"price_up_oi_down", "price_down_oi_up"}:
        deriv_q = 0.55
    cost_q = 0.8 if (edge.get("edge_to_cost_ratio") or 0) >= 1.2 else 0.4 if (edge.get("expected_net_edge") or 0) > 0 else 0.2
    timing_q = 0.7 if abs(float((enrichment.get("momentum_1m") or {}).get("return") or 0)) < 0.3 else 0.5
    components = {
        "structure_alignment": round(struct_align, 4),
        "momentum_alignment": round(mom_align, 4),
        "activity_quality": round(act_q, 4),
        "liquidity_quality": round(liq_q, 4),
        "regime_alignment": round(regime_align, 4),
        "derivatives_quality": round(deriv_q, 4),
        "cost_quality": round(cost_q, 4),
        "timing_quality": round(timing_q, 4),
    }
    score = sum(components.values()) / len(components)
    return {"entry_quality_score": round(score, 4), "components": components}


def build_evidence_lists(
    enrichment: dict[str, Any],
    *,
    side: str,
    structure: str,
    regime: str,
    edge: dict[str, Any],
) -> tuple[list[str], list[str]]:
    support: list[str] = []
    contradict: list[str] = []
    m5 = (enrichment.get("momentum_5m") or {}).get("return")
    if m5 is not None:
        if side.upper() == "LONG" and float(m5) > 0:
            support.append("MOMENTUM_5M_POSITIVE")
        elif side.upper() == "SHORT" and float(m5) < 0:
            support.append("MOMENTUM_5M_POSITIVE")
        else:
            contradict.append("MOMENTUM_5M_AGAINST")
    if structure in {"BREAKOUT_UP", "BREAKOUT_DOWN"}:
        support.append(f"STRUCTURE_{structure}")
    oi_rel = classify_oi_relationship(enrichment, side)
    if oi_rel == "price_up_oi_up" and side.upper() == "LONG":
        support.append("OI_EXPANDING")
    elif oi_rel == "price_up_oi_down":
        contradict.append("OI_DIVERGENCE")
    fr = enrichment.get("funding_rate")
    if fr is not None and abs(float(fr)) > 0.0003:
        if float(fr) > 0 and side.upper() == "LONG":
            contradict.append("FUNDING_CROWDED")
        elif float(fr) < 0 and side.upper() == "SHORT":
            contradict.append("FUNDING_CROWDED")
    spread = enrichment.get("spread_bps")
    if spread is not None and float(spread) > 8:
        contradict.append("SPREAD_WIDE")
    if enrichment.get("activity_fallback"):
        contradict.append("ACTIVITY_FALLBACK")
    if (edge.get("expected_net_edge") or 0) <= 0:
        contradict.append("POST_COST_EDGE_NEGATIVE")
    if (edge.get("edge_to_cost_ratio") or 0) >= 1.5:
        support.append("EDGE_COVERS_COSTS")
    if regime in {"UNCERTAIN", "UNDETERMINED"}:
        contradict.append("REGIME_UNCERTAIN")
    return support, contradict


def evaluate_regime(enrichment: dict[str, Any]) -> dict[str, Any]:
    engine = MarketStateEngine()
    m5 = enrichment.get("momentum_5m") or {}
    inputs = {
        "trend": (m5.get("return") or 0) / 100.0 if m5.get("return") is not None else None,
        "momentum": (m5.get("velocity") or 0) / 100.0 if m5.get("velocity") is not None else None,
        "volatility": (enrichment.get("volatility") or 0) / 100.0 if enrichment.get("volatility") else None,
        "activity": enrichment.get("activity_score"),
        "volume": math.log10(max(1.0, float(enrichment.get("turnover") or 1))),
        "oi": enrichment.get("open_interest"),
        "funding": enrichment.get("funding_rate"),
        "spread": (enrichment.get("spread_bps") or 0) / 10_000.0,
        "liquidity": compute_liquidity_quality(enrichment),
        "freshness_sec": (enrichment.get("data_freshness_ms") or 0) / 1000.0,
        "data_trust": 0.5 if enrichment.get("activity_fallback") else 0.85,
    }
    result = engine.evaluate(inputs)
    structure = classify_market_structure(enrichment)
    return {
        "market_structure": structure,
        "regime": result.regime_primary,
        "regime_confidence": result.regime_confidence,
        "regime_evidence": list(result.regime_evidence),
        "regime_invalidators": list(result.regime_invalidators),
    }
