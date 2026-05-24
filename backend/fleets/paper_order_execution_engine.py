from datetime import datetime
from uuid import uuid4

from backend.trading.r_exit_engine import build_r_exit_state


class PaperOrderExecutionEngine:
    """Paper execution only. No exchange API is called here."""

    def __init__(self, ledger, position_manager, event_bus):
        self.ledger = ledger
        self.position_manager = position_manager
        self.event_bus = event_bus
        self.orders = []
        self.trades = []

    def _is_radar_pool(self, fleet, capital_pool=None):
        pool = str(capital_pool or "").strip().lower()
        return pool == "radar" or str(fleet or "").upper() == "RADAR"

    def _freeze_margin(self, fleet, margin, note, capital_pool="fleet"):
        if self._is_radar_pool(fleet, capital_pool):
            self.ledger.freeze_radar(margin, note)
        else:
            self.ledger.freeze(fleet, margin, note)

    def _release_margin(self, position, margin, pnl, note):
        if self._is_radar_pool(position.get("fleet"), position.get("capital_pool")):
            self.ledger.release_radar(margin, pnl, note)
        else:
            self.ledger.release(position["fleet"], margin, pnl, note)

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
        self._freeze_margin(fleet, margin, "paper market order margin", capital_pool=capital_pool)
        notional = margin * leverage
        quantity = notional / price
        raw_symbol = str(symbol_override or f"{fleet}USDT").upper()
        if "/" in raw_symbol:
            raw_symbol = raw_symbol.replace("/", "")
        if not raw_symbol.endswith("USDT"):
            raw_symbol = f"{raw_symbol}USDT"
        display_symbol = raw_symbol.replace("USDT", "/USDT")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order = {
            "id": f"ord_{uuid4().hex[:10]}",
            "time": now,
            "fleet": fleet,
            "symbol": display_symbol,
            "side": side,
            "type": "MARKET",
            "price": round(price, 10),
            "margin": round(margin, 6),
            "leverage": leverage,
            "quantity": round(quantity, 10),
            "status": "FILLED",
            "reason": reason,
            "capital_pool": capital_pool,
        }
        position = {
            "id": f"pos_{uuid4().hex[:10]}",
            "opened_at": now,
            "fleet": fleet,
            "symbol": display_symbol,
            "side": side,
            "entry_price": price,
            "mark_price": price,
            "quantity": quantity,
            "margin": margin,
            "leverage": leverage,
            "unrealized_pnl": 0.0,
            "reason": reason,
            "market_type": "futures",
            "capital_pool": capital_pool,
            "r_exit_state": build_r_exit_state(margin, quantity),
        }
        self.orders.insert(0, order)
        self.trades.insert(0, {**order, "event": "OPEN"})
        self.position_manager.open_position(position)
        self.event_bus.publish("trade_opened", {"order": order, "position": position})
        return order, position

    def close_position(self, position_id, price, reason="strategy exit"):
        position = self.position_manager.close_position(position_id)
        if not position:
            return None
        side_factor = 1 if position["side"] == "BUY" else -1
        pnl = (price - position["entry_price"]) * position["quantity"] * side_factor
        self._release_margin(position, position["margin"], pnl, reason)
        trade = {
            "id": f"cls_{uuid4().hex[:10]}",
            "position_id": position_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": "CLOSE",
            "fleet": position["fleet"],
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": round(position["entry_price"], 10),
            "exit_price": round(price, 10),
            "quantity": round(position["quantity"], 10),
            "margin": round(position["margin"], 6),
            "pnl": round(pnl, 6),
            "reason": reason,
        }
        self.trades.insert(0, trade)
        self.event_bus.publish("trade_closed", {"trade": trade, "position": position})
        return trade

    def reduce_position(self, position_id, close_fraction, price, reason="r_exit_partial"):
        position = self.position_manager.get_position(position_id)
        if not position:
            return None
        state = position.get("r_exit_state") or {}
        initial_qty = float(state.get("initial_quantity", position.get("quantity", 0.0)) or 0.0)
        close_qty = min(float(position.get("quantity", 0.0) or 0.0), initial_qty * float(close_fraction or 0.0))
        if close_qty <= 0:
            return None
        result = self.position_manager.reduce_position(position_id, close_qty, mark_price=price)
        if not result:
            return None
        remaining, released_margin, executed_qty = result
        side_factor = 1 if position["side"] == "BUY" else -1
        pnl = (price - position["entry_price"]) * executed_qty * side_factor
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
            "exit_price": round(price, 10),
            "quantity": round(executed_qty, 10),
            "margin": round(released_margin, 6),
            "pnl": round(pnl, 6),
            "reason": reason,
            "exit_class": "take_profit",
            "remaining_quantity": round(float(remaining.get("quantity", 0.0) if remaining else 0.0), 10),
        }
        self.trades.insert(0, trade)
        self.event_bus.publish("trade_partial", {"trade": trade, "position": remaining or position})
        return trade

    def recent_trades(self, limit=80):
        return list(self.trades[:limit])

    def recent_orders(self, limit=80):
        return list(self.orders[:limit])
