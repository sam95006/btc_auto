"""ATR-inverse margin sizing: higher volatility -> smaller margin (equal wallet R at stop)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

BASELINE_SYMBOL = "BTCUSDT"
BASELINE_FLEET = "BTC"


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


def _atr_pct(context: Optional[Dict[str, Any]]) -> float:
    ctx = dict(context or {})
    direct = _safe_float(ctx.get("atr_pct"))
    if direct > 0:
        return direct
    atr = _safe_float(ctx.get("atr_14"))
    close = _safe_float(ctx.get("close") or ctx.get("mark_price") or ctx.get("price"))
    if atr > 0 and close > 0:
        return atr / close
    vol_pct = _safe_float(ctx.get("volatility_percentile"))
    if vol_pct > 0:
        return vol_pct * 0.03
    return 0.0


class VolatilityPositionSizer:
    """
    Scale margin inversely vs BTC baseline ATR%.
    PEPE at 5x BTC vol -> ~0.2x margin (same approximate stop-dollar risk when stops are ATR-aware).
    """

    def __init__(
        self,
        *,
        min_multiplier: float = None,
        max_multiplier: float = None,
        baseline_fleet: str = BASELINE_FLEET,
    ):
        self.min_multiplier = float(
            min_multiplier if min_multiplier is not None else os.getenv("NEXUS_VOL_SIZE_MIN_MULT", "0.2")
        )
        self.max_multiplier = float(
            max_multiplier if max_multiplier is not None else os.getenv("NEXUS_VOL_SIZE_MAX_MULT", "1.0")
        )
        self.baseline_fleet = str(baseline_fleet or BASELINE_FLEET).upper()

    def margin_multiplier(
        self,
        symbol_context: Optional[Dict[str, Any]],
        market_contexts: Optional[Dict[str, Any]] = None,
    ) -> float:
        contexts = dict(market_contexts or {})
        baseline = contexts.get(self.baseline_fleet) or contexts.get(BASELINE_SYMBOL) or {}
        base_pct = _atr_pct(baseline)
        sym_pct = _atr_pct(symbol_context)
        if base_pct <= 0 or sym_pct <= 0:
            return 1.0
        ratio = sym_pct / base_pct
        mult = 1.0 / max(1.0, ratio)
        return max(self.min_multiplier, min(self.max_multiplier, mult))

    def apply_to_request(
        self,
        request: Dict[str, Any],
        symbol_context: Optional[Dict[str, Any]],
        market_contexts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request = dict(request or {})
        mult = self.margin_multiplier(symbol_context, market_contexts)
        if mult != 1.0 and request.get("margin") is not None:
            request["margin"] = round(_safe_float(request.get("margin")) * mult, 4)
            request["volatility_size_multiplier"] = round(mult, 4)
        return request

    def scale_proposal(self, proposal: Dict[str, Any], market_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Used by StrategyProposalHub after confidence sizing."""
        return self.apply_to_request(proposal, market_context, {BASELINE_FLEET: market_context or {}})
