from threading import RLock

from backend.trading.r_exit_engine import ensure_r_exit_state


class PaperPositionManager:
    def __init__(self):
        self._lock = RLock()
        self.positions = {}

    def open_position(self, position):
        position = ensure_r_exit_state(dict(position))
        key = position["id"]
        with self._lock:
            self.positions[key] = position
        return position

    def close_position(self, position_id):
        with self._lock:
            return self.positions.pop(position_id, None)

    def get_position(self, position_id):
        with self._lock:
            pos = self.positions.get(position_id)
            return dict(pos) if pos else None

    def update_position(self, position_id, updates):
        with self._lock:
            pos = self.positions.get(position_id)
            if not pos:
                return None
            pos.update(updates or {})
            self.positions[position_id] = ensure_r_exit_state(pos)
            return dict(self.positions[position_id])

    def reduce_position(self, position_id, close_quantity, mark_price=None):
        with self._lock:
            pos = self.positions.get(position_id)
            if not pos:
                return None
            close_quantity = float(close_quantity or 0.0)
            current_qty = float(pos.get("quantity", 0.0) or 0.0)
            if close_quantity <= 0 or current_qty <= 0:
                return None
            close_quantity = min(close_quantity, current_qty)
            ratio = close_quantity / current_qty
            released_margin = float(pos.get("margin", 0.0) or 0.0) * ratio
            pos["quantity"] = round(current_qty - close_quantity, 10)
            pos["margin"] = round(float(pos.get("margin", 0.0) or 0.0) - released_margin, 6)
            if mark_price is not None:
                pos["mark_price"] = mark_price
            if pos["quantity"] <= 1e-12:
                return self.positions.pop(position_id, None)
            self.positions[position_id] = ensure_r_exit_state(pos)
            return dict(self.positions[position_id]), round(released_margin, 6), round(close_quantity, 10)

    def get_by_fleet(self, fleet):
        with self._lock:
            return [dict(pos) for pos in self.positions.values() if pos.get("fleet") == fleet]

    def get_by_symbol(self, symbol):
        symbol = str(symbol or "").upper()
        with self._lock:
            return [dict(pos) for pos in self.positions.values() if str(pos.get("symbol", "")).upper() == symbol]

    def all_positions(self):
        with self._lock:
            return [dict(pos) for pos in self.positions.values()]

    def update_unrealized(self, prices, symbol_prices=None):
        symbol_prices = symbol_prices or {}
        with self._lock:
            for pos in self.positions.values():
                fleet = pos.get("fleet")
                symbol = str(pos.get("symbol") or "").upper()
                price = None
                if fleet and fleet in prices:
                    price = prices.get(fleet, {}).get("price")
                if not price and symbol in symbol_prices:
                    price = symbol_prices.get(symbol)
                if not price:
                    continue
                side_factor = 1 if pos["side"] == "BUY" else -1
                pos["mark_price"] = price
                pos["unrealized_pnl"] = (price - pos["entry_price"]) * pos["quantity"] * side_factor
        return self.all_positions()
