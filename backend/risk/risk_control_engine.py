from backend.config.capital_config import RISK_LIMITS
from config.leverage_config import (
    CONSECUTIVE_LOSS_CAP,
    FLEET_LEVERAGE_CAPS,
    MAX_SYSTEM_LEVERAGE,
    MIN_FUTURES_LEVERAGE,
    PEPE_DEFAULT_MAX_LEVERAGE,
    RISK_EVENT_LEVERAGE_CAP,
)
from backend.risk.dynamic_leverage_engine import DynamicLeverageEngine


class RiskControlEngine:
    def __init__(self, ledger, pnl_tracker):
        self.ledger = ledger
        self.pnl_tracker = pnl_tracker
        self.dynamic_leverage_engine = DynamicLeverageEngine()

    def validate_order(self, order, meeting_notes=None):
        if str(order.get("market_type") or "futures").lower() == "spot":
            return self.validate_spot_order(order)
        fleet = order["fleet"]
        leverage = float(order.get("leverage", 1.0) or 1.0)
        margin = float(order.get("margin", 0.0) or 0.0)
        ds = str(order.get("decision_source") or "")
        try:
            from config.pure_ai_trading_config import PURE_AI_MAX_MARGIN_USD, pure_ai_active

            if pure_ai_active() and ds.startswith(("pure_ai", "ai_flex")):
                pool = float(order.get("deployable_pool") or 0.0)
                cap = float(PURE_AI_MAX_MARGIN_USD)
                if pool > 0:
                    cap = min(cap, pool * 0.12)
                if (
                    margin >= 1.0
                    and margin <= cap + 0.01
                    and leverage >= RISK_LIMITS["min_leverage"]
                    and leverage <= RISK_LIMITS["max_leverage"]
                ):
                    return True, "approved_pure_ai_testnet"
        except Exception:
            pass

        if leverage < RISK_LIMITS["min_leverage"]:
            return False, "leverage_below_minimum"

        if leverage > RISK_LIMITS["max_leverage"]:
            return False, "leverage_above_limit"

        if str(fleet).upper() == "RADAR" or order.get("capital_pool") == "radar":
            available = float(self.ledger.radar_available())
            ds = str(order.get("decision_source") or "")
            try:
                from config.pure_ai_trading_config import PURE_AI_MAX_MARGIN_USD, pure_ai_active

                if pure_ai_active() and ds.startswith(("pure_ai", "ai_flex")):
                    pool = float(order.get("deployable_pool") or 0.0)
                    cap = float(PURE_AI_MAX_MARGIN_USD)
                    if available > 0:
                        cap = min(cap, available * 1.02)
                    if pool > 0:
                        cap = min(cap, pool * 0.12)
                    if margin > cap + 0.01:
                        return False, "insufficient_radar_budget"
                    if margin < 1.0:
                        return False, "radar_margin_invalid"
                    return True, "approved"
            except Exception:
                pass
            if margin > available:
                return False, "insufficient_radar_budget"
            if margin < 1.0:
                return False, "radar_margin_invalid"
            return True, "approved"

        account = self.ledger.snapshot()["fleets"].get(fleet, {})
        if margin > float(account.get("available", 0.0) or 0.0):
            return False, "insufficient_available_capital"

        max_margin = float(account.get("allocated", 0.0) or 0.0) * RISK_LIMITS["max_margin_pct"]
        if margin > max_margin:
            return False, "margin_above_allocation_limit"

        notional = margin * leverage
        max_notional = float(account.get("allocated", 0.0) or 0.0) * RISK_LIMITS["max_position_notional_pct"]
        if notional > max_notional:
            return False, "position_notional_above_limit"

        fleet_pnl = self.pnl_tracker.snapshot()["fleets"].get(fleet, {}).get("total", 0.0)
        if fleet_pnl <= RISK_LIMITS["fleet_max_loss"]:
            return False, "fleet_max_loss_reached"

        return True, "approved"

    def validate_spot_order(self, order):
        margin = float(order.get("margin", 0.0) or 0.0)
        if margin <= 0:
            return False, "spot_margin_invalid"
        available_cash = float(order.get("available_cash", margin) or 0.0)
        if margin > available_cash:
            return False, "spot_insufficient_available_capital"
        max_cash_pct = float(order.get("max_cash_pct", 0.25) or 0.25)
        if available_cash > 0 and margin > available_cash * max_cash_pct:
            return False, "spot_order_above_cash_risk_limit"
        return True, "approved"

    def leverage_risk_cap(self, symbol, fleet, market_regime, risk_context=None):
        risk_context = risk_context or {}
        market_regime = str(market_regime or "").lower()
        fleet = str(fleet or "").upper()
        if market_regime in {"extreme_volatility", "crash", "news_shock", "alert_red"}:
            return {"allowed": False, "risk_cap_leverage": RISK_EVENT_LEVERAGE_CAP, "reason": "risk_cap_due_to_market_volatility"}
        if risk_context.get("alert_red"):
            return {"allowed": False, "risk_cap_leverage": RISK_EVENT_LEVERAGE_CAP, "reason": "risk_cap_due_to_alert_red"}
        if risk_context.get("liquidity_risk") or risk_context.get("news_conflict") or risk_context.get("whale_conflict"):
            return {"allowed": True, "risk_cap_leverage": RISK_EVENT_LEVERAGE_CAP, "reason": "risk_cap_due_to_context_conflict"}

        closes = [trade for trade in getattr(self.pnl_tracker, "recent_trades", lambda limit=50: [])(50) if trade.get("fleet") == fleet and trade.get("event") == "CLOSE"]
        consecutive_losses = 0
        for trade in closes:
            if float(trade.get("pnl", 0.0) or 0.0) < 0:
                consecutive_losses += 1
            else:
                break
        if consecutive_losses >= 5:
            return {"allowed": False, "risk_cap_leverage": 0, "reason": "fleet_paused_due_to_consecutive_losses"}
        if consecutive_losses >= CONSECUTIVE_LOSS_CAP:
            return {"allowed": True, "risk_cap_leverage": RISK_EVENT_LEVERAGE_CAP, "reason": "risk_cap_due_to_consecutive_losses"}

        fleet_pnl = float(self.pnl_tracker.snapshot()["fleets"].get(fleet, {}).get("total", 0.0) or 0.0)
        if fleet_pnl <= RISK_LIMITS["fleet_max_loss"]:
            return {"allowed": False, "risk_cap_leverage": 0, "reason": "fleet_daily_drawdown_limit"}

        cap = min(int(FLEET_LEVERAGE_CAPS.get(fleet, MAX_SYSTEM_LEVERAGE)), MAX_SYSTEM_LEVERAGE)
        if fleet == "PEPE" or "PEPE" in str(symbol or "").upper():
            cap = min(cap, PEPE_DEFAULT_MAX_LEVERAGE)
        return {"allowed": True, "risk_cap_leverage": cap, "reason": "fleet_risk_cap"}

    def calculate_final_leverage(self, symbol, fleet, confidence_score, market_regime, risk_context=None, estimated_notional=0.0):
        risk_context = risk_context or {}
        forced = int(risk_context.get("pure_ai_force_leverage") or 0)
        if forced >= MIN_FUTURES_LEVERAGE:
            try:
                from config.pure_ai_trading_config import pure_ai_active

                if pure_ai_active():
                    symbol_max = int(risk_context.get("symbol_max_leverage") or MAX_SYSTEM_LEVERAGE)
                    final_leverage = min(forced, symbol_max, int(MAX_SYSTEM_LEVERAGE))
                    if final_leverage >= MIN_FUTURES_LEVERAGE:
                        return {
                            "confidence_score": float(confidence_score or 0.0),
                            "proposed_leverage": forced,
                            "symbol_max_leverage": symbol_max,
                            "risk_cap_leverage": final_leverage,
                            "final_leverage": int(final_leverage),
                            "reason": "pure_ai_forced_leverage",
                        }
            except Exception:
                pass
        proposed = self.dynamic_leverage_engine.calculate_proposed_leverage(confidence_score)
        if not proposed["allowed"]:
            return {
                "confidence_score": proposed["confidence_score"],
                "proposed_leverage": 0,
                "symbol_max_leverage": 0,
                "risk_cap_leverage": 0,
                "final_leverage": 0,
                "reason": proposed["reason"],
            }

        symbol_max_leverage = int(risk_context.get("symbol_max_leverage") or MAX_SYSTEM_LEVERAGE)
        cap = self.leverage_risk_cap(symbol, fleet, market_regime, risk_context=risk_context)
        if not cap["allowed"] and cap["risk_cap_leverage"] <= 0:
            return {
                "confidence_score": proposed["confidence_score"],
                "proposed_leverage": int(proposed["proposed_leverage"]),
                "symbol_max_leverage": symbol_max_leverage,
                "risk_cap_leverage": int(cap["risk_cap_leverage"]),
                "final_leverage": 0,
                "reason": cap["reason"],
            }

        growth_cap = int(risk_context.get("growth_max_leverage") or MAX_SYSTEM_LEVERAGE)
        final_leverage = min(
            int(proposed["proposed_leverage"]),
            int(MAX_SYSTEM_LEVERAGE),
            int(symbol_max_leverage),
            int(cap["risk_cap_leverage"]),
            max(MIN_FUTURES_LEVERAGE, growth_cap),
        )
        if final_leverage < MIN_FUTURES_LEVERAGE:
            return {
                "confidence_score": proposed["confidence_score"],
                "proposed_leverage": int(proposed["proposed_leverage"]),
                "symbol_max_leverage": symbol_max_leverage,
                "risk_cap_leverage": int(cap["risk_cap_leverage"]),
                "final_leverage": 0,
                "reason": "final_leverage_below_minimum",
            }
        return {
            "confidence_score": proposed["confidence_score"],
            "proposed_leverage": int(proposed["proposed_leverage"]),
            "symbol_max_leverage": int(symbol_max_leverage),
            "risk_cap_leverage": int(cap["risk_cap_leverage"]),
            "final_leverage": int(final_leverage),
            "reason": cap["reason"],
        }

    def should_trigger_emergency(self):
        pnl = self.pnl_tracker.snapshot()
        if pnl["total_pnl"] <= RISK_LIMITS["system_daily_max_loss"]:
            return True, "system_daily_max_loss_reached"
        for fleet, item in pnl["fleets"].items():
            if item["total"] <= RISK_LIMITS["fleet_max_loss"]:
                return True, f"{fleet}_max_loss_reached"
        return False, ""
