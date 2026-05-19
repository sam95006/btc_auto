import unittest
from unittest.mock import Mock

from backend.trading.binance_execution_router import BinanceExecutionRouter, ExecutionPermissionError


class _FakeSpotEngine:
    def market_order(self, *args, **kwargs):
        return {"id": "spot-order"}, {"id": "spot-position"}


class _FakeFuturesClient:
    def __init__(self):
        self.call_order = []

    def resolve_symbol(self, fleet):
        return f"{fleet}USDT"

    def get_symbol_leverage_bracket(self, symbol, estimated_notional=0.0):
        return {"symbol": symbol, "initialLeverage": 75}

    def set_margin_type_isolated(self, symbol):
        self.call_order.append(("set_margin_type_isolated", symbol))

    def set_leverage(self, symbol, leverage):
        self.call_order.append(("set_leverage", symbol, leverage))


class _FakeFuturesEngine:
    def __init__(self):
        self.client = _FakeFuturesClient()
        self.call_order = self.client.call_order

    def market_order(self, **kwargs):
        self.call_order.append(("market_order", kwargs))
        return {"id": "futures-order"}, {"id": "futures-position"}


class _FakeDynamicLeverageEngine:
    def calculate_proposed_leverage(self, confidence_score):
        return {
            "allowed": True,
            "confidence_score": confidence_score,
            "proposed_leverage": 50,
            "reason": "confidence_band_match",
        }


class _FakeIdempotencyGuard:
    def __init__(self):
        self.seen = set()

    def claim(self, fleet, symbol, side, strategy_signal_hash, **kwargs):
        key = (fleet, symbol, side, strategy_signal_hash)
        if key in self.seen:
            return False, "duplicate"
        self.seen.add(key)
        return True, "ok"


class ExecutionRouterLeverageTests(unittest.TestCase):
    def setUp(self):
        self.futures_engine = _FakeFuturesEngine()
        self.risk_engine = Mock()
        self.risk_engine.calculate_final_leverage.return_value = {
            "confidence_score": 0.88,
            "proposed_leverage": 50,
            "symbol_max_leverage": 75,
            "risk_cap_leverage": 20,
            "final_leverage": 20,
            "reason": "fleet_risk_cap",
        }
        self.router = BinanceExecutionRouter(
            spot_engine=_FakeSpotEngine(),
            futures_engine=self.futures_engine,
            risk_engine=self.risk_engine,
            dynamic_leverage_engine=_FakeDynamicLeverageEngine(),
            trading_mode="binance_testnet",
            idempotency_guard=_FakeIdempotencyGuard(),
        )

    def test_futures_order_sets_leverage_before_order(self):
        self.router.route_futures_order(
            fleet="BTC",
            side="BUY",
            price=100.0,
            margin=20.0,
            reason="test",
            confidence_score=0.88,
            market_regime="normal",
        )
        self.assertEqual(self.futures_engine.call_order[0][0], "set_margin_type_isolated")
        self.assertEqual(self.futures_engine.call_order[1][0], "set_leverage")
        self.assertEqual(self.futures_engine.call_order[2][0], "market_order")

    def test_news_cannot_place_futures_order(self):
        with self.assertRaises(ExecutionPermissionError):
            self.router.route_futures_order(
                fleet="NEWS",
                side="BUY",
                price=100.0,
                margin=20.0,
                reason="test",
                confidence_score=0.88,
                market_regime="normal",
            )

    def test_hq_cannot_use_futures_leverage(self):
        with self.assertRaises(ExecutionPermissionError):
            self.router.route_futures_order(
                fleet="HQ",
                side="BUY",
                price=100.0,
                margin=20.0,
                reason="test",
                confidence_score=0.88,
                market_regime="normal",
            )

    def test_risk_engine_is_required_in_route(self):
        self.router.route_futures_order(
            fleet="BTC",
            side="BUY",
            price=100.0,
            margin=20.0,
            reason="test",
            confidence_score=0.88,
            market_regime="normal",
        )
        self.assertEqual(self.risk_engine.calculate_final_leverage.call_count, 1)

    def test_duplicate_order_is_blocked(self):
        self.router.route_futures_order(
            fleet="BTC",
            side="BUY",
            price=100.0,
            margin=20.0,
            reason="test",
            confidence_score=0.88,
            market_regime="normal",
        )
        with self.assertRaises(ExecutionPermissionError):
            self.router.route_futures_order(
                fleet="BTC",
                side="BUY",
                price=100.0,
                margin=20.0,
                reason="test",
                confidence_score=0.88,
                market_regime="normal",
            )


if __name__ == "__main__":
    unittest.main()
