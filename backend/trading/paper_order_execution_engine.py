import os

from backend.fleets.paper_order_execution_engine import PaperOrderExecutionEngine as LocalPaperOrderExecutionEngine
from backend.trading.binance_spot_testnet_execution_engine import BinanceSpotTestnetExecutionEngine
from backend.trading.binance_testnet_execution_engine import BinanceTestnetExecutionEngine


class MixedTestnetExecutionEngine:
    def __init__(self, ledger, position_manager, event_bus):
        self.paper = LocalPaperOrderExecutionEngine(ledger, position_manager, event_bus)
        self.spot = BinanceSpotTestnetExecutionEngine.from_env(ledger, position_manager, event_bus)
        self.futures = BinanceTestnetExecutionEngine.from_env(ledger, position_manager, event_bus)
        self.ledger = ledger
        self.position_manager = position_manager
        self.event_bus = event_bus

    @property
    def orders(self):
        return self.paper.orders

    @orders.setter
    def orders(self, value):
        self.paper.orders = value
        self.spot.orders = self.paper.orders
        self.futures.orders = self.paper.orders

    @property
    def trades(self):
        return self.paper.trades

    @trades.setter
    def trades(self, value):
        self.paper.trades = value
        self.spot.trades = self.paper.trades
        self.futures.trades = self.paper.trades

    def _engine_for_fleet(self, fleet):
        market_type = os.getenv(f"NEXUS_MARKET_TYPE_{fleet.upper()}", "futures").strip().lower()
        if market_type == "spot":
            return self.spot
        if market_type == "futures":
            return self.futures
        return self.paper

    def market_order(self, fleet, side, price, margin, leverage=1.0, reason="strategy signal"):
        return self._engine_for_fleet(fleet).market_order(fleet, side, price, margin, leverage, reason)

    def close_position(self, position_id, price, reason="strategy exit"):
        position = self.position_manager.positions.get(position_id)
        if not position:
            return None
        return self._engine_for_fleet(position["fleet"]).close_position(position_id, price, reason)

    def reduce_position(self, position_id, close_fraction, price, reason="r_exit_partial"):
        position = self.position_manager.positions.get(position_id)
        if not position:
            return None
        engine = self._engine_for_fleet(position["fleet"])
        if not hasattr(engine, "reduce_position"):
            return None
        return engine.reduce_position(position_id, close_fraction, price, reason=reason)

    def recent_orders(self, limit=80):
        return self.paper.recent_orders(limit)

    def recent_trades(self, limit=80):
        return self.paper.recent_trades(limit)


class PaperOrderExecutionEngine:
    def __new__(cls, ledger, position_manager, event_bus):
        trading_mode = os.getenv("NEXUS_TRADING_MODE", "").strip().lower()
        if trading_mode == "live":
            raise RuntimeError("NEXUS_TRADING_MODE=live is forbidden")

        execution_mode = os.getenv("NEXUS_EXECUTION_MODE", "").strip().lower()
        if trading_mode == "binance_testnet" and not execution_mode:
            mode = "binance_mixed_testnet"
        elif trading_mode == "paper" and not execution_mode:
            mode = "paper"
        else:
            mode = execution_mode or "paper"
        if mode == "binance_mixed_testnet":
            try:
                return MixedTestnetExecutionEngine(ledger, position_manager, event_bus)
            except Exception as exc:
                print(f"[execution_factory] Binance mixed testnet disabled: {exc}")
        if mode == "binance_spot_testnet":
            try:
                return BinanceSpotTestnetExecutionEngine.from_env(ledger, position_manager, event_bus)
            except Exception as exc:
                print(f"[execution_factory] Binance spot testnet disabled: {exc}")
        if mode in {"binance_testnet", "binance_futures_testnet"}:
            try:
                return BinanceTestnetExecutionEngine.from_env(ledger, position_manager, event_bus)
            except Exception as exc:
                print(f"[execution_factory] Binance futures testnet disabled: {exc}")
        return LocalPaperOrderExecutionEngine(ledger, position_manager, event_bus)


__all__ = ["PaperOrderExecutionEngine"]
