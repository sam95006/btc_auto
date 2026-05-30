from config.exit_config import (
    BREAK_EVEN_AFTER_TP1,
    RISK_PCT,
    SIGNAL_REVERSE_MIN_CONFIDENCE,
    STOP_R,
    TP_LADDER,
)
from config.sandbox_exit_config import (
    SANDBOX_ABS_EXIT_ENABLED,
    SANDBOX_SL_ABS_USD,
    SANDBOX_TP_ABS_USD,
)
from backend.trading.sandbox_mode import sandbox_active


def build_r_exit_state(margin, quantity):
    margin = float(margin or 0.0)
    quantity = float(quantity or 0.0)
    risk_r_usd = max(margin * RISK_PCT, 1e-6)
    return {
        "initial_quantity": quantity,
        "initial_margin": margin,
        "risk_r_usd": round(risk_r_usd, 6),
        "tp1_done": False,
        "tp2_done": False,
        "tp3_done": False,
        "stop_at_be": False,
    }


def ensure_r_exit_state(position):
    position = dict(position or {})
    state = dict(position.get("r_exit_state") or {})
    margin = float(position.get("margin", 0.0) or 0.0)
    quantity = float(position.get("quantity", 0.0) or 0.0)
    init_margin = float(state.get("initial_margin", 0.0) or 0.0)
    if not state or not state.get("risk_r_usd") or (margin > 0 and init_margin < margin * 0.2):
        state = build_r_exit_state(margin, quantity)
    state.setdefault("initial_quantity", quantity)
    state.setdefault("initial_margin", margin)
    state.setdefault("risk_r_usd", max(margin * RISK_PCT, 1e-6))
    for key in ("tp1_done", "tp2_done", "tp3_done", "stop_at_be"):
        state.setdefault(key, False)
    position["r_exit_state"] = state
    return position


class RExitEngine:
    def evaluate(self, position, price, signal=None):
        position = ensure_r_exit_state(position)
        state = position["r_exit_state"]
        unrealized = float(position.get("unrealized_pnl", 0.0) or 0.0)
        risk_r_usd = float(state.get("risk_r_usd", 0.0) or 0.0)
        if risk_r_usd <= 0:
            return None

        pnl_r = unrealized / risk_r_usd
        signal = signal or {}
        action = str(signal.get("action", "HOLD")).upper()
        confidence = float(signal.get("confidence", 0.0) or 0.0)
        side = str(position.get("side", "BUY")).upper()

        if sandbox_active() and SANDBOX_ABS_EXIT_ENABLED:
            if unrealized >= float(SANDBOX_TP_ABS_USD):
                return {
                    "type": "full",
                    "reason": "sandbox_abs_take_profit",
                    "exit_class": "take_profit",
                    "pnl_r": round(pnl_r, 4),
                }
            if unrealized <= -float(SANDBOX_SL_ABS_USD):
                return {
                    "type": "full",
                    "reason": "sandbox_abs_stop_loss",
                    "exit_class": "stop_loss",
                    "pnl_r": round(pnl_r, 4),
                }

        if pnl_r <= -STOP_R:
            return {
                "type": "full",
                "reason": "r_exit_stop_loss",
                "exit_class": "stop_loss",
                "pnl_r": round(pnl_r, 4),
            }

        if state.get("stop_at_be") and pnl_r <= 0:
            return {
                "type": "full",
                "reason": "r_exit_break_even",
                "exit_class": "break_even",
                "pnl_r": round(pnl_r, 4),
            }

        for level in reversed(TP_LADDER):
            tag = level["tag"].lower()
            done_key = f"{tag}_done"
            if state.get(done_key):
                continue
            if pnl_r >= float(level["r"]):
                fraction = float(level["fraction"])
                if fraction < 1.0:
                    from backend.trading.fee_churn_guard import get_fee_churn_guard

                    ok, _reason = get_fee_churn_guard().allow_r_partial(position, unrealized)
                    if not ok:
                        continue
                exit_action = {
                    "type": "partial" if level["fraction"] < 1.0 else "full",
                    "fraction": float(level["fraction"]),
                    "reason": f"r_exit_{tag.lower()}",
                    "exit_class": "take_profit",
                    "tp_tag": level["tag"],
                    "pnl_r": round(pnl_r, 4),
                    "move_stop_to_be": bool(level.get("move_stop_to_be")) and BREAK_EVEN_AFTER_TP1,
                }
                return exit_action

        opposite = (action == "SELL" and side == "BUY") or (action == "BUY" and side == "SELL")
        if opposite and confidence >= SIGNAL_REVERSE_MIN_CONFIDENCE:
            return {
                "type": "full",
                "reason": "r_exit_signal_reverse",
                "exit_class": "signal_exit",
                "pnl_r": round(pnl_r, 4),
            }

        return None

    def apply_exit_state_update(self, position, exit_action):
        position = ensure_r_exit_state(position)
        state = position["r_exit_state"]
        tp_tag = str(exit_action.get("tp_tag") or "").upper()
        if tp_tag:
            state[f"{tp_tag.lower()}_done"] = True
        if exit_action.get("move_stop_to_be"):
            state["stop_at_be"] = True
        if exit_action.get("type") == "full":
            for tag in ("tp1", "tp2", "tp3"):
                state[f"{tag}_done"] = True
        position["r_exit_state"] = state
        return position
