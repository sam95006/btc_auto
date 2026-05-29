"""Spot long + futures short funding harvest (market-neutral pair)."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from config.fleet_routing_config import validate_futures_open_route
from config.market_neutral_config import (
    MARKET_NEUTRAL_CAPITAL_PCT,
    MARKET_NEUTRAL_ENABLED,
    MARKET_NEUTRAL_INTERVAL_SEC,
    MARKET_NEUTRAL_LEG_MARGIN_MIN,
    MARKET_NEUTRAL_MAX_POSITIONS,
    MARKET_NEUTRAL_MIN_FUNDING_RATE,
    MARKET_NEUTRAL_PAUSE_RADAR,
)

logger = logging.getLogger(__name__)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


class MarketNeutralFundingEngine:
    FLEET = "RADAR"

    def __init__(self):
        self._last_scan = 0.0
        self._open_pairs: Dict[str, Dict[str, Any]] = {}

    def enabled(self) -> bool:
        return MARKET_NEUTRAL_ENABLED

    def pause_radar_directional(self) -> bool:
        return MARKET_NEUTRAL_PAUSE_RADAR and bool(self._open_pairs)

    def pool_budget(self, total_equity: float) -> float:
        return max(0.0, _safe_float(total_equity) * MARKET_NEUTRAL_CAPITAL_PCT)

    def collect_proposals(
        self,
        market_contexts: Optional[Dict[str, Any]] = None,
        *,
        total_equity: float = 0.0,
        held_symbols: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        if not self.enabled():
            return []
        now = time.time()
        if now - self._last_scan < MARKET_NEUTRAL_INTERVAL_SEC:
            return []
        self._last_scan = now

        held_symbols = {str(s).upper() for s in (held_symbols or set())}
        budget = self.pool_budget(total_equity)
        if budget < MARKET_NEUTRAL_LEG_MARGIN_MIN * 2:
            return []

        leg_margin = max(MARKET_NEUTRAL_LEG_MARGIN_MIN, budget / max(MARKET_NEUTRAL_MAX_POSITIONS, 1) / 2.0)
        proposals = []
        contexts = dict(market_contexts or {})

        for key, ctx in contexts.items():
            if len(self._open_pairs) + len(proposals) >= MARKET_NEUTRAL_MAX_POSITIONS:
                break
            symbol = str(ctx.get("symbol") or key or "").upper()
            if not symbol.endswith("USDT") or symbol in held_symbols:
                continue
            funding = _safe_float(ctx.get("funding_rate"))
            if funding < MARKET_NEUTRAL_MIN_FUNDING_RATE:
                continue
            if not ctx.get("coingecko_liquidity_ok", True):
                continue
            ok, _ = validate_futures_open_route("RADAR", symbol)
            if not ok:
                continue
            proposals.append(
                {
                    "fleet": self.FLEET,
                    "symbol": symbol,
                    "side": "NEUTRAL_HEDGE",
                    "margin": round(leg_margin, 4),
                    "leverage": 1.0,
                    "strategy_key": "market_neutral_funding",
                    "capital_pool": "market_neutral",
                    "decision_source": "market_neutral_funding",
                    "proposer": "market_neutral_engine",
                    "funding_rate": funding,
                    "confidence_score": min(100.0, 60.0 + funding * 50_000.0),
                }
            )
        return proposals[:MARKET_NEUTRAL_MAX_POSITIONS]

    def register_pair(self, symbol: str, spot_order: Dict[str, Any], futures_order: Dict[str, Any]) -> None:
        symbol = str(symbol or "").upper()
        self._open_pairs[symbol] = {
            "symbol": symbol,
            "spot_order_id": spot_order.get("orderId") or spot_order.get("id"),
            "futures_order_id": futures_order.get("orderId") or futures_order.get("id"),
            "opened_at": time.time(),
        }

    def execute_hedge(
        self,
        execution_router,
        symbol: str,
        price: float,
        margin: float,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if not execution_router:
            return None, None
        symbol = str(symbol or "").upper()
        try:
            spot_order = execution_router.route_spot_order(
                "HQ",
                "BUY",
                price,
                margin,
                reason=f"market_neutral:spot:{symbol}",
                symbol=symbol,
            )
            futures_order, _pos = execution_router.route_futures_order(
                "RADAR",
                "SELL",
                price,
                margin,
                reason=f"market_neutral:futures:{symbol}",
                confidence_score=0.7,
                market_regime="market_neutral",
                symbol_override=symbol,
                capital_pool="market_neutral",
            )
            self.register_pair(symbol, spot_order or {}, futures_order or {})
            return spot_order, futures_order
        except Exception as exc:
            logger.warning("market_neutral hedge failed %s: %s", symbol, exc)
            return None, None

    def emergency_flatten_one_leg(self, execution_router, symbol: str, price: float, missing_leg: str) -> None:
        """If one leg missing, flatten the other (best-effort)."""
        symbol = str(symbol or "").upper()
        if not execution_router:
            return
        try:
            if missing_leg == "spot":
                execution_router.route_futures_order(
                    "RADAR",
                    "BUY",
                    price,
                    MARKET_NEUTRAL_LEG_MARGIN_MIN,
                    reason=f"market_neutral:hedge_repair:{symbol}",
                    confidence_score=0.5,
                    market_regime="market_neutral",
                    symbol_override=symbol,
                    capital_pool="market_neutral",
                )
            else:
                execution_router.route_spot_order(
                    "HQ",
                    "SELL",
                    price,
                    MARKET_NEUTRAL_LEG_MARGIN_MIN,
                    reason=f"market_neutral:hedge_repair:{symbol}",
                    symbol=symbol,
                )
        except Exception as exc:
            logger.warning("market_neutral repair failed %s: %s", symbol, exc)
        self._open_pairs.pop(symbol, None)

    def status_snapshot(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled(),
            "open_pairs": list(self._open_pairs.keys()),
            "pause_radar": self.pause_radar_directional(),
            "capital_pct": MARKET_NEUTRAL_CAPITAL_PCT,
        }
