"""Map 0-100 confidence score -> margin & leverage tiers (demo: no >100% margin boost)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.governance.autonomy_bounds_guard import clamp_trade_proposal, validate_proposal_bounds
from config.confidence_matrix_config import (
    ABSOLUTE_MAX_LEVERAGE,
    ABSOLUTE_MAX_MARGIN_PCT,
    BASE_MARGIN_CORE,
    BASE_MARGIN_RADAR,
    SCORE_TIER_LOW_MAX,
    SCORE_TIER_MID_MAX,
    TIER_HIGH_LEVERAGE,
    TIER_HIGH_MARGIN_MULT,
    TIER_LOW_LEVERAGE,
    TIER_LOW_MARGIN_MULT,
    TIER_MID_LEVERAGE,
    TIER_MID_MARGIN_MULT,
)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


class DynamicAssetAllocator:
    def tier_for_score(self, score: float) -> str:
        score = _safe_float(score)
        if score <= SCORE_TIER_LOW_MAX:
            return "low"
        if score <= SCORE_TIER_MID_MAX:
            return "medium"
        return "high"

    def allocate(
        self,
        confidence_score: float,
        *,
        fleet: str = "RADAR",
        deployable_pool: float = 0.0,
        available_balance: float = 0.0,
    ) -> Dict[str, Any]:
        fleet = str(fleet or "RADAR").upper()
        tier = self.tier_for_score(confidence_score)
        if tier == "low":
            margin_mult = TIER_LOW_MARGIN_MULT
            leverage = TIER_LOW_LEVERAGE
        elif tier == "medium":
            margin_mult = TIER_MID_MARGIN_MULT
            leverage = TIER_MID_LEVERAGE
        else:
            margin_mult = TIER_HIGH_MARGIN_MULT
            leverage = TIER_HIGH_LEVERAGE

        base = BASE_MARGIN_RADAR if fleet == "RADAR" else BASE_MARGIN_CORE
        pool = max(0.0, _safe_float(deployable_pool))
        if pool > 0:
            base = max(base, pool * (0.04 if fleet == "RADAR" else 0.06))

        margin = base * margin_mult
        wallet_cap = max(0.0, _safe_float(available_balance)) * ABSOLUTE_MAX_MARGIN_PCT
        if wallet_cap > 0:
            margin = min(margin, wallet_cap)

        leverage = min(ABSOLUTE_MAX_LEVERAGE, leverage)
        return {
            "tier": tier,
            "confidence_score": round(confidence_score, 2),
            "margin_multiplier": round(margin_mult, 4),
            "margin": round(margin, 4),
            "leverage": round(leverage, 2),
            "wallet_cap": round(wallet_cap, 4) if wallet_cap else None,
        }

    def apply_to_proposal(
        self,
        proposal: Dict[str, Any],
        matrix_result: Dict[str, Any],
        *,
        deployable_pool: float = 0.0,
        available_balance: float = 0.0,
    ) -> Dict[str, Any]:
        proposal = dict(proposal or {})
        score = _safe_float(matrix_result.get("confidence_score"))
        fleet = str(proposal.get("fleet") or "RADAR").upper()
        alloc = self.allocate(
            score,
            fleet=fleet,
            deployable_pool=deployable_pool,
            available_balance=available_balance,
        )
        proposal["margin"] = alloc["margin"]
        proposal["leverage"] = alloc["leverage"]
        proposal["confidence_matrix"] = dict(matrix_result or {})
        proposal["dynamic_allocation"] = alloc
        proposal["adjusted_confidence"] = round(score / 100.0, 4)
        proposal["raw_confidence"] = proposal.get("raw_confidence", proposal["adjusted_confidence"])
        proposal, _ = clamp_trade_proposal(proposal)
        proposal, _ = validate_proposal_bounds(proposal, available_balance=available_balance)
        return proposal
