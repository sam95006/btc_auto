import hashlib

from config.fleet_routing_config import validate_futures_open_route
from config.leverage_config import MAX_SYSTEM_LEVERAGE, MIN_FUTURES_LEVERAGE
from backend.trading.order_idempotency_guard import OrderIdempotencyGuard


class TradingModeError(RuntimeError):
    pass


class ExecutionPermissionError(RuntimeError):
    pass


class BinanceExecutionRouter:
    FLEET_PERMISSIONS = {
        "HQ": {"spot": True, "futures": False},
        "BTC": {"spot": False, "futures": True},
        "ETH": {"spot": False, "futures": True},
        "SOL": {"spot": False, "futures": True},
        "PEPE": {"spot": False, "futures": True},
        "RADAR": {"spot": False, "futures": True},
        "NEWS": {"spot": False, "futures": False},
    }

    def __init__(self, spot_engine, futures_engine, risk_engine, dynamic_leverage_engine, trading_mode="paper", idempotency_guard=None):
        self.spot_engine = spot_engine
        self.futures_engine = futures_engine
        self.risk_engine = risk_engine
        self.dynamic_leverage_engine = dynamic_leverage_engine
        self.idempotency_guard = idempotency_guard or OrderIdempotencyGuard()
        self.trading_mode = str(trading_mode or "paper").strip().lower()
        if self.trading_mode == "live":
            raise TradingModeError("live trading mode is forbidden")

    def _check_actor(self, actor="strategy"):
        if actor == "ui":
            raise ExecutionPermissionError("ui_cannot_trade_directly")

    def _check_permission(self, fleet, market_type):
        perms = self.FLEET_PERMISSIONS.get(str(fleet).upper(), {"spot": False, "futures": False})
        if not perms.get(market_type, False):
            raise ExecutionPermissionError(f"{fleet}_cannot_trade_{market_type}")

    @staticmethod
    def _strategy_signal_hash(*parts):
        payload = "|".join(str(part or "") for part in parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def route_spot_order(self, fleet, side, price, margin, reason, actor="strategy", symbol=None):
        self._check_actor(actor)
        self._check_permission(fleet, "spot")
        symbol = str(symbol or "").strip().upper()
        signal_hash = self._strategy_signal_hash(fleet, side, reason, price, margin, symbol, "spot")
        allowed, fingerprint = self.idempotency_guard.claim(
            fleet=fleet,
            symbol=symbol,
            side=side,
            strategy_signal_hash=signal_hash,
            metadata={"market_type": "spot", "reason": reason},
        )
        if not allowed:
            raise ExecutionPermissionError(f"duplicate_order_blocked:{fingerprint}")
        return self.spot_engine.market_order(
            fleet,
            side,
            price,
            margin,
            leverage=1.0,
            reason=reason,
            symbol_override=symbol,
        )

    def route_futures_order(
        self,
        fleet,
        side,
        price,
        margin,
        reason,
        confidence_score,
        market_regime,
        risk_context=None,
        actor="strategy",
        symbol_override=None,
        capital_pool="fleet",
    ):
        self._check_actor(actor)
        self._check_permission(fleet, "futures")
        risk_context = risk_context or {}
        symbol = str(symbol_override or self.futures_engine.client.resolve_symbol(fleet)).upper()
        allowed_route, route_reason = validate_futures_open_route(fleet, symbol)
        if not allowed_route:
            raise ExecutionPermissionError(route_reason)
        signal_hash = self._strategy_signal_hash(
            fleet,
            symbol,
            side,
            reason,
            confidence_score,
            market_regime,
            risk_context.get("strategy_signal_hash"),
        )
        allowed, fingerprint = self.idempotency_guard.claim(
            fleet=fleet,
            symbol=symbol,
            side=side,
            strategy_signal_hash=signal_hash,
            metadata={
                "market_type": "futures",
                "reason": reason,
                "confidence_score": confidence_score,
                "market_regime": market_regime,
            },
        )
        if not allowed:
            raise ExecutionPermissionError(f"duplicate_order_blocked:{fingerprint}")
        proposed = self.dynamic_leverage_engine.calculate_proposed_leverage(confidence_score)
        estimated_notional = float(margin or 0.0) * max(MIN_FUTURES_LEVERAGE, float(proposed.get("proposed_leverage") or MIN_FUTURES_LEVERAGE))
        bracket = self.futures_engine.client.get_symbol_leverage_bracket(symbol, estimated_notional=estimated_notional)
        risk_context = dict(risk_context)
        risk_context["symbol_max_leverage"] = int(bracket.get("initialLeverage") or MAX_SYSTEM_LEVERAGE)
        leverage_plan = self.risk_engine.calculate_final_leverage(
            symbol=symbol,
            fleet=fleet,
            confidence_score=confidence_score,
            market_regime=market_regime,
            risk_context=risk_context,
            estimated_notional=estimated_notional,
        )
        final_leverage = int(leverage_plan["final_leverage"])
        forced = int(risk_context.get("pure_ai_force_leverage") or 0)
        if forced >= MIN_FUTURES_LEVERAGE and final_leverage < MIN_FUTURES_LEVERAGE:
            symbol_cap = int(risk_context.get("symbol_max_leverage") or forced)
            final_leverage = min(forced, symbol_cap)
        if final_leverage < MIN_FUTURES_LEVERAGE:
            raise ExecutionPermissionError("final_leverage_below_minimum")
        if final_leverage > MAX_SYSTEM_LEVERAGE:
            raise ExecutionPermissionError("final_leverage_above_system_cap")
        self.futures_engine.client.set_margin_type_isolated(symbol)
        self.futures_engine.client.set_leverage(symbol, final_leverage)
        expected_slippage_bps = float(risk_context.get("worst_slippage_bps") or 0.0)
        order, position = self.futures_engine.market_order(
            fleet=fleet,
            side=side,
            price=price,
            margin=margin,
            leverage=final_leverage,
            reason=reason,
            symbol_override=symbol,
            capital_pool=capital_pool,
            expected_slippage_bps=expected_slippage_bps,
            prefer_limit=risk_context.get("prefer_limit"),
        )
        order["leverage_status"] = dict(leverage_plan)
        position["leverage_status"] = dict(leverage_plan)
        return order, position
