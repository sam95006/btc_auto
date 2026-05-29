from __future__ import annotations

from config.exit_config import RISK_PCT, STOP_R, TP_LADDER
from config.execution_enhancements_config import (
    TRAILING_ACTIVATION_R,
    TRAILING_CALLBACK_R,
    TRAILING_EXIT_ADVISORY,
)
from backend.governance.ai_tp_band_planner import AiTpBandPlanner


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class AiExitPlanner:
    """Compute TP1–TP3 target prices from entry, size, and R ladder (for UI + monitoring)."""

    def __init__(self):
        self.tp_band_planner = AiTpBandPlanner()

    def plan_for_position(self, position, market_context=None):
        position = dict(position or {})
        market_context = dict(market_context or {})
        entry = _safe_float(position.get("entry_price"))
        qty = abs(_safe_float(position.get("quantity")))
        margin = _safe_float(position.get("margin"))
        mark = _safe_float(position.get("mark_price") or market_context.get("mark_price") or entry)
        side = str(position.get("side") or "BUY").upper()
        if entry <= 0 or qty <= 0 or margin <= 0:
            return None

        risk_r_usd = max(margin * RISK_PCT, 1e-6)
        unrealized = _safe_float(position.get("unrealized_pnl"))
        pnl_r = unrealized / risk_r_usd if risk_r_usd > 0 else 0.0
        sign = 1.0 if side == "BUY" else -1.0
        stop_price = entry - sign * (STOP_R * risk_r_usd / qty)

        levels = []
        state = dict(position.get("r_exit_state") or {})
        for spec in TP_LADDER:
            tag = str(spec.get("tag") or "").upper()
            done = bool(state.get(f"{tag.lower()}_done"))
            target_r = _safe_float(spec.get("r"))
            move_usd = target_r * risk_r_usd
            target_price = entry + sign * (move_usd / qty)
            levels.append(
                {
                    "tag": tag,
                    "target_r": round(target_r, 4),
                    "target_price": round(target_price, 8),
                    "fraction": _safe_float(spec.get("fraction")),
                    "done": done,
                    "hit": pnl_r >= target_r and not done,
                }
            )

        payload = {
            "symbol": str(position.get("symbol") or "").upper(),
            "fleet": str(position.get("fleet") or "").upper(),
            "side": side,
            "entry_price": round(entry, 8),
            "mark_price": round(mark, 8),
            "stop_price": round(stop_price, 8),
            "pnl_r": round(pnl_r, 4),
            "risk_r_usd": round(risk_r_usd, 4),
            "tp_levels": levels,
            "execution_mode": "nexus_tick_r_exit",
            "note": "Binance 介面 TP/SL 欄位為空屬正常；由 NEXUS 每 tick 監控 R 止盈並下 reduceOnly 單。",
        }
        advisory = self.tp_band_planner.suggest(position, market_context=market_context)
        if advisory:
            payload["tp_advisory"] = advisory
        if TRAILING_EXIT_ADVISORY and pnl_r >= TRAILING_ACTIVATION_R:
            payload["trailing_advisory"] = {
                "active": True,
                "activation_r": TRAILING_ACTIVATION_R,
                "callback_r": TRAILING_CALLBACK_R,
                "lock_r": round(max(TRAILING_ACTIVATION_R - TRAILING_CALLBACK_R, 0.0), 4),
                "note": "Advisory only; R-exit engine remains primary.",
            }
        return payload

    def plan_all(self, positions, market_contexts=None):
        market_contexts = market_contexts or {}
        rows = []
        for position in list(positions or []):
            fleet = str(position.get("fleet") or "").upper()
            ctx = dict(market_contexts.get(fleet) or {})
            plan = self.plan_for_position(position, market_context=ctx)
            if plan:
                rows.append(plan)
        return rows
