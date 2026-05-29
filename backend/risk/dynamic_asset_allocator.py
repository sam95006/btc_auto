"""Map 0-100 confidence score -> margin & leverage (data-driven bands up to 100x)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.governance.autonomy_bounds_guard import clamp_trade_proposal, validate_proposal_bounds
from backend.risk.dynamic_leverage_engine import DynamicLeverageEngine
from backend.risk.dynamic_margin_engine import DynamicMarginEngine
from config.autonomy_bounds_config import HARD_MAX_LEVERAGE, HARD_MAX_MARGIN_USD, HARD_MIN_MARGIN_USD
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
    USE_CONFIDENCE_LEVERAGE_TABLE,
    USE_CONFIDENCE_MARGIN_TABLE,
)
from config.fee_churn_config import MIN_MARGIN_USD
from config.leverage_config import FLEET_LEVERAGE_CAPS, FLEET_MARGIN_CAPS, MAX_SYSTEM_LEVERAGE, MAX_SYSTEM_MARGIN_USD


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


class DynamicAssetAllocator:
    def __init__(self, leverage_engine=None, margin_engine=None):
        self.leverage_engine = leverage_engine or DynamicLeverageEngine()
        self.margin_engine = margin_engine or DynamicMarginEngine()

    def tier_for_score(self, score: float) -> str:
        score = _safe_float(score)
        if score <= SCORE_TIER_LOW_MAX:
            return "low"
        if score <= SCORE_TIER_MID_MAX:
            return "medium"
        return "high"

    def _confidence_0_1(self, score: float) -> float:
        return max(0.0, min(1.0, _safe_float(score) / 100.0))

    def _leverage_from_score(self, score: float, fleet: str) -> float:
        fleet = str(fleet or "RADAR").upper()
        fleet_cap = float(FLEET_LEVERAGE_CAPS.get(fleet, MAX_SYSTEM_LEVERAGE))
        system_cap = min(float(MAX_SYSTEM_LEVERAGE), float(HARD_MAX_LEVERAGE), float(ABSOLUTE_MAX_LEVERAGE))

        if USE_CONFIDENCE_LEVERAGE_TABLE:
            confidence_0_1 = self._confidence_0_1(score)
            proposal = self.leverage_engine.calculate_proposed_leverage(confidence_0_1)
            if not proposal.get("allowed"):
                return 0.0
            leverage = float(proposal.get("proposed_leverage") or 0.0)
            return min(leverage, fleet_cap, system_cap)

        tier = self.tier_for_score(score)
        if tier == "low":
            leverage = TIER_LOW_LEVERAGE
        elif tier == "medium":
            leverage = TIER_MID_LEVERAGE
        else:
            leverage = TIER_HIGH_LEVERAGE
        return min(leverage, fleet_cap, system_cap)

    def _margin_from_score(
        self,
        score: float,
        *,
        fleet: str,
        deployable_pool: float = 0.0,
        available_balance: float = 0.0,
    ) -> Dict[str, Any]:
        fleet = str(fleet or "RADAR").upper()
        pool = max(0.0, _safe_float(deployable_pool))
        base = BASE_MARGIN_RADAR if fleet == "RADAR" else BASE_MARGIN_CORE
        margin_mult = 1.0
        deployable_pct = 0.04 if fleet == "RADAR" else 0.06
        margin_mode = "fixed_tiers"

        if USE_CONFIDENCE_MARGIN_TABLE:
            confidence_0_1 = self._confidence_0_1(score)
            proposal = self.margin_engine.calculate_proposed_margin(confidence_0_1)
            if not proposal.get("allowed"):
                return {
                    "margin": 0.0,
                    "margin_multiplier": 0.0,
                    "margin_mode": "confidence_table",
                    "deployable_pct": 0.0,
                }
            margin_mult = float(proposal.get("margin_mult") or 1.0)
            deployable_pct = float(proposal.get("deployable_pct") or deployable_pct)
            margin_mode = "confidence_table"
        else:
            tier = self.tier_for_score(score)
            if tier == "low":
                margin_mult = TIER_LOW_MARGIN_MULT
            elif tier == "medium":
                margin_mult = TIER_MID_MARGIN_MULT
            else:
                margin_mult = TIER_HIGH_MARGIN_MULT

        if pool > 0:
            fleet_deploy_cap = float(FLEET_MARGIN_CAPS.get(fleet, MAX_SYSTEM_MARGIN_USD))
            pool_base = min(pool * deployable_pct, fleet_deploy_cap)
            base = max(base, pool_base)

        margin = base * margin_mult
        fleet_cap = float(FLEET_MARGIN_CAPS.get(fleet, MAX_SYSTEM_MARGIN_USD))
        system_cap = min(float(HARD_MAX_MARGIN_USD), float(MAX_SYSTEM_MARGIN_USD), fleet_cap)
        margin = min(margin, system_cap)

        wallet_cap = max(0.0, _safe_float(available_balance)) * ABSOLUTE_MAX_MARGIN_PCT
        if wallet_cap > 0:
            margin = min(margin, wallet_cap)

        floor = max(HARD_MIN_MARGIN_USD, MIN_MARGIN_USD)
        margin = max(floor, margin)

        return {
            "margin": round(margin, 4),
            "margin_multiplier": round(margin_mult, 4),
            "margin_mode": margin_mode,
            "deployable_pct": round(deployable_pct, 4),
            "wallet_cap": round(wallet_cap, 4) if wallet_cap else None,
            "fleet_margin_cap": round(fleet_cap, 4),
        }

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
        margin_info = self._margin_from_score(
            confidence_score,
            fleet=fleet,
            deployable_pool=deployable_pool,
            available_balance=available_balance,
        )
        leverage = self._leverage_from_score(confidence_score, fleet)
        margin = float(margin_info.get("margin") or 0.0)
        notional = round(margin * leverage, 4) if margin > 0 and leverage > 0 else 0.0

        return {
            "tier": tier,
            "confidence_score": round(confidence_score, 2),
            "margin_multiplier": margin_info.get("margin_multiplier"),
            "margin": margin,
            "leverage": round(leverage, 2),
            "notional_usd": notional,
            "wallet_cap": margin_info.get("wallet_cap"),
            "fleet_margin_cap": margin_info.get("fleet_margin_cap"),
            "margin_mode": margin_info.get("margin_mode"),
            "leverage_mode": "confidence_table" if USE_CONFIDENCE_LEVERAGE_TABLE else "fixed_tiers",
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
