from __future__ import annotations

import time

from backend.trading.grid_trading_engine import GridTradingEngine
from config.fleet_routing_config import validate_futures_open_route
from config.grid_trading_config import (
    GRID_CAPITAL_POOL_FRACTION,
    GRID_LOOKBACK_TICKS,
    GRID_MAX_PROPOSALS_PER_TICK,
    GRID_MAX_VOLATILITY_PERCENTILE,
    GRID_MIN_CONFIDENCE,
    GRID_RANGE_MAX_DEVIATION_PCT,
    GRID_SIGNAL_INTERVAL_SEC,
    GRID_SPACING_PCT,
    GRID_TRADING_ENABLED,
)
from config.radar_dispatch_config import RADAR_MAX_LEVERAGE, RADAR_MIN_MARGIN


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class GridSignalBridge:
    """P3 range-grid proposals (sideways markets) — passes governance + validation in runtime."""

    def __init__(self):
        self._last_run = 0.0
        self._price_history = {}
        self.engine = GridTradingEngine(
            lookback_ticks=GRID_LOOKBACK_TICKS,
            spacing_pct=GRID_SPACING_PCT,
            range_max_deviation_pct=GRID_RANGE_MAX_DEVIATION_PCT,
        )

    def enabled(self):
        return GRID_TRADING_ENABLED

    def collect_proposals(self, prices, market_contexts=None, positions=None, deployable_pool=0.0):
        if not self.enabled():
            return []
        now = time.time()
        if now - self._last_run < GRID_SIGNAL_INTERVAL_SEC:
            return []
        self._last_run = now

        market_contexts = dict(market_contexts or {})
        positions = list(positions or [])
        held = {str(item.get("symbol") or "").upper() for item in positions}
        deployable_pool = max(_safe_float(deployable_pool), 0.0)
        proposals = []

        for fleet, data in (prices or {}).items():
            fleet = str(fleet).upper()
            if fleet == "RADAR":
                continue
            symbol = str((data or {}).get("symbol") or f"{fleet}USDT").upper().replace("/", "")
            price = _safe_float((data or {}).get("price"))
            if price <= 0 or symbol in held:
                continue

            history = self._price_history.setdefault(symbol, [])
            history.append(price)
            if len(history) > GRID_LOOKBACK_TICKS + 4:
                history.pop(0)

            ctx = dict(market_contexts.get(fleet, {}) or {})
            ctx["grid_max_vol"] = GRID_MAX_VOLATILITY_PERCENTILE
            signal = self.engine.evaluate(symbol, price, history, market_context=ctx)
            if not signal or signal.get("confidence", 0) < GRID_MIN_CONFIDENCE:
                continue

            ok_route, _ = validate_futures_open_route(fleet, symbol)
            if not ok_route:
                continue

            confidence = _safe_float(signal.get("confidence"))
            margin = max(
                RADAR_MIN_MARGIN,
                min(deployable_pool * GRID_CAPITAL_POOL_FRACTION / max(GRID_MAX_PROPOSALS_PER_TICK, 1), 55.0),
            )
            if margin <= 0:
                continue

            proposals.append(
                {
                    "fleet": fleet,
                    "symbol": symbol,
                    "symbol_override": symbol,
                    "side": signal["side"],
                    "margin": round(margin, 4),
                    "leverage": min(RADAR_MAX_LEVERAGE, 10.0),
                    "adjusted_confidence": round(confidence, 4),
                    "raw_confidence": round(confidence, 4),
                    "reason": f"grid_range:{signal['side'].lower()}:{signal.get('deviation_pct')}%",
                    "decision_source": "grid_signal_bridge",
                    "strategy_key": "grid_trading_engine",
                    "capital_pool": "grid",
                    "proposer": "grid_engine",
                    "ai_rationale": f"Grid mid={signal.get('mid')} spacing={signal.get('spacing')}",
                    "market_type": "futures",
                }
            )
            if len(proposals) >= GRID_MAX_PROPOSALS_PER_TICK:
                break

        return proposals
