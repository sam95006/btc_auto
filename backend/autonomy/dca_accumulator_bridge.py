from __future__ import annotations

import time

from config.dca_accumulator_config import (
    DCA_ACCUMULATOR_ENABLED,
    DCA_FLEET_MAP,
    DCA_INTERVAL_SEC,
    DCA_MARGIN_USD,
    DCA_MIN_CONFIDENCE,
    DCA_SYMBOLS,
)
from config.fleet_routing_config import validate_futures_open_route
from config.radar_dispatch_config import RADAR_MAX_LEVERAGE


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class DcaAccumulatorBridge:
    """Slow DCA layer for core pairs (long bias accumulation)."""

    def __init__(self):
        self._last_run = 0.0
        self._cursor = 0

    def enabled(self):
        return DCA_ACCUMULATOR_ENABLED

    def collect_proposals(self, prices, market_contexts=None, positions=None, deployable_pool=0.0):
        if not self.enabled():
            return []
        now = time.time()
        if now - self._last_run < DCA_INTERVAL_SEC:
            return []
        self._last_run = now

        symbols = list(DCA_SYMBOLS)
        if not symbols:
            return []
        symbol = symbols[self._cursor % len(symbols)]
        self._cursor += 1

        fleet = DCA_FLEET_MAP.get(symbol, "BTC")
        ctx = dict((market_contexts or {}).get(fleet, {}) or {})
        if str(ctx.get("market_regime") or "normal") in {"crash", "liquidation_risk", "news_shock"}:
            return []

        held = {str(item.get("symbol") or "").upper() for item in list(positions or [])}
        if symbol in held:
            return []

        ok_route, _ = validate_futures_open_route(fleet, symbol)
        if not ok_route:
            return []

        if _safe_float(deployable_pool) < DCA_MARGIN_USD:
            return []

        return [
            {
                "fleet": fleet,
                "symbol": symbol,
                "symbol_override": symbol,
                "side": "BUY",
                "margin": round(DCA_MARGIN_USD, 4),
                "leverage": min(RADAR_MAX_LEVERAGE, 5.0),
                "adjusted_confidence": DCA_MIN_CONFIDENCE,
                "raw_confidence": DCA_MIN_CONFIDENCE,
                "reason": f"dca_accumulator:{symbol.lower()}",
                "decision_source": "dca_accumulator",
                "strategy_key": "dca_accumulator",
                "capital_pool": "dca",
                "proposer": "dca_accumulator",
                "ai_rationale": "Scheduled DCA accumulation slot",
                "market_type": "futures",
            }
        ]
