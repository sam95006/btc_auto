import time

from config.radar_dispatch_config import (
    CORE_FLEET_SYMBOLS,
    RADAR_AUTO_TRADE_ENABLED,
    RADAR_COOLDOWN_SECONDS,
    RADAR_MARGIN_PCT_OF_BUDGET,
    RADAR_MAX_LEVERAGE,
    RADAR_MAX_OPEN_POSITIONS,
    RADAR_MIN_CANDIDATE_SCORE,
    RADAR_MIN_MARGIN,
)
from backend.trading.r_exit_engine import RExitEngine, ensure_r_exit_state


class RadarDispatchService:
    FLEET = "RADAR"

    def __init__(self, r_exit_engine=None):
        self.r_exit_engine = r_exit_engine or RExitEngine()
        self._last_open_at = {}

    def eligible_candidates(self, radar_scan):
        if not RADAR_AUTO_TRADE_ENABLED:
            return []
        candidates = list((radar_scan or {}).get("candidates") or [])
        eligible = []
        for item in candidates:
            symbol = str(item.get("symbol") or "").upper()
            score = float(item.get("candidate_score", 0.0) or 0.0)
            if not symbol or symbol in CORE_FLEET_SYMBOLS:
                continue
            if score < RADAR_MIN_CANDIDATE_SCORE:
                continue
            if item.get("reason") != "healthy_structure":
                continue
            eligible.append(item)
        return eligible[:RADAR_MAX_OPEN_POSITIONS]

    def build_open_request(self, candidate, price, market_context, ledger, growth_directives=None, learning_guidance=None):
        growth_directives = growth_directives or {}
        learning_guidance = learning_guidance or {}
        if growth_directives.get("block_new_entries") or learning_guidance.get("pause_new_entries"):
            return None
        symbol = str(candidate.get("symbol") or "").upper()
        blocked = {str(item).upper() for item in (learning_guidance.get("blocked_symbols") or [])}
        if symbol in blocked:
            return None
        cooldown = dict(learning_guidance.get("symbol_cooldown") or {}).get(symbol) or {}
        if cooldown.get("active"):
            return None
        leverage_cap = learning_guidance.get("leverage_cap")
        if leverage_cap is not None and float(leverage_cap or 0) <= 0:
            return None
        available = float(ledger.radar_available())
        if available < RADAR_MIN_MARGIN:
            return None
        score = float(candidate.get("candidate_score", 0.0) or 0.0)
        margin = max(RADAR_MIN_MARGIN, available * RADAR_MARGIN_PCT_OF_BUDGET * (score / 100.0))
        margin = min(margin, available * 0.35)
        side = "BUY" if candidate.get("candidate_side") == "LONG" else "SELL"
        confidence = min(0.95, 0.45 + score / 200.0)
        min_confidence = float(learning_guidance.get("min_confidence_threshold", 0.35) or 0.35)
        if confidence < min_confidence:
            return None
        leverage = min(RADAR_MAX_LEVERAGE, float(growth_directives.get("max_leverage", RADAR_MAX_LEVERAGE) or RADAR_MAX_LEVERAGE))
        if learning_guidance.get("leverage_cap") is not None:
            leverage = min(leverage, float(learning_guidance.get("leverage_cap") or RADAR_MAX_LEVERAGE))
        pos_mult = float(learning_guidance.get("position_size_multiplier", 1.0) or 1.0)
        margin = round(margin * max(0.35, min(1.0, pos_mult)), 4)
        symbol = str(candidate.get("symbol") or "").upper()
        return {
            "fleet": self.FLEET,
            "symbol": symbol,
            "symbol_override": symbol,
            "side": side,
            "price": price,
            "margin": round(margin, 4),
            "leverage": round(leverage, 4),
            "reason": f"radar_dispatch:{candidate.get('candidate_side', 'WATCH').lower()}:{symbol}",
            "raw_confidence": round(confidence, 4),
            "adjusted_confidence": round(confidence, 4),
            "strategy_key": "radar_market_scan_strategy",
            "market_type": "futures",
            "capital_pool": "radar",
            "candidate_score": score,
            "market_regime": market_context.get("market_regime", "normal"),
        }

    def can_open_symbol(self, symbol, learning_guidance=None):
        symbol = str(symbol or "").upper()
        learning_guidance = learning_guidance or {}
        blocked = {str(item).upper() for item in (learning_guidance.get("blocked_symbols") or [])}
        if symbol in blocked:
            return False
        cooldown = dict(learning_guidance.get("symbol_cooldown") or {}).get(symbol) or {}
        if cooldown.get("active"):
            return False
        if learning_guidance.get("pause_new_entries"):
            return False
        leverage_cap = learning_guidance.get("leverage_cap")
        if leverage_cap is not None and float(leverage_cap or 0) <= 0:
            return False
        last = float(self._last_open_at.get(symbol, 0.0) or 0.0)
        return (time.time() - last) >= RADAR_COOLDOWN_SECONDS

    def mark_open(self, symbol):
        self._last_open_at[str(symbol or "").upper()] = time.time()

    def manage_position_exits(self, position, price, signal=None, execution_engine=None, position_manager=None):
        position = ensure_r_exit_state(position)
        exit_action = self.r_exit_engine.evaluate(position, price, signal=signal or {"action": "HOLD", "confidence": 0.0})
        if not exit_action or not execution_engine:
            return []
        trades = []
        if exit_action["type"] == "partial":
            trade = execution_engine.reduce_position(position["id"], exit_action["fraction"], price, reason=exit_action["reason"])
        else:
            trade = execution_engine.close_position(position["id"], price, reason=exit_action["reason"])
        if trade and position_manager:
            updated = position_manager.get_position(position["id"])
            if updated:
                updated = self.r_exit_engine.apply_exit_state_update(updated, exit_action)
                position_manager.update_position(position["id"], {"r_exit_state": updated.get("r_exit_state")})
            trade["exit_class"] = exit_action.get("exit_class")
            trade["pnl_r"] = exit_action.get("pnl_r")
            trades.append(trade)
        elif trade:
            trade["exit_class"] = exit_action.get("exit_class")
            trade["pnl_r"] = exit_action.get("pnl_r")
            trades.append(trade)
        return trades

    def build_signal_from_candidate(self, candidate):
        side = "BUY" if candidate.get("candidate_side") == "LONG" else "SELL"
        score = float(candidate.get("candidate_score", 0.0) or 0.0)
        return {
            "action": side,
            "confidence": min(0.95, 0.45 + score / 200.0),
            "reason": f"radar_candidate_{side.lower()}",
        }
