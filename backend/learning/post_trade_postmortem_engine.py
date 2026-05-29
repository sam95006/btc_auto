"""Post-loss review: tactical loss diagnosis + dynamic blocklist + matrix penalty."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from backend.learning.dynamic_blocklist import DynamicBlocklist
from config.confidence_matrix_config import POSTMORTEM_MACRO_PENALTY

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


class PostTradePostMortemEngine:
    def __init__(self, llm_gateway=None, blocklist: Optional[DynamicBlocklist] = None):
        self.llm_gateway = llm_gateway
        self.blocklist = blocklist or DynamicBlocklist()

    def on_trade_close(self, trade: Dict[str, Any], context_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        trade = dict(trade or {})
        pnl = _safe_float(trade.get("pnl"))
        if pnl >= 0:
            return {"skipped": "win_or_breakeven"}

        context_snapshot = dict(context_snapshot or {})
        diagnosis = self._diagnose(trade, context_snapshot)
        if diagnosis.get("is_tactical_loss"):
            symbol = str(diagnosis.get("target_symbol") or trade.get("symbol") or "").upper()
            minutes = int(diagnosis.get("block_duration_minutes") or 120)
            if symbol:
                self.blocklist.block_symbol(symbol, minutes, reason=diagnosis.get("action_recommendation", ""))
            features = list(diagnosis.get("toxic_features") or [])
            if features:
                self.blocklist.add_feature_penalty(features, POSTMORTEM_MACRO_PENALTY, hours=24.0)

        diagnosis["timestamp"] = _now()
        diagnosis["order_id"] = trade.get("id") or trade.get("order_id")
        return diagnosis

    def _diagnose(self, trade: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        llm_result = self._llm_diagnose(trade, ctx)
        if llm_result:
            return llm_result
        return self._rule_diagnose(trade, ctx)

    def _rule_diagnose(self, trade: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        toxic = []
        if ctx.get("external_oi_stress"):
            toxic.append("oi_stress")
        if ctx.get("external_whale_dump_alert"):
            toxic.append("high_inflow")
        if str(ctx.get("market_regime_ai") or "").upper() == "HIGH_RISK_MACRO":
            toxic.append("macro_bearish")
        regime_chop = str(ctx.get("market_regime_ai") or "").upper() == "CHOP_RNG"
        fleet = str(trade.get("fleet") or "").upper()
        is_tactical = bool(toxic) or (regime_chop and fleet in {"PEPE", "RADAR"})
        return {
            "is_tactical_loss": is_tactical,
            "toxic_features": toxic,
            "action_recommendation": "BLOCK_STRATEGY" if is_tactical else "MONITOR",
            "target_symbol": trade.get("symbol"),
            "block_duration_minutes": 120 if is_tactical else 0,
            "source": "rules",
        }

    def _llm_diagnose(self, trade: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.llm_gateway or not getattr(self.llm_gateway, "enabled", lambda: False)():
            return None
        try:
            payload = {
                "trade": {
                    "symbol": trade.get("symbol"),
                    "fleet": trade.get("fleet"),
                    "pnl": trade.get("pnl"),
                    "exit_class": trade.get("exit_class"),
                    "exit_reason": trade.get("exit_reason") or trade.get("reason"),
                    "confidence_score": (trade.get("confidence_matrix") or {}).get("confidence_score"),
                },
                "context": {
                    "rsi_14": ctx.get("rsi_14"),
                    "atr_pct": ctx.get("atr_pct"),
                    "market_regime_ai": ctx.get("market_regime_ai"),
                    "funding_rate": ctx.get("funding_rate"),
                    "external_alerts": ctx.get("external_market_alerts"),
                },
            }
            result = self.llm_gateway.run_task("post_mortem", payload, fallback_output={})
            output = result.get("output") if isinstance(result.get("output"), dict) else result
            if not isinstance(output, dict):
                return None
            return {
                "is_tactical_loss": bool(output.get("is_tactical_loss")),
                "toxic_features": list(output.get("toxic_features") or []),
                "action_recommendation": output.get("action_recommendation", "MONITOR"),
                "target_symbol": output.get("target_symbol") or trade.get("symbol"),
                "block_duration_minutes": int(output.get("block_duration_minutes") or 0),
                "source": "llm",
                "rationale": output.get("rationale", ""),
            }
        except Exception as exc:
            logger.warning("post_mortem llm failed: %s", exc)
            return None
