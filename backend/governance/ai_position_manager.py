from __future__ import annotations

from datetime import datetime


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


import os

from backend.governance.ai_exit_planner import AiExitPlanner
from config.fee_churn_config import AI_LIQ_EXIT_REQUIRES_CRITICAL


def _env_float(name, default):
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return float(default)


class AiPositionManager:
    """Heuristic position review + TP plan (executed via nexus_runtime + RExitEngine)."""

    def __init__(self):
        self.exit_planner = AiExitPlanner()
        self.partial_tp_margin_pct = _env_float("NEXUS_AI_PARTIAL_TP_MARGIN_PCT", 0.06)

    def review_positions(self, positions, market_contexts=None, llm_gateway=None):
        market_contexts = market_contexts or {}
        actions = []
        tp_plans = []
        for position in list(positions or []):
            symbol = str(position.get("symbol") or "").upper()
            fleet = str(position.get("fleet") or "").upper()
            ctx = dict(market_contexts.get(fleet) or {})
            if symbol:
                ctx = {**ctx, **(market_contexts.get(symbol) or {})}
            plan = self.exit_planner.plan_for_position(position, market_context=ctx)
            if plan:
                tp_plans.append(plan)
            action = self._evaluate_one(position, ctx, plan=plan)
            if action:
                actions.append(action)
        return {
            "reviewed_at": _now(),
            "position_count": len(list(positions or [])),
            "actions": actions[:12],
            "tp_plans": tp_plans[:12],
            "mode": "heuristic_v1",
        }

    def _evaluate_one(self, position, market_context, plan=None):
        symbol = str(position.get("symbol") or "").upper()
        unrealized = _safe_float(position.get("unrealized_pnl"))
        margin = max(_safe_float(position.get("margin")), 0.01)
        pnl_pct = unrealized / margin
        liq_dist = _safe_float(market_context.get("liquidation_distance_pct"))
        liq_risk = str(market_context.get("liquidation_risk") or "").lower()
        fleet = str(position.get("fleet") or "")

        if liq_risk == "critical" or (
            not AI_LIQ_EXIT_REQUIRES_CRITICAL and liq_dist and liq_dist <= 3.5
        ):
            return {
                "symbol": symbol,
                "fleet": fleet,
                "action": "reduce_or_close",
                "urgency": "high",
                "reason": "liquidation_pressure",
                "confidence": 0.88,
            }
        if pnl_pct <= -0.22:
            return {
                "symbol": symbol,
                "fleet": fleet,
                "action": "reduce",
                "urgency": "medium",
                "reason": "drawdown_guard",
                "confidence": 0.75,
            }
        if pnl_pct >= self.partial_tp_margin_pct and liq_dist and liq_dist < 8:
            return {
                "symbol": symbol,
                "fleet": fleet,
                "action": "take_partial_profit",
                "urgency": "low",
                "reason": "profit_lock_near_liquidation_band",
                "confidence": 0.7,
            }
        if str(market_context.get("news_conflict") or "").lower() in {"1", "true", "yes"}:
            return {
                "symbol": symbol,
                "fleet": fleet,
                "action": "tighten_stop",
                "urgency": "medium",
                "reason": "news_conflict",
                "confidence": 0.65,
            }
        return None
