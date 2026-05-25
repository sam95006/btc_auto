from __future__ import annotations

from datetime import datetime


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value):
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


class LiquidationTracker:
    """Detect exchange-side position closes (liquidations) and feed the learning loop."""

    def __init__(self):
        self._last_positions = {}
        self._processed_trade_ids = set()
        self._processed_close_keys = set()
        self._watched_symbols = set()

    def watched_symbols(self):
        return set(self._watched_symbols)

    def _watch_symbol(self, symbol):
        symbol = str(symbol or "").upper()
        if symbol:
            self._watched_symbols.add(symbol)

    def reconcile(self, live_positions, live_trades, futures_client, record_trade_result):
        self._ingest_live_trades(live_trades, record_trade_result)
        self._ingest_income_events(futures_client, record_trade_result)
        self._ingest_position_closures(live_positions, record_trade_result)

    def _ingest_live_trades(self, live_trades, record_trade_result):
        for trade in list(live_trades or []):
            trade_id = str(trade.get("id") or "")
            pnl = _safe_float(trade.get("pnl"))
            if not trade_id or trade_id in self._processed_trade_ids:
                continue
            if pnl >= -0.01:
                continue
            self._processed_trade_ids.add(trade_id)
            self._record_exchange_loss(trade, pnl, record_trade_result, exit_reason="exchange_realized_loss")

    def _ingest_income_events(self, futures_client, record_trade_result):
        if not futures_client or not getattr(futures_client, "is_configured", lambda: False)():
            return
        get_income = getattr(futures_client, "get_income_history", None)
        if not callable(get_income):
            return
        try:
            rows = get_income(income_type="INSURANCE_CLEAR", limit=30) or []
        except Exception:
            rows = []
        for row in rows:
            event_id = str(row.get("tranId") or row.get("id") or "")
            if not event_id or event_id in self._processed_trade_ids:
                continue
            amount = _safe_float(row.get("income"))
            if amount >= -0.01:
                continue
            self._processed_trade_ids.add(event_id)
            symbol = str(row.get("symbol") or "").upper()
            trade_time = row.get("time")
            timestamp = _now()
            if trade_time:
                try:
                    timestamp = datetime.fromtimestamp(int(trade_time) / 1000).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    timestamp = _now()
            self._record_exchange_loss(
                {
                    "id": f"income_{event_id}",
                    "symbol": symbol,
                    "fleet": "RADAR",
                    "side": "SELL",
                    "time": timestamp,
                },
                amount,
                record_trade_result,
                exit_reason="exchange_liquidation",
            )

    def _ingest_position_closures(self, live_positions, record_trade_result):
        current = {}
        for position in list(live_positions or []):
            symbol = str(position.get("symbol") or "").upper()
            qty = abs(_safe_float(position.get("quantity") or position.get("signed_quantity")))
            if symbol and qty > 1e-12:
                current[symbol] = position
                self._watch_symbol(symbol)

        for symbol, previous in self._last_positions.items():
            if symbol in current:
                continue
            close_key = f"closed:{symbol}"
            if close_key in self._processed_close_keys:
                continue
            pnl = _safe_float(previous.get("unrealized_pnl"))
            if pnl >= 0:
                margin = _safe_float(previous.get("margin"))
                pnl = -max(0.5, margin * 0.15) if margin > 0 else -1.0
            self._record_exchange_loss(
                {
                    "id": close_key,
                    "symbol": symbol,
                    "fleet": str(previous.get("fleet") or "RADAR").upper(),
                    "side": str(previous.get("side") or "HOLD").upper(),
                    "entry_price": previous.get("entry_price"),
                    "time": _now(),
                    "final_leverage": previous.get("leverage"),
                },
                pnl,
                record_trade_result,
                exit_reason="exchange_liquidation",
            )

        self._last_positions = current

    def _record_exchange_loss(self, trade, pnl, record_trade_result, exit_reason):
        symbol = str(trade.get("symbol") or "").upper()
        if not symbol:
            return
        self._watch_symbol(symbol)
        close_key = f"closed:{symbol}"
        if close_key in self._processed_close_keys and str(trade.get("id") or "").startswith("closed:"):
            return
        self._processed_close_keys.add(close_key)
        fleet = str(trade.get("fleet") or "RADAR").upper()
        record_trade_result(
            {
                "order_id": trade.get("id"),
                "symbol": symbol,
                "market_type": "futures",
                "fleet": fleet,
                "entry_price": trade.get("entry_price"),
                "exit_price": trade.get("price"),
                "pnl": round(pnl, 4),
                "exit_reason": exit_reason,
                "failure_reason": "exchange_liquidation",
                "strategy_key": "radar_market_scan_strategy" if fleet == "RADAR" else f"{fleet.lower()}_adaptive_strategy",
                "market_regime": "radar_alt" if fleet == "RADAR" else "normal",
                "side": trade.get("side"),
                "final_leverage": trade.get("final_leverage") or trade.get("leverage"),
                "timestamp": trade.get("time") or _now(),
            },
            context={
                "setup_type": "radar_dispatch" if fleet == "RADAR" else "fleet_engine",
                "market_regime": "radar_alt" if fleet == "RADAR" else "normal",
                "liquidation_risk": "critical",
            },
        )
