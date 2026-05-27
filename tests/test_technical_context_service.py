import unittest

from backend.governance.ai_exit_planner import AiExitPlanner
from backend.market.technical_context_service import TechnicalContextService


def _make_kline(open_px, high, low, close, volume):
    return [0, str(open_px), str(high), str(low), str(close), str(volume), 0, 0, 0, 0, 0, 0]


class _FakeFuturesClient:
    def __init__(self, klines_by_interval=None):
        self.klines_by_interval = klines_by_interval or {}

    def is_configured(self):
        return True

    def get_klines(self, symbol, interval="5m", limit=100):
        return list(self.klines_by_interval.get(interval) or [])


def _rising_klines(count=40, start=100.0, step=0.4, volume=1000.0):
    rows = []
    price = start
    for idx in range(count):
        open_px = price
        close = price + step
        rows.append(_make_kline(open_px, close + 0.2, open_px - 0.1, close, volume + idx))
        price = close
    return rows


def _falling_klines(count=40, start=120.0, step=0.5, volume=1200.0):
    rows = []
    price = start
    for idx in range(count):
        open_px = price
        close = price - step
        rows.append(_make_kline(open_px, open_px + 0.1, close - 0.2, close, volume + idx * 2))
        price = close
    return rows


class TechnicalContextServiceTests(unittest.TestCase):
    def test_analyze_builds_rsi_ema_and_volume_fields(self):
        client = _FakeFuturesClient(
            {
                "5m": _rising_klines(),
                "15m": _rising_klines(start=95.0),
            }
        )
        service = TechnicalContextService(client)
        payload = service.analyze("BTCUSDT")
        flat = payload.get("flat") or {}
        self.assertTrue(flat.get("technical_ready"))
        self.assertIn("rsi_14", flat)
        self.assertIn("ema_20", flat)
        self.assertIn("atr_14", flat)
        self.assertEqual(flat.get("trend_bias"), "bullish")
        self.assertIn("5m", payload.get("intervals") or {})
        self.assertIn("15m", payload.get("intervals") or {})

    def test_technical_exit_score_rises_for_long_in_bearish_regime(self):
        client = _FakeFuturesClient(
            {
                "5m": _falling_klines(volume=2500.0),
                "15m": _falling_klines(start=130.0, volume=2200.0),
            }
        )
        service = TechnicalContextService(client)
        payload = service.analyze("ETHUSDT", position_side="LONG")
        flat = payload.get("flat") or {}
        self.assertGreaterEqual(float(flat.get("technical_exit_score") or 0.0), 0.55)
        self.assertEqual(flat.get("trend_bias"), "bearish")


class AiExitPlannerAdvisoryTests(unittest.TestCase):
    def test_exit_planner_includes_tp_advisory_when_technical_fields_present(self):
        planner = AiExitPlanner()
        payload = planner.plan_for_position(
            {
                "symbol": "ETHUSDT",
                "fleet": "ETH",
                "side": "BUY",
                "entry_price": 100.0,
                "mark_price": 105.0,
                "quantity": 1.0,
                "margin": 50.0,
                "unrealized_pnl": 5.0,
                "r_exit_state": {"risk_r_usd": 5.0},
            },
            market_context={
                "atr_14": 1.2,
                "trend_bias": "bearish",
                "technical_exit_score": 0.72,
                "regime_change": True,
            },
        )
        self.assertIsNotNone(payload)
        self.assertIn("tp_advisory", payload)
        advisory = payload.get("tp_advisory") or {}
        self.assertIn("suggested_tp_levels", advisory)
        self.assertTrue(len(advisory.get("suggested_tp_levels") or []) >= 2)


if __name__ == "__main__":
    unittest.main()
