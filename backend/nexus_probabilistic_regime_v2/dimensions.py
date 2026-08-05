"""Per-dimension probabilistic scorers (descriptive, non-predictive)."""
from __future__ import annotations

import math
from typing import Any

from backend.nexus_probabilistic_regime_v2.fixtures import log_returns


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def score_dimensions(bars: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Score all ten regime dimensions from PIT-eligible bars."""
    if len(bars) < 4:
        return _unknown_all("insufficient_bars")

    closes = [float(b["close"]) for b in bars]
    rets = log_returns(closes)
    if len(rets) < 3:
        return _unknown_all("insufficient_returns")

    mu = _mean(rets)
    sigma = _std(rets)
    spreads = [float(b.get("spread_bps") or 0.0) for b in bars]
    depths = [float(b.get("book_depth_score") or 0.0) for b in bars]
    oi = [float(b.get("open_interest_z") or 0.0) for b in bars]
    funding = [float(b.get("funding_rate") or 0.0) for b in bars]
    peer = [float(b.get("peer_return") or 0.0) for b in bars]
    own = [float(b.get("own_return") or 0.0) for b in bars]
    liq = [float(b.get("liquidation_intensity") or 0.0) for b in bars]
    flow = [float(b.get("net_capital_flow") or 0.0) for b in bars]
    micro = [float(b.get("microstructure_imbalance") or 0.5) for b in bars]
    events = [float(b.get("event_flag") or 0.0) for b in bars]
    hours = [int(b.get("session_hour_utc") or 0) for b in bars]

    # Direction
    dir_score = _clamp01(abs(mu) / 0.003)
    if mu > 0.0008:
        dir_label, bull, bear = "BULL", _clamp01(0.55 + dir_score * 0.45), _clamp01(0.2 * (1 - dir_score))
    elif mu < -0.0008:
        dir_label, bull, bear = "BEAR", _clamp01(0.2 * (1 - dir_score)), _clamp01(0.55 + dir_score * 0.45)
    else:
        dir_label, bull, bear = "NEUTRAL", 0.35, 0.35
    # Conflicting consecutive signs → MIXED
    sign_flips = sum(1 for i in range(1, len(rets)) if rets[i] * rets[i - 1] < 0)
    if sign_flips >= max(3, len(rets) // 2) and abs(mu) < 0.0015:
        dir_label, bull, bear = "MIXED", 0.45, 0.45

    # Volatility
    vol_exp = _clamp01((sigma - 0.004) / 0.02)
    vol_label = "EXPANSION" if vol_exp >= 0.55 else ("COMPRESSION" if vol_exp <= 0.2 else "NORMAL")

    # Liquidity
    avg_spread = _mean(spreads)
    avg_depth = _mean(depths)
    liq_stress = _clamp01((avg_spread / 30.0) * 0.6 + (1.0 - avg_depth) * 0.4)
    liq_label = "STRESS" if liq_stress >= 0.55 else ("AMPLE" if liq_stress <= 0.25 else "NORMAL")

    # Leverage / Crowding
    avg_oi = _mean(oi)
    avg_fund = _mean(funding)
    crowding = _clamp01(avg_oi * 0.65 + _clamp01(avg_fund / 0.0015) * 0.35)
    crowd_label = "LONG_CROWDED" if crowding >= 0.65 and avg_fund >= 0 else (
        "SHORT_CROWDED" if crowding >= 0.65 else "BALANCED"
    )

    # Trend quality
    path = sum(abs(r) for r in rets) or 1e-12
    efficiency = _clamp01(abs(sum(rets)) / path)
    tq_label = "HIGH" if efficiency >= 0.55 else ("LOW" if efficiency <= 0.25 else "MEDIUM")

    # Cross-asset correlation
    corr = _pearson(own[-min(20, len(own)) :], peer[-min(20, len(peer)) :])
    if corr is None:
        corr_label, corr_break = "UNKNOWN", 0.5
    else:
        corr_break = _clamp01((0.7 - corr) / 1.4)
        corr_label = "BREAKDOWN" if corr < 0.25 else ("TIGHT" if corr > 0.75 else "NORMAL")

    # Event risk
    event_p = _clamp01(_mean(events) * 0.7 + _mean(liq) * 0.3 + vol_exp * 0.2)
    event_label = "ELEVATED" if event_p >= 0.45 else "QUIET"

    # Session (UTC hour concentration)
    if hours:
        modal = max(set(hours), key=hours.count)
        session_label = f"UTC_{modal:02d}"
        session_score = _clamp01(hours.count(modal) / len(hours))
    else:
        session_label, session_score = "UNKNOWN", 0.0

    # Capital flow
    flow_m = _mean(flow)
    flow_score = _clamp01(abs(flow_m) / 3.0)
    flow_label = "INFLOW" if flow_m > 0.4 else ("OUTFLOW" if flow_m < -0.4 else "NEUTRAL")

    # Microstructure
    micro_m = _mean(micro)
    micro_score = _clamp01(abs(micro_m - 0.5) * 2)
    micro_label = "BID_HEAVY" if micro_m >= 0.6 else ("ASK_HEAVY" if micro_m <= 0.4 else "BALANCED")

    return {
        "Direction": {
            "label": dir_label,
            "score": dir_score,
            "strong_bull_probability": round(bull, 6),
            "strong_bear_probability": round(bear, 6),
            "metrics": {"mean_log_return": mu, "sign_flips": sign_flips},
        },
        "Volatility": {
            "label": vol_label,
            "score": vol_exp,
            "volatility_expansion_probability": round(vol_exp, 6),
            "metrics": {"return_std": sigma},
        },
        "Liquidity": {
            "label": liq_label,
            "score": liq_stress,
            "liquidity_stress_probability": round(liq_stress, 6),
            "metrics": {"avg_spread_bps": avg_spread, "avg_depth": avg_depth},
        },
        "LeverageCrowding": {
            "label": crowd_label,
            "score": crowding,
            "long_crowding_probability": round(crowding if avg_fund >= 0 else crowding * 0.3, 6),
            "metrics": {"avg_oi_z": avg_oi, "avg_funding": avg_fund},
        },
        "TrendQuality": {
            "label": tq_label,
            "score": efficiency,
            "metrics": {"efficiency_ratio": efficiency},
        },
        "CrossAssetCorrelation": {
            "label": corr_label,
            "score": 1.0 - corr_break if corr is not None else 0.0,
            "correlation_breakdown_probability": round(corr_break, 6),
            "metrics": {"pearson": corr},
        },
        "EventRisk": {
            "label": event_label,
            "score": event_p,
            "event_risk_probability": round(event_p, 6),
            "metrics": {"event_mean": _mean(events), "liq_mean": _mean(liq)},
        },
        "Session": {
            "label": session_label,
            "score": session_score,
            "metrics": {"modal_hour_utc": hours and max(set(hours), key=hours.count)},
        },
        "CapitalFlow": {
            "label": flow_label,
            "score": flow_score,
            "metrics": {"mean_net_capital_flow": flow_m},
        },
        "Microstructure": {
            "label": micro_label,
            "score": micro_score,
            "metrics": {"mean_imbalance": micro_m},
        },
    }


def _unknown_all(reason: str) -> dict[str, dict[str, Any]]:
    dims = (
        "Direction",
        "Volatility",
        "Liquidity",
        "LeverageCrowding",
        "TrendQuality",
        "CrossAssetCorrelation",
        "EventRisk",
        "Session",
        "CapitalFlow",
        "Microstructure",
    )
    out: dict[str, dict[str, Any]] = {}
    for d in dims:
        out[d] = {
            "label": "UNKNOWN",
            "score": 0.0,
            "metrics": {"reason": reason},
        }
    out["Direction"]["strong_bull_probability"] = 0.0
    out["Direction"]["strong_bear_probability"] = 0.0
    out["Volatility"]["volatility_expansion_probability"] = 0.0
    out["Liquidity"]["liquidity_stress_probability"] = 0.0
    out["LeverageCrowding"]["long_crowding_probability"] = 0.0
    out["CrossAssetCorrelation"]["correlation_breakdown_probability"] = 0.0
    out["EventRisk"]["event_risk_probability"] = 0.0
    return out
