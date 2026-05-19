import os
from datetime import datetime
from uuid import uuid4

from backend.fleets.paper_order_execution_engine import PaperOrderExecutionEngine
from backend.trading.binance_futures_testnet_client import BinanceFuturesTestnetClient
from backend.trading.r_exit_engine import build_r_exit_state


class BinanceTestnetExecutionEngine(PaperOrderExecutionEngine):
    def __init__(self, ledger, position_manager, event_bus, client=None):
        super().__init__(ledger, position_manager, event_bus)
        self.client = client or BinanceFuturesTestnetClient()
        self.source = "binance_futures_testnet"

    def market_order(
        self,
        fleet,
        side,
        price,
        margin,
        leverage=1.0,
        reason="strategy signal",
        symbol_override=None,
        capital_pool="fleet",
    ):
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if price <= 0 or margin <= 0:
            raise ValueError("price and margin must be positive")

        leverage = max(1.0, float(leverage))
        symbol = str(symbol_override or self.client.resolve_symbol(fleet)).upper()
        desired_quantity = (margin * leverage) / price
        quantity = self.client.normalize_quantity(symbol, desired_quantity)
        if quantity <= 0:
            raise ValueError(f"{symbol} normalized quantity is zero")

        self.client.set_margin_type_isolated(symbol)
        self.client.set_leverage(symbol, leverage)
        external_id = f"nexus_{fleet.lower()}_{uuid4().hex[:20]}"
        external_order = self.client.place_market_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            client_order_id=external_id,
        )
        fill_price = self.client.extract_fill_price(external_order, fallback_price=price)
        executed_quantity = float(external_order.get("executedQty") or quantity)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._freeze_margin(fleet, margin, "binance testnet market order margin", capital_pool=capital_pool)

        order = {
            "id": f"ord_{uuid4().hex[:10]}",
            "time": now,
            "fleet": fleet,
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "price": round(fill_price, 10),
            "margin": round(margin, 6),
            "leverage": leverage,
            "quantity": round(executed_quantity, 10),
            "status": str(external_order.get("status", "FILLED")),
            "reason": reason,
            "execution_source": self.source,
            "external_order_id": external_order.get("orderId"),
            "external_client_order_id": external_order.get("clientOrderId", external_id),
            "capital_pool": capital_pool,
        }
        position = {
            "id": f"pos_{uuid4().hex[:10]}",
            "opened_at": now,
            "fleet": fleet,
            "symbol": symbol,
            "side": side,
            "entry_price": fill_price,
            "mark_price": fill_price,
            "quantity": executed_quantity,
            "margin": margin,
            "leverage": leverage,
            "unrealized_pnl": 0.0,
            "reason": reason,
            "execution_source": self.source,
            "external_order_id": external_order.get("orderId"),
            "market_type": "futures",
            "capital_pool": capital_pool,
            "r_exit_state": build_r_exit_state(margin, executed_quantity),
        }
        self.orders.insert(0, order)
        self.trades.insert(0, {**order, "event": "OPEN"})
        self.position_manager.open_position(position)
        self.event_bus.publish("trade_opened", {"order": order, "position": position})
        return order, position

    def close_position(self, position_id, price, reason="strategy exit"):
        position = self.position_manager.positions.get(position_id)
        if not position:
            return None

        close_side = "SELL" if position["side"] == "BUY" else "BUY"
        symbol = position["symbol"]
        quantity = self.client.normalize_quantity(symbol, position["quantity"])
        external_id = f"nexus_close_{position['fleet'].lower()}_{uuid4().hex[:16]}"
        external_order = self.client.place_market_order(
            symbol=symbol,
            side=close_side,
            quantity=quantity,
            reduce_only=True,
            client_order_id=external_id,
        )

        closed = self.position_manager.close_position(position_id)
        if not closed:
            return None

        fill_price = self.client.extract_fill_price(external_order, fallback_price=price)
        side_factor = 1 if closed["side"] == "BUY" else -1
        pnl = (fill_price - closed["entry_price"]) * closed["quantity"] * side_factor
        self._release_margin(closed, closed["margin"], pnl, reason)

        trade = {
            "id": f"cls_{uuid4().hex[:10]}",
            "position_id": position_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": "CLOSE",
            "fleet": closed["fleet"],
            "symbol": closed["symbol"],
            "side": closed["side"],
            "entry_price": round(closed["entry_price"], 10),
            "exit_price": round(fill_price, 10),
            "quantity": round(closed["quantity"], 10),
            "margin": round(closed["margin"], 6),
            "leverage": round(float(closed.get("leverage", 1.0) or 1.0), 4),
            "pnl": round(pnl, 6),
            "reason": reason,
            "execution_source": self.source,
            "external_order_id": external_order.get("orderId"),
            "external_client_order_id": external_order.get("clientOrderId", external_id),
            "market_type": "futures",
        }
        self.trades.insert(0, trade)
        self.event_bus.publish("trade_closed", {"trade": trade, "position": closed})
        return trade

    def reduce_position(self, position_id, close_fraction, price, reason="r_exit_partial"):
        position = self.position_manager.get_position(position_id)
        if not position:
            return None
        state = position.get("r_exit_state") or {}
        initial_qty = float(state.get("initial_quantity", position.get("quantity", 0.0)) or 0.0)
        close_qty = min(float(position.get("quantity", 0.0) or 0.0), initial_qty * float(close_fraction or 0.0))
        close_qty = self.client.normalize_quantity(position["symbol"], close_qty)
        if close_qty <= 0:
            return None

        close_side = "SELL" if position["side"] == "BUY" else "BUY"
        external_id = f"nexus_partial_{position['fleet'].lower()}_{uuid4().hex[:16]}"
        external_order = self.client.place_market_order(
            symbol=position["symbol"],
            side=close_side,
            quantity=close_qty,
            reduce_only=True,
            client_order_id=external_id,
        )
        fill_price = self.client.extract_fill_price(external_order, fallback_price=price)
        executed_qty = float(external_order.get("executedQty") or close_qty)
        result = self.position_manager.reduce_position(position_id, executed_qty, mark_price=fill_price)
        if not result:
            return None
        remaining, released_margin, _ = result
        side_factor = 1 if position["side"] == "BUY" else -1
        pnl = (fill_price - position["entry_price"]) * executed_qty * side_factor
        self._release_margin(position, released_margin, pnl, reason)
        trade = {
            "id": f"prt_{uuid4().hex[:10]}",
            "position_id": position_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": "PARTIAL",
            "fleet": position["fleet"],
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": round(position["entry_price"], 10),
            "exit_price": round(fill_price, 10),
            "quantity": round(executed_qty, 10),
            "margin": round(released_margin, 6),
            "pnl": round(pnl, 6),
            "reason": reason,
            "exit_class": "take_profit",
            "execution_source": self.source,
            "external_order_id": external_order.get("orderId"),
            "market_type": "futures",
            "remaining_quantity": round(float(remaining.get("quantity", 0.0) if remaining else 0.0), 10),
        }
        self.trades.insert(0, trade)
        self.event_bus.publish("trade_partial", {"trade": trade, "position": remaining or position})
        return trade

    @classmethod
    def from_env(cls, ledger, position_manager, event_bus):
        client = BinanceFuturesTestnetClient()
        if not client.is_configured():
            raise ValueError("Binance futures testnet credentials are not configured")
        if os.getenv("BINANCE_TESTNET_VALIDATE_ON_BOOT", "0").strip() in {"1", "true", "TRUE"}:
            client.validate_credentials()
        return cls(ledger, position_manager, event_bus, client=client)
