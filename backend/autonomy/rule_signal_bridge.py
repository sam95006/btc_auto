from __future__ import annotations

import time

from config.fee_churn_config import MIN_MARGIN_USD
from config.fleet_routing_config import validate_futures_open_route
from config.multi_timeframe_config import MTF_ENTRY_LOOKBACK_TICKS, MTF_TREND_LOOKBACK_TICKS, MULTI_TIMEFRAME_ENABLED
from config.radar_dispatch_config import RADAR_MAX_LEVERAGE, RADAR_MIN_MARGIN
from config.rule_signal_config import (
    RULE_SIGNAL_BRIDGE_ENABLED,
    RULE_SIGNAL_INTERVAL_SEC,
    RULE_SIGNAL_MAX_PROPOSALS,
    RULE_SIGNAL_MIN_CONFIDENCE,
    RULE_SIGNAL_MOMENTUM_PCT,
)


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class RuleSignalBridge:
    """
    P2 / A-B: Kaizen-style zero-LLM rule proposals on a 60s cadence.
    Proposals still pass governance + validation in nexus_runtime.
    """

    def __init__(self):
        self._last_run = 0.0
        self._price_history = {}

    def enabled(self):
        return RULE_SIGNAL_BRIDGE_ENABLED

    def collect_proposals(self, prices, market_contexts=None, positions=None, deployable_pool=0.0):
        if not self.enabled():
            return []
        now = time.time()
        if now - self._last_run < RULE_SIGNAL_INTERVAL_SEC:
            return []
        self._last_run = now

        market_contexts = dict(market_contexts or {})
        positions = list(positions or [])
        held_symbols = {str(item.get("symbol") or "").upper() for item in positions}
        proposals = []

        for fleet, data in (prices or {}).items():
            fleet = str(fleet).upper()
            symbol = str((data or {}).get("symbol") or "").upper().replace("/", "")
            if not symbol:
                continue
            if not symbol.endswith("USDT"):
                symbol = f"{symbol}USDT" if len(symbol) <= 6 else symbol
            price = _safe_float((data or {}).get("price"))
            if price <= 0:
                continue
            if symbol in held_symbols:
                continue

            history = self._price_history.setdefault(symbol, [])
            history.append(price)
            max_len = max(MTF_TREND_LOOKBACK_TICKS, MTF_ENTRY_LOOKBACK_TICKS) + 2
            if len(history) > max_len:
                history.pop(0)

            if len(history) < MTF_ENTRY_LOOKBACK_TICKS + 1:
                continue

            entry_move = (history[-1] - history[-MTF_ENTRY_LOOKBACK_TICKS]) / history[-MTF_ENTRY_LOOKBACK_TICKS]
            trend_move = (
                (history[-1] - history[-min(len(history), MTF_TREND_LOOKBACK_TICKS)])
                / history[-min(len(history), MTF_TREND_LOOKBACK_TICKS)]
                if len(history) >= 3
                else entry_move
            )

            side = None
            confidence = RULE_SIGNAL_MIN_CONFIDENCE
            if MULTI_TIMEFRAME_ENABLED:
                if trend_move > RULE_SIGNAL_MOMENTUM_PCT and entry_move > 0:
                    side = "BUY"
                    confidence = min(0.72, RULE_SIGNAL_MIN_CONFIDENCE + abs(entry_move) * 40)
                elif trend_move < -RULE_SIGNAL_MOMENTUM_PCT and entry_move < 0:
                    side = "SELL"
                    confidence = min(0.72, RULE_SIGNAL_MIN_CONFIDENCE + abs(entry_move) * 40)
            else:
                if entry_move > RULE_SIGNAL_MOMENTUM_PCT:
                    side = "BUY"
                elif entry_move < -RULE_SIGNAL_MOMENTUM_PCT:
                    side = "SELL"

            if not side or confidence < RULE_SIGNAL_MIN_CONFIDENCE:
                continue

            route_fleet = fleet if fleet in {"BTC", "ETH", "SOL", "PEPE"} else "RADAR"
            ok_route, _ = validate_futures_open_route(route_fleet, symbol)
            if not ok_route and fleet in {"BTC", "ETH", "SOL", "PEPE"}:
                continue
            margin = (
                max(MIN_MARGIN_USD, RADAR_MIN_MARGIN, min(deployable_pool * 0.06, 55.0))
                if route_fleet == "RADAR"
                else max(MIN_MARGIN_USD, 20.0, min(deployable_pool * 0.08, 65.0))
            )
            if margin <= 0:
                continue

            proposals.append(
                {
                    "fleet": route_fleet,
                    "symbol": symbol,
                    "side": side,
                    "margin": round(margin, 4),
                    "leverage": min(RADAR_MAX_LEVERAGE, 12.0),
                    "raw_confidence": round(confidence, 4),
                    "adjusted_confidence": round(confidence, 4),
                    "reason": f"rule_signal_mtf:{side.lower()}:{round(entry_move * 100, 3)}pct",
                    "decision_source": "rule_signal_bridge",
                    "strategy_key": "rule_signal_bridge",
                    "capital_pool": "radar" if route_fleet == "RADAR" else "fleet",
                    "proposer": "rule_brain_ab",
                }
            )
            if len(proposals) >= RULE_SIGNAL_MAX_PROPOSALS:
                break

        return proposals
