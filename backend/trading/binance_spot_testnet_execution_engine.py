import os
from datetime import datetime
from uuid import uuid4

from backend.fleets.paper_order_execution_engine import PaperOrderExecutionEngine
from backend.trading.binance_spot_testnet_client import BinanceSpotTestnetClient


class BinanceSpotTestnetExecutionEngine(PaperOrderExecutionEngine):
    def __init__(self, ledger, position_manager, event_bus, client=None):
        super().__init__(ledger, position_manager, event_bus)
        self.client = client or BinanceSpotTestnetClient()
        self.source = "binance_spot_testnet"

    def market_order(self, fleet, side, price, margin, leverage=1.0, reason="strategy signal", symbol_override=None):
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if price <= 0 or margin <= 0:
            raise ValueError("price and margin must be positive")
        if side == "SELL":
            raise ValueError(f"{fleet} spot testnet does not support opening short positions")

        symbol = str(symbol_override or self.client.resolve_symbol(fleet)).strip().upper()
        external_id = f"nexus_spot_{fleet.lower()}_{uuid4().hex[:20]}"
        external_order = self.client.place_market_buy(
            symbol=symbol,
            quote_order_qty=margin,
            client_order_id=external_id,
        )

        fill_price = self.client.extract_fill_price(external_order, fallback_price=price)
        executed_quantity = float(external_order.get("executedQty") or (margin / price))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.ledger.freeze(fleet, margin, "binance spot testnet market buy quote amount")

        order = {
            "id": f"ord_{uuid4().hex[:10]}",
            "time": now,
            "fleet": fleet,
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "price": round(fill_price, 10),
            "margin": round(margin, 6),
            "leverage": 1.0,
            "quantity": round(executed_quantity, 10),
            "status": str(external_order.get("status", "FILLED")),
            "reason": reason,
            "execution_source": self.source,
            "external_order_id": external_order.get("orderId"),
            "external_client_order_id": external_order.get("clientOrderId", external_id),
        }
        position = {
            "id": f"pos_{uuid4().hex[:10]}",
            "opened_at": now,
            "fleet": fleet,
            "symbol": symbol,
            "side": "BUY",
            "entry_price": fill_price,
            "mark_price": fill_price,
            "quantity": executed_quantity,
            "margin": margin,
            "leverage": 1.0,
            "unrealized_pnl": 0.0,
            "reason": reason,
            "execution_source": self.source,
            "external_order_id": external_order.get("orderId"),
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
        if position["side"] != "BUY":
            raise ValueError(f"{position['fleet']} spot testnet only supports closing long positions")

        symbol = position["symbol"]
        quantity = self.client.normalize_quantity(symbol, position["quantity"])
        external_id = f"nexus_spot_close_{position['fleet'].lower()}_{uuid4().hex[:16]}"
        external_order = self.client.place_market_sell(
            symbol=symbol,
            quantity=quantity,
            client_order_id=external_id,
        )

        closed = self.position_manager.close_position(position_id)
        if not closed:
            return None

        fill_price = self.client.extract_fill_price(external_order, fallback_price=price)
        pnl = (fill_price - closed["entry_price"]) * closed["quantity"]
        self.ledger.release(closed["fleet"], closed["margin"], pnl, reason)

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
            "leverage": 1.0,
            "pnl": round(pnl, 6),
            "reason": reason,
            "execution_source": self.source,
            "external_order_id": external_order.get("orderId"),
            "external_client_order_id": external_order.get("clientOrderId", external_id),
            "market_type": "spot",
        }
        self.trades.insert(0, trade)
        self.event_bus.publish("trade_closed", {"trade": trade, "position": closed})
        return trade

    @classmethod
    def from_env(cls, ledger, position_manager, event_bus):
        client = BinanceSpotTestnetClient()
        if not client.is_configured():
            raise ValueError("Binance spot testnet credentials are not configured")
        if os.getenv("BINANCE_TESTNET_VALIDATE_ON_BOOT", "0").strip() in {"1", "true", "TRUE"}:
            client.validate_credentials()
        return cls(ledger, position_manager, event_bus, client=client)
