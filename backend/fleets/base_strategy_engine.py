from backend.config.capital_config import MAX_FUTURES_LEVERAGE, MIN_FUTURES_LEVERAGE, MIN_FUTURES_MARGIN
from backend.trading.r_exit_engine import RExitEngine
from config.exit_config import CORE_FLEETS


class BaseFleetStrategyEngine:
    MIN_MARGIN_PER_ORDER = MIN_FUTURES_MARGIN
    BASE_LEVERAGE = {
        "BTC": 16.0,
        "ETH": 16.0,
        "SOL": 17.0,
        "PEPE": 15.0,
    }

    def __init__(self, fleet, execution_engine, position_manager, risk_engine, event_bus, learning_feedback=None):
        self.fleet = fleet
        self.execution_engine = execution_engine
        self.position_manager = position_manager
        self.risk_engine = risk_engine
        self.event_bus = event_bus
        self.learning_feedback = learning_feedback
        self.r_exit_engine = RExitEngine()
        self.last_signal = "HOLD"
        self.last_reason = "Initialized"

    def _recent_closed_trades(self, lookback=24):
        trades = self.execution_engine.recent_trades(limit=lookback * 3)
        return [trade for trade in trades if trade.get("event") == "CLOSE" and trade.get("fleet") == self.fleet][:lookback]

    def _recent_win_rate(self, lookback=20):
        closes = self._recent_closed_trades(lookback)
        if not closes:
            return 0.5
        wins = sum(1 for trade in closes if float(trade.get("pnl", 0.0) or 0.0) > 0)
        return wins / len(closes)

    def _performance_profile(self, lookback=24):
        closes = self._recent_closed_trades(lookback)
        if not closes:
            return {
                "trade_count": 0,
                "win_rate": 0.5,
                "loss_rate": 0.5,
                "consecutive_losses": 0,
                "consecutive_wins": 0,
                "avg_pnl": 0.0,
                "aggression_scale": 1.12,
                "precision_scale": 1.0,
                "recovery_mode": False,
            }

        consecutive_losses = 0
        consecutive_wins = 0
        for trade in closes:
            pnl = float(trade.get("pnl", 0.0) or 0.0)
            if pnl < 0 and consecutive_wins == 0:
                consecutive_losses += 1
            else:
                break
        for trade in closes:
            pnl = float(trade.get("pnl", 0.0) or 0.0)
            if pnl > 0 and consecutive_losses == 0:
                consecutive_wins += 1
            else:
                break

        win_rate = self._recent_win_rate(lookback)
        avg_pnl = sum(float(trade.get("pnl", 0.0) or 0.0) for trade in closes) / len(closes)
        loss_rate = 1.0 - win_rate
        aggression_scale = 1.15 + max(0.0, win_rate - 0.5) * 0.7 - min(consecutive_losses, 4) * 0.08
        aggression_scale = min(1.55, max(0.82, aggression_scale))
        precision_scale = 1.0 + min(consecutive_losses, 4) * 0.07

        return {
            "trade_count": len(closes),
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "consecutive_losses": consecutive_losses,
            "consecutive_wins": consecutive_wins,
            "avg_pnl": avg_pnl,
            "aggression_scale": aggression_scale,
            "precision_scale": precision_scale,
            "recovery_mode": consecutive_losses >= 2,
        }

    def build_open_request(self, signal, price, market_context=None):
        action = signal["action"]
        self.last_signal = action
        self.last_reason = signal["reason"]
        if action == "HOLD":
            return None

        side = "BUY" if action == "BUY" else "SELL"
        strategy_key = f"{self.fleet.lower()}_adaptive_strategy"
        raw_confidence = max(0.0, min(1.0, float(signal.get("confidence", 0.0) or 0.0)))
        profile = self._performance_profile()
        guidance = (
            self.learning_feedback.get_strategy_guidance(
                self.fleet,
                strategy_key,
                (market_context or {}).get("market_regime", "normal"),
                market_context=market_context or {},
            )
            if self.learning_feedback
            else {}
        )
        if guidance.get("pause_new_entries"):
            self.last_reason = "learning_pause_due_to_recent_losses"
            return None
        if guidance.get("regime_blocked"):
            self.last_reason = "learning_regime_blocked"
            return None
        symbol = f"{self.fleet}USDT"
        symbol_cooldown = dict(guidance.get("symbol_cooldown", {}) or {})
        from backend.trading.sandbox_mode import sandbox_active

        if bool((symbol_cooldown.get(symbol) or {}).get("active")) and not sandbox_active():
            self.last_reason = "learning_symbol_cooldown"
            return None
        failure_flags = set(guidance.get("failure_focus_flags", []) or [])
        if "low_liquidity" in failure_flags:
            liquidity_status = str((market_context or {}).get("liquidity_status") or "healthy").lower()
            slippage_risk = str((market_context or {}).get("slippage_risk") or "normal").lower()
            oi_notional_status = str((market_context or {}).get("oi_notional_status") or "healthy").lower()
            if liquidity_status != "healthy" or slippage_risk == "elevated" or oi_notional_status != "healthy":
                self.last_reason = "learning_low_liquidity_block"
                return None
        if "news_conflict" in failure_flags and bool((market_context or {}).get("news_conflict")):
            self.last_reason = "learning_news_conflict_block"
            return None
        if "whale_conflict" in failure_flags and bool((market_context or {}).get("whale_conflict")):
            self.last_reason = "learning_whale_conflict_block"
            return None
        confidence = min(
            1.0,
            max(
                0.0,
                raw_confidence * profile["precision_scale"] - float(guidance.get("confidence_penalty", 0.0) or 0.0),
            ),
        )
        if confidence < float(guidance.get("min_confidence_threshold", 0.35) or 0.35):
            self.last_reason = "learning_confidence_gate"
            return None
        win_rate = profile["win_rate"]

        account = self.risk_engine.ledger.snapshot()["fleets"][self.fleet]
        available = float(account.get("available", 0.0) or 0.0)
        allocation = float(account.get("allocated", 0.0) or 0.0)

        desired_margin = allocation * (
            0.08
            + confidence * 0.24
            + max(0.0, win_rate - 0.5) * 0.12
        ) * profile["aggression_scale"] * float(guidance.get("aggression_multiplier", 1.0) or 1.0)
        desired_margin *= float(guidance.get("position_size_multiplier", 1.0) or 1.0)
        if self.fleet == "PEPE":
            desired_margin = min(desired_margin, max(self.MIN_MARGIN_PER_ORDER, allocation * 0.08))
        max_margin_from_alloc = allocation * 0.42
        max_margin_from_available = max(0.0, available * 0.92)
        margin = min(desired_margin, max_margin_from_alloc, max_margin_from_available)
        margin = max(self.MIN_MARGIN_PER_ORDER, margin)
        if available < self.MIN_MARGIN_PER_ORDER:
            margin = available

        base_lev = self.BASE_LEVERAGE.get(self.fleet, MIN_FUTURES_LEVERAGE)
        leverage_boost = confidence * 6.2 + max(0.0, win_rate - 0.5) * 4.0 + profile["consecutive_wins"] * 0.4
        leverage_penalty = profile["consecutive_losses"] * 0.9
        leverage = min(
            MAX_FUTURES_LEVERAGE,
            max(MIN_FUTURES_LEVERAGE, base_lev + leverage_boost - leverage_penalty),
        )
        if guidance.get("leverage_cap") is not None:
            leverage = min(leverage, float(guidance.get("leverage_cap") or leverage))
        if self.fleet == "PEPE":
            leverage = min(leverage, 15.0)

        return {
            "fleet": self.fleet,
            "side": side,
            "price": price,
            "margin": round(margin, 4),
            "leverage": round(leverage, 4),
            "reason": signal["reason"],
            "raw_confidence": raw_confidence,
            "adjusted_confidence": round(confidence, 4),
            "recent_win_rate": round(win_rate, 4),
            "reflection_profile": {
                "trade_count": profile["trade_count"],
                "loss_rate": round(profile["loss_rate"], 4),
                "consecutive_losses": profile["consecutive_losses"],
                "consecutive_wins": profile["consecutive_wins"],
                "recovery_mode": profile["recovery_mode"],
            },
            "strategy_key": strategy_key,
            "learning_guidance": guidance,
        }

    def manage_position_exits(self, signal, price):
        positions = self.position_manager.get_by_fleet(self.fleet)
        if not positions:
            return []
        position = positions[0]
        if self.fleet not in CORE_FLEETS:
            return self._legacy_close_if_needed(signal, price, position)

        exit_action = self.r_exit_engine.evaluate(position, price, signal=signal)
        if not exit_action:
            return []

        trades = []
        trade = None
        if exit_action["type"] == "partial":
            from backend.trading.fee_churn_guard import get_fee_churn_guard

            trade = self.execution_engine.reduce_position(
                position["id"],
                exit_action["fraction"],
                price,
                reason=exit_action["reason"],
            )
            if trade:
                get_fee_churn_guard().mark_partial_exit(position["id"])
        else:
            trade = self.execution_engine.close_position(position["id"], price, reason=exit_action["reason"])

        if trade:
            updated = self.position_manager.get_position(position["id"])
            if updated:
                updated = self.r_exit_engine.apply_exit_state_update(updated, exit_action)
                self.position_manager.update_position(position["id"], {"r_exit_state": updated.get("r_exit_state")})
            trade["exit_class"] = exit_action.get("exit_class")
            trade["pnl_r"] = exit_action.get("pnl_r")
            trades.append(trade)
        return trades

    def _legacy_close_if_needed(self, signal, price, position):
        action = signal["action"]
        profile = self._performance_profile()
        unrealized = float(position.get("unrealized_pnl", 0.0) or 0.0)
        margin = float(position.get("margin", 0.0) or 0.0)
        confidence = float(signal.get("confidence", 0.0) or 0.0)
        adaptive_stop = margin * max(0.085, 0.15 - profile["consecutive_losses"] * 0.018)
        adaptive_take = margin * (0.14 + max(0.0, profile["win_rate"] - 0.5) * 0.12)
        should_close = (
            (action == "SELL" and position["side"] == "BUY")
            or (action == "BUY" and position["side"] == "SELL")
            or unrealized <= -adaptive_stop
            or (unrealized >= adaptive_take and action == "HOLD")
            or (unrealized >= adaptive_take * 0.8 and confidence < 0.42)
        )
        if not should_close:
            return []
        trade = self.execution_engine.close_position(position["id"], price, signal["reason"])
        return [trade] if trade else []

    def maybe_close_position(self, signal, price):
        trades = self.manage_position_exits(signal, price)
        return trades[-1] if trades else None
