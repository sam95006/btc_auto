from __future__ import annotations

import time

from config.fleet_routing_config import validate_futures_open_route
from config.funding_arb_config import (
    FUNDING_ARB_CAPITAL_FRACTION,
    FUNDING_ARB_ENABLED,
    FUNDING_ARB_INTERVAL_SEC,
    FUNDING_ARB_MAX_LEVERAGE,
    FUNDING_ARB_MAX_PROPOSALS,
    FUNDING_ARB_MIN_ABS_RATE,
    FUNDING_ARB_MIN_CONFIDENCE,
)
from config.radar_dispatch_config import RADAR_MIN_MARGIN


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class FundingArbProposer:
    """Funding-rate bias proposals: lean long when funding is negative, short when positive."""

    def __init__(self):
        self._last_run = 0.0

    def enabled(self):
        return FUNDING_ARB_ENABLED

    def collect_proposals(self, prices, market_contexts=None, positions=None, deployable_pool=0.0):
        if not self.enabled():
            return []
        now = time.time()
        if now - self._last_run < FUNDING_ARB_INTERVAL_SEC:
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
            if symbol in held:
                continue

            ctx = dict(market_contexts.get(fleet, {}) or {})
            funding = _safe_float(ctx.get("funding_rate"))
            if abs(funding) < FUNDING_ARB_MIN_ABS_RATE:
                continue
            if str(ctx.get("liquidity_status") or "healthy") != "healthy":
                continue
            if str(ctx.get("spread_status") or "normal") != "normal":
                continue
            if str(ctx.get("funding_risk") or "normal") == "elevated" and abs(funding) < FUNDING_ARB_MIN_ABS_RATE * 2:
                continue

            side = "BUY" if funding < 0 else "SELL"
            confidence = min(0.74, FUNDING_ARB_MIN_CONFIDENCE + abs(funding) * 4500.0)
            if confidence < FUNDING_ARB_MIN_CONFIDENCE:
                continue

            ok_route, _ = validate_futures_open_route(fleet, symbol)
            if not ok_route:
                continue

            margin = max(
                RADAR_MIN_MARGIN,
                min(deployable_pool * FUNDING_ARB_CAPITAL_FRACTION / max(FUNDING_ARB_MAX_PROPOSALS, 1), 50.0),
            )
            if margin <= 0:
                continue

            proposals.append(
                {
                    "fleet": fleet,
                    "symbol": symbol,
                    "symbol_override": symbol,
                    "side": side,
                    "margin": round(margin, 4),
                    "leverage": round(min(FUNDING_ARB_MAX_LEVERAGE, 6.0 + confidence * 4.0), 2),
                    "adjusted_confidence": round(confidence, 4),
                    "raw_confidence": round(confidence, 4),
                    "reason": f"funding_arb:{side.lower()}:rate={round(funding, 6)}",
                    "decision_source": "funding_arb_proposer",
                    "strategy_key": "funding_arb_proposer",
                    "capital_pool": "funding_arb",
                    "proposer": "funding_arb",
                    "ai_rationale": f"Funding bias {funding:+.6f} → {side}",
                    "market_type": "futures",
                }
            )
            if len(proposals) >= FUNDING_ARB_MAX_PROPOSALS:
                break

        return proposals
