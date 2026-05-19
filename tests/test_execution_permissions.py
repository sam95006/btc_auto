import unittest

from backend.trading.binance_execution_router import BinanceExecutionRouter, ExecutionPermissionError


class _FakeSpotEngine:
    def __init__(self):
        self.calls = []

    def market_order(self, *args, **kwargs):
        self.calls.append(("spot_market_order", args, kwargs))
        return {"id": "spot-order"}, {"id": "spot-position"}


class _FakeFuturesClient:
    def __init__(self):
        self.calls = []

    def resolve_symbol(self, fleet):
        return f"{fleet}USDT"

    def get_symbol_leverage_bracket(self, symbol, estimated_notional=0.0):
        return {"symbol": symbol, "initialLeverage": 75}

    def set_margin_type_isolated(self, symbol):
        self.calls.append(("set_margin_type_isolated", symbol))
        return {"symbol": symbol}

    def set_leverage(self, symbol, leverage):
        self.calls.append(("set_leverage", symbol, leverage))
        return {"symbol": symbol, "leverage": leverage}


class _FakeFuturesEngine:
    def __init__(self):
        self.client = _FakeFuturesClient()
        self.calls = []

    def market_order(self, **kwargs):
        self.calls.append(("futures_market_order", kwargs))
        return {"id": "futures-order"}, {"id": "futures-position"}


class _FakeDynamicLeverageEngine:
    def calculate_proposed_leverage(self, confidence_score):
        return {
            "allowed": True,
            "confidence_score": confidence_score,
            "proposed_leverage": 20,
            "reason": "confidence_band_match",
        }


class _FakeIdempotencyGuard:
    def claim(self, *args, **kwargs):
        return True, "test-fingerprint"


class _FakeRiskEngine:
    def __init__(self):
        self.dynamic_leverage_engine = _FakeDynamicLeverageEngine()
        self.calculate_calls = 0

    def calculate_final_leverage(self, **kwargs):
        self.calculate_calls += 1
        return {
            "confidence_score": kwargs["confidence_score"],
            "proposed_leverage": 20,
            "symbol_max_leverage": 75,
            "risk_cap_leverage": 20,
            "final_leverage": 20,
            "reason": "fleet_risk_cap",
        }


class ExecutionPermissionTests(unittest.TestCase):
    def setUp(self):
        self.spot = _FakeSpotEngine()
        self.futures = _FakeFuturesEngine()
        self.risk = _FakeRiskEngine()
        self.router = BinanceExecutionRouter(
            spot_engine=self.spot,
            futures_engine=self.futures,
            risk_engine=self.risk,
            dynamic_leverage_engine=self.risk.dynamic_leverage_engine,
            trading_mode="binance_testnet",
            idempotency_guard=_FakeIdempotencyGuard(),
        )

    def test_hq_cannot_trade_futures(self):
        with self.assertRaises(ExecutionPermissionError):
            self.router.route_futures_order(
                fleet="HQ",
                side="BUY",
                price=100.0,
                margin=20.0,
                reason="test",
                confidence_score=0.8,
                market_regime="normal",
            )

    def test_fleet_cannot_trade_spot(self):
        with self.assertRaises(ExecutionPermissionError):
            self.router.route_spot_order(
                fleet="BTC",
                side="BUY",
                price=100.0,
                margin=20.0,
                reason="test",
            )

    def test_news_cannot_trade(self):
        with self.assertRaises(ExecutionPermissionError):
            self.router.route_futures_order(
                fleet="NEWS",
                side="BUY",
                price=100.0,
                margin=20.0,
                reason="test",
                confidence_score=0.8,
                market_regime="normal",
            )

    def test_ui_actor_cannot_trade_directly(self):
        with self.assertRaises(ExecutionPermissionError):
            self.router.route_futures_order(
                fleet="BTC",
                side="BUY",
                price=100.0,
                margin=20.0,
                reason="test",
                confidence_score=0.8,
                market_regime="normal",
                actor="ui",
            )


if __name__ == "__main__":
    unittest.main()
