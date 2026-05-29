"""Matrix score -> dynamic allocation -> volatility tuning -> hard bounds."""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.risk.confidence_matrix_engine import ConfidenceMatrixEngine
from backend.risk.dynamic_asset_allocator import DynamicAssetAllocator
from backend.risk.volatility_position_sizer import VolatilityPositionSizer


class ConfidenceSizingPipeline:
    def __init__(
        self,
        matrix_engine=None,
        allocator=None,
        volatility_sizer=None,
        blocklist=None,
    ):
        self.matrix_engine = matrix_engine or ConfidenceMatrixEngine()
        self.allocator = allocator or DynamicAssetAllocator()
        self.volatility_sizer = volatility_sizer or VolatilityPositionSizer()
        self.blocklist = blocklist

    def should_apply(self, proposal: Dict[str, Any]) -> bool:
        if not self.matrix_engine.enabled:
            return False
        if proposal.get("strategy_key") == "market_neutral_funding":
            return False
        if proposal.get("confidence_matrix_applied"):
            return False
        source = str(proposal.get("decision_source") or proposal.get("proposer") or "")
        markers = ("ai_led", "llm", "rule_signal", "rule_brain", "grid_", "funding_", "dca_", "radar")
        if any(m in source.lower() for m in markers):
            return True
        return proposal.get("strategy_key") in {
            "ai_led_trade_proposer",
            "rule_signal_bridge",
            "radar_market_scan_strategy",
        }

    def apply(
        self,
        proposal: Dict[str, Any],
        *,
        market_context: Optional[Dict[str, Any]] = None,
        market_contexts: Optional[Dict[str, Any]] = None,
        regime_state: Optional[Dict[str, Any]] = None,
        deployable_pool: float = 0.0,
        available_balance: float = 0.0,
    ) -> Dict[str, Any]:
        proposal = dict(proposal or {})
        if not self.should_apply(proposal):
            return proposal

        symbol = str(proposal.get("symbol") or proposal.get("fleet") or "").upper()
        fleet = str(proposal.get("fleet") or "RADAR").upper()
        contexts = dict(market_contexts or {})
        ctx = dict(market_context or contexts.get(fleet) or contexts.get(symbol) or {})

        macro_penalty = 0.0
        if self.blocklist is not None:
            macro_penalty = self.blocklist.matching_toxic_penalty(ctx)

        matrix = self.matrix_engine.score(
            proposal,
            market_context=ctx,
            regime_state=regime_state,
            macro_penalty=macro_penalty,
        )
        proposal = self.allocator.apply_to_proposal(
            proposal,
            matrix,
            deployable_pool=deployable_pool,
            available_balance=available_balance,
        )
        proposal = self.volatility_sizer.apply_to_request(proposal, ctx, contexts)
        proposal["confidence_matrix_applied"] = True
        return proposal
