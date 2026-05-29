"""Scale margin & leverage from AI / rule proposal confidence."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.governance.autonomy_bounds_guard import clamp_trade_proposal
from config.ai_confidence_sizing_config import (
    AI_CONFIDENCE_BASE_MARGIN_CORE,
    AI_CONFIDENCE_BASE_MARGIN_RADAR,
    AI_CONFIDENCE_DEPLOYABLE_CAP_CORE,
    AI_CONFIDENCE_DEPLOYABLE_CAP_RADAR,
    AI_CONFIDENCE_DEPLOYABLE_PCT_CORE,
    AI_CONFIDENCE_DEPLOYABLE_PCT_RADAR,
    AI_CONFIDENCE_LEVERAGE_MAX,
    AI_CONFIDENCE_LEVERAGE_MIN,
    AI_CONFIDENCE_MARGIN_CEILING,
    AI_CONFIDENCE_MARGIN_FLOOR,
    AI_CONFIDENCE_MARGIN_MULT_MAX,
    AI_CONFIDENCE_MARGIN_MULT_MIN,
    AI_CONFIDENCE_MIN,
    AI_CONFIDENCE_SIZING_ENABLED,
)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


def _normalize_confidence(confidence: float, min_conf: float = AI_CONFIDENCE_MIN) -> float:
    """Map [min_conf, 1.0] -> [0.0, 1.0]."""
    confidence = max(0.0, min(1.0, confidence))
    floor = max(0.0, min(0.99, float(min_conf)))
    if confidence <= floor:
        return 0.0
    return min(1.0, (confidence - floor) / max(0.01, 1.0 - floor))


def _tier(norm: float) -> str:
    if norm >= 0.85:
        return "very_high"
    if norm >= 0.6:
        return "high"
    if norm >= 0.35:
        return "medium"
    return "low"


class ConfidencePositionSizer:
    """
    Higher confidence -> larger margin & higher leverage (within hard bounds).
    Lower confidence -> smaller exposure; still tradable if above min_confidence gate.
    """

    def __init__(self, *, enabled: bool = None, min_confidence: float = None):
        self.enabled = AI_CONFIDENCE_SIZING_ENABLED if enabled is None else bool(enabled)
        self.min_confidence = float(min_confidence if min_confidence is not None else AI_CONFIDENCE_MIN)

    def extract_confidence(self, proposal: Dict[str, Any]) -> Optional[float]:
        proposal = dict(proposal or {})
        for key in ("adjusted_confidence", "raw_confidence", "confidence", "llm_confidence"):
            val = proposal.get(key)
            if val is not None:
                return _safe_float(val, -1.0)
        return None

    def should_apply(self, proposal: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        if proposal.get("confidence_sizing_applied"):
            return False
        confidence = self.extract_confidence(proposal)
        if confidence is None or confidence < 0:
            return False
        source = str(proposal.get("decision_source") or proposal.get("proposer") or proposal.get("strategy_key") or "")
        ai_markers = ("ai_led", "llm", "rule_signal", "rule_brain", "grid_", "funding_", "dca_")
        if any(marker in source.lower() for marker in ai_markers):
            return True
        if proposal.get("strategy_key") in {
            "ai_led_trade_proposer",
            "rule_signal_bridge",
            "radar_market_scan_strategy",
        }:
            return True
        return confidence >= self.min_confidence

    def compute(
        self,
        confidence: float,
        *,
        fleet: str = "RADAR",
        deployable_pool: float = 0.0,
    ) -> Dict[str, Any]:
        norm = _normalize_confidence(confidence, self.min_confidence)
        margin_mult = AI_CONFIDENCE_MARGIN_MULT_MIN + norm * (
            AI_CONFIDENCE_MARGIN_MULT_MAX - AI_CONFIDENCE_MARGIN_MULT_MIN
        )
        leverage = AI_CONFIDENCE_LEVERAGE_MIN + norm * (
            AI_CONFIDENCE_LEVERAGE_MAX - AI_CONFIDENCE_LEVERAGE_MIN
        )

        fleet = str(fleet or "RADAR").upper()
        is_radar = fleet == "RADAR"
        base = AI_CONFIDENCE_BASE_MARGIN_RADAR if is_radar else AI_CONFIDENCE_BASE_MARGIN_CORE
        pool = max(0.0, float(deployable_pool or 0.0))
        if pool > 0:
            pct = AI_CONFIDENCE_DEPLOYABLE_PCT_RADAR if is_radar else AI_CONFIDENCE_DEPLOYABLE_PCT_CORE
            cap = AI_CONFIDENCE_DEPLOYABLE_CAP_RADAR if is_radar else AI_CONFIDENCE_DEPLOYABLE_CAP_CORE
            base = max(base, min(pool * pct, cap))

        raw_margin = base * margin_mult
        dynamic_floor = AI_CONFIDENCE_MARGIN_FLOOR * margin_mult
        margin = max(dynamic_floor, min(AI_CONFIDENCE_MARGIN_CEILING, raw_margin))
        return {
            "confidence": round(confidence, 4),
            "confidence_norm": round(norm, 4),
            "confidence_tier": _tier(norm),
            "margin_multiplier": round(margin_mult, 4),
            "leverage": round(leverage, 2),
            "margin": round(margin, 4),
        }

    def apply(
        self,
        proposal: Dict[str, Any],
        *,
        deployable_pool: float = 0.0,
        market_contexts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        proposal = dict(proposal or {})
        if not self.should_apply(proposal):
            return proposal

        confidence = self.extract_confidence(proposal)
        if confidence is None:
            return proposal

        fleet = str(proposal.get("fleet") or "RADAR").upper()
        sized = self.compute(confidence, fleet=fleet, deployable_pool=deployable_pool)

        proposal["margin"] = sized["margin"]
        proposal["leverage"] = sized["leverage"]
        proposal["confidence_sizing"] = sized
        proposal["confidence_sizing_applied"] = True
        proposal["adjusted_confidence"] = sized["confidence"]

        proposal, _warnings = clamp_trade_proposal(proposal)
        return proposal
