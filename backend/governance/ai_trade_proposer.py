from __future__ import annotations

import os

from config.radar_dispatch_config import CORE_FLEET_SYMBOLS, RADAR_MAX_LEVERAGE, RADAR_MIN_MARGIN
from config.fleet_routing_config import validate_futures_open_route
from config.ai_trading_config import (
    AI_LED_INCLUDE_CORE_FLEETS,
    AI_LED_MIN_CONFIDENCE,
    AI_LED_PRIMARY_MODE,
    AI_LED_TRADING_ENABLED,
)


def _env_bool(name, default=True):
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return default


class AiTradeProposer:
    """Build executable RADAR proposals from LLM outputs (AI-led path)."""

    def __init__(self, llm_gateway=None, trade_proposal_service=None):
        self.llm_gateway = llm_gateway
        self.trade_proposal_service = trade_proposal_service
        self.enabled = AI_LED_TRADING_ENABLED
        self.primary_mode = AI_LED_PRIMARY_MODE
        self.include_core_fleets = AI_LED_INCLUDE_CORE_FLEETS
        self.min_confidence = AI_LED_MIN_CONFIDENCE

    def collect_proposals(self, context):
        if not self.enabled:
            return []
        proposals = []
        proposals.extend(self._from_radar_llm(context.get("radar_llm_items") or []))
        proposals.extend(self._from_agent_output(context.get("agent_output") or {}))
        proposals.extend(self._from_llm_task(context))
        if self.include_core_fleets:
            proposals.extend(self._from_core_fleet_context(context))
        return self._dedupe(proposals)[: int(os.getenv("NEXUS_AI_PROPOSAL_MAX_PER_TICK", "5") or 5)]

    def _from_core_fleet_context(self, context):
        rows = []
        fleets = context.get("core_fleets") or {}
        for fleet, data in fleets.items():
            fleet = str(fleet).upper()
            if fleet == "RADAR":
                continue
            symbol = str(data.get("symbol") or "").upper()
            signal = data.get("signal") or {}
            action = str(signal.get("action") or "HOLD").upper()
            if action not in {"BUY", "SELL"}:
                continue
            confidence = _safe_float(signal.get("confidence", 0.5))
            if confidence < self.min_confidence:
                continue
            row = self._build_request(symbol, action, confidence, "llm_core_signal", signal.get("reason"), fleet=fleet)
            if row:
                rows.append(row)
        return rows

    def _from_radar_llm(self, items):
        rows = []
        for item in list(items or []):
            symbol = str(item.get("symbol") or "").upper().replace("/", "")
            if not symbol or symbol in CORE_FLEET_SYMBOLS:
                continue
            side = "BUY" if str(item.get("candidate_side") or "LONG").upper() in {"LONG", "BUY"} else "SELL"
            confidence = _safe_float(item.get("llm_confidence") or item.get("candidate_score", 0) / 100.0)
            if confidence < self.min_confidence:
                continue
            rows.append(self._build_request(symbol, side, confidence, "radar_llm", item.get("llm_rationale")))
        return rows

    def _from_agent_output(self, output):
        output = dict(output or {})
        rows = []
        for item in list(output.get("trade_proposals") or output.get("ranked_proposals") or []):
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper().replace("/", "")
            if not symbol:
                continue
            fleet = str(item.get("fleet") or "RADAR").upper()
            if fleet != "RADAR" and symbol in CORE_FLEET_SYMBOLS:
                continue
            side = str(item.get("side", "BUY")).upper()
            if side not in {"BUY", "SELL"}:
                side = "BUY" if side in {"LONG"} else "SELL"
            confidence = _safe_float(item.get("confidence", 0.55))
            if confidence < self.min_confidence:
                continue
            rows.append(
                self._build_request(
                    symbol,
                    side,
                    confidence,
                    "llm_agent",
                    item.get("rationale") or item.get("reason"),
                    fleet=fleet if fleet != "RADAR" else "RADAR",
                )
            )
        return rows

    def _from_llm_task(self, context):
        if not self.llm_gateway or not getattr(self.llm_gateway, "enabled", lambda: False)():
            return []
        payload = {
            "positions": (context.get("positions") or [])[:12],
            "market_context": context.get("market_context") or {},
            "learning_blocked_symbols": context.get("blocked_symbols") or [],
            "news_headlines": context.get("news_headlines") or [],
            "radar_candidates": (context.get("radar_scan") or {}).get("candidates") or [],
        }
        result = self.llm_gateway.run_task("trade_proposer", payload, fallback_output={})
        output = result.get("output") if isinstance(result.get("output"), dict) else result
        if not isinstance(output, dict):
            return []
        rows = []
        for item in output.get("trade_proposals") or []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper().replace("/", "")
            side = str(item.get("side", "BUY")).upper()
            confidence = _safe_float(item.get("confidence", 0.55))
            if confidence < self.min_confidence or not symbol:
                continue
            rows.append(
                self._build_request(
                    symbol,
                    side if side in {"BUY", "SELL"} else "BUY",
                    confidence,
                    "llm_proposer",
                    item.get("rationale"),
                )
            )
        return rows

    def _build_request(self, symbol, side, confidence, source, rationale=None, fleet="RADAR"):
        route_ok, _reason = validate_futures_open_route(fleet, symbol)
        if not route_ok:
            return None
        margin = max(RADAR_MIN_MARGIN, 12.0 + confidence * 20.0) if fleet == "RADAR" else max(20.0, 15.0 + confidence * 25.0)
        return {
            "fleet": fleet,
            "symbol": symbol,
            "symbol_override": symbol,
            "side": side,
            "margin": round(margin, 4),
            "leverage": round(min(RADAR_MAX_LEVERAGE, 5 + confidence * 10), 2),
            "reason": f"ai_led:{source}:{symbol}",
            "raw_confidence": round(confidence, 4),
            "adjusted_confidence": round(confidence, 4),
            "strategy_key": "ai_led_trade_proposer",
            "market_type": "futures",
            "capital_pool": "radar" if fleet == "RADAR" else "fleet",
            "decision_source": source,
            "proposer": source,
            "ai_rationale": str(rationale or "")[:280],
        }

    def _dedupe(self, proposals):
        seen = set()
        unique = []
        for proposal in proposals:
            if not proposal:
                continue
            key = (proposal.get("fleet"), proposal.get("symbol"), proposal.get("side"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(proposal)
        return unique
