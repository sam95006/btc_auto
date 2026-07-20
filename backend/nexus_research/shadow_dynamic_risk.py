"""NEXUS Phase 6.5 Gate G — Dynamic leverage/margin SHADOW ONLY.

Never mutates production PAPER limits (3x / 20 USDT / 1 position).
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

PRODUCTION_LEVERAGE_CAP = 3
PRODUCTION_MARGIN_CAP_USD = 20.0
PRODUCTION_MAX_POSITIONS = 1

USER_REQUESTED_POLICY = "USER_REQUESTED_POLICY"
RISK_ADAPTIVE_POLICY = "RISK_ADAPTIVE_POLICY"


def _tier(symbol: str) -> str:
    sym = symbol.upper()
    if sym in ("BTCUSDT", "ETHUSDT"):
        return "LARGE_CAP"
    return "SMALL_CAP"


def propose_dynamic_risk(
    *,
    symbol: str,
    direction: str,
    confidence: float,
    volatility: float,
    atr_pct: float,
    spread_bps: float,
    depth_usd: float,
    funding_rate: Optional[float],
    oi_change_pct: Optional[float],
    account_equity: float = 10000.0,
    policy: str = RISK_ADAPTIVE_POLICY,
) -> dict[str, Any]:
    """Shadow-only DynamicRiskProposal — no orders, no production mutation."""
    tier = _tier(symbol)
    proposal_id = str(uuid.uuid4())

    if policy == USER_REQUESTED_POLICY:
        lev_min, lev_max = (20, 75) if tier == "LARGE_CAP" else (10, 45)
    else:
        lev_min, lev_max = (1, 75) if tier == "LARGE_CAP" else (1, 45)

    # Risk-adaptive scaling (shadow math only)
    vol_penalty = min(0.8, max(0.0, volatility * 2.0))
    spread_penalty = min(0.5, spread_bps / 200.0)
    depth_bonus = min(0.2, depth_usd / 500_000.0) if depth_usd > 0 else 0.0
    conf_boost = min(0.3, confidence / 100.0)

    raw_lev = lev_min + (lev_max - lev_min) * max(0.0, conf_boost + depth_bonus - vol_penalty - spread_penalty)
    proposed_leverage = max(lev_min, min(lev_max, round(raw_lev, 2)))

    # Margin from shadow policy — capped separately from production
    proposed_margin = min(account_equity * 0.02, 500.0) * (1.0 - vol_penalty)
    proposed_margin = max(5.0, round(proposed_margin, 2))
    proposed_notional = round(proposed_margin * proposed_leverage, 2)

    rejection = None
    if spread_bps > 50:
        rejection = "SPREAD_TOO_WIDE"
    elif depth_usd < 10_000:
        rejection = "DEPTH_TOO_LOW"
    elif confidence < 40:
        rejection = "CONFIDENCE_TOO_LOW"

    return {
        "proposalId": proposal_id,
        "researchOnly": True,
        "shadowOnly": True,
        "productionUnchanged": True,
        "policyVersion": "6.5.0",
        "policy": policy,
        "symbol": symbol.upper(),
        "liquidityTier": tier,
        "proposedDirection": direction.upper(),
        "proposedLeverage": proposed_leverage,
        "proposedMargin": proposed_margin,
        "proposedNotional": proposed_notional,
        "proposedStop": None,
        "proposedTargets": [],
        "maxLoss": round(proposed_margin * 0.5, 2),
        "liquidationDistanceEstimate": round(100.0 / max(proposed_leverage, 1), 2),
        "portfolioRiskContribution": round(proposed_notional / max(account_equity, 1), 4),
        "rejectionReason": rejection,
        "productionLimits": {
            "maxLeverage": PRODUCTION_LEVERAGE_CAP,
            "maxMarginUsd": PRODUCTION_MARGIN_CAP_USD,
            "maxOpenPositions": PRODUCTION_MAX_POSITIONS,
        },
        "orderCreated": False,
    }


def run_stress_comparison(proposal: dict[str, Any]) -> dict[str, Any]:
    """Compare USER_REQUESTED vs RISK_ADAPTIVE under adverse scenarios (shadow)."""
    sym = proposal.get("symbol") or "BTCUSDT"
    scenarios = [
        {"name": "adverse_1pct", "move_pct": -1.0},
        {"name": "adverse_2pct", "move_pct": -2.0},
        {"name": "adverse_5pct", "move_pct": -5.0},
        {"name": "spread_spike", "spread_bps": 80},
        {"name": "funding_spike", "funding_rate": 0.001},
    ]
    user_p = propose_dynamic_risk(
        symbol=sym, direction="LONG", confidence=70, volatility=0.02, atr_pct=1.5,
        spread_bps=5, depth_usd=200_000, funding_rate=0.0001, oi_change_pct=0.5,
        policy=USER_REQUESTED_POLICY,
    )
    risk_p = propose_dynamic_risk(
        symbol=sym, direction="LONG", confidence=70, volatility=0.02, atr_pct=1.5,
        spread_bps=5, depth_usd=200_000, funding_rate=0.0001, oi_change_pct=0.5,
        policy=RISK_ADAPTIVE_POLICY,
    )
    results = []
    for sc in scenarios:
        move = abs(sc.get("move_pct", 0))
        for label, p in [("USER_REQUESTED", user_p), ("RISK_ADAPTIVE", risk_p)]:
            notional = float(p.get("proposedNotional") or 0)
            loss = notional * (move / 100.0)
            results.append({
                "scenario": sc["name"],
                "policy": label,
                "estimatedLossUsd": round(loss, 2),
                "liquidationProximityPct": round(move / max(float(p.get("liquidationDistanceEstimate") or 1), 0.01), 2),
                "survivalRate": 1.0 if loss < float(p.get("proposedMargin") or 0) else 0.0,
            })
    return {
        "ok": True,
        "researchOnly": True,
        "shadowOnly": True,
        "scenarios": results,
        "userRequestedPolicy": user_p,
        "riskAdaptivePolicy": risk_p,
        "productionLeverageUnchanged": True,
        "orderCreated": False,
    }
