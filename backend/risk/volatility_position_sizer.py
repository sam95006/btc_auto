from __future__ import annotations

from config.risk_budget_config import (
    VOLATILITY_SIZING_ENABLED,
    VOLATILITY_SIZE_CAP,
    VOLATILITY_SIZE_FLOOR,
    VOLATILITY_TARGET_PERCENTILE,
)


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class VolatilityPositionSizer:
    """Scale margin/leverage down in extreme volatility, slight boost in normal band."""

    def multiplier_for_context(self, market_context=None):
        if not VOLATILITY_SIZING_ENABLED:
            return 1.0
        ctx = dict(market_context or {})
        vol = _safe_float(ctx.get("volatility_percentile"), VOLATILITY_TARGET_PERCENTILE)
        target = float(VOLATILITY_TARGET_PERCENTILE or 0.45)
        distance = abs(vol - target)
        mult = 1.0 - distance * 0.55
        return max(float(VOLATILITY_SIZE_FLOOR), min(float(VOLATILITY_SIZE_CAP), mult))

    def scale_proposal(self, proposal, market_context=None):
        proposal = dict(proposal or {})
        mult = self.multiplier_for_context(market_context)
        if mult == 1.0:
            return proposal
        margin = _safe_float(proposal.get("margin")) * mult
        leverage = _safe_float(proposal.get("leverage"), 5.0) * (0.85 + mult * 0.15)
        proposal["margin"] = round(max(margin, 8.0), 4)
        proposal["leverage"] = round(max(2.0, min(leverage, 20.0)), 2)
        proposal["volatility_size_multiplier"] = round(mult, 4)
        return proposal
