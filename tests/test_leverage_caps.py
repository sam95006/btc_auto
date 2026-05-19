import unittest

from backend.risk.risk_control_engine import RiskControlEngine


class _FakeLedger:
    pass


class _FakePnlTracker:
    def __init__(self, fleet_total=0.0, recent=None):
        self.fleet_total = fleet_total
        self._recent = recent or []

    def snapshot(self):
        return {
            "fleets": {
                "BTC": {"total": self.fleet_total},
                "ETH": {"total": self.fleet_total},
                "SOL": {"total": self.fleet_total},
                "PEPE": {"total": self.fleet_total},
            }
        }

    def recent_trades(self, limit=50):
        return list(self._recent)[:limit]


class LeverageCapTests(unittest.TestCase):
    def test_binance_symbol_cap_applies(self):
        engine = RiskControlEngine(_FakeLedger(), _FakePnlTracker())
        result = engine.calculate_final_leverage(
            symbol="BTCUSDT",
            fleet="BTC",
            confidence_score=0.95,
            market_regime="normal",
            risk_context={"symbol_max_leverage": 75},
        )
        self.assertEqual(result["final_leverage"], 75)

    def test_system_max_100_applies(self):
        engine = RiskControlEngine(_FakeLedger(), _FakePnlTracker())
        result = engine.calculate_final_leverage(
            symbol="BTCUSDT",
            fleet="BTC",
            confidence_score=0.95,
            market_regime="normal",
            risk_context={"symbol_max_leverage": 125},
        )
        self.assertEqual(result["final_leverage"], 100)

    def test_confidence_band_cap_applies(self):
        engine = RiskControlEngine(_FakeLedger(), _FakePnlTracker())
        result = engine.calculate_final_leverage(
            symbol="SOLUSDT",
            fleet="SOL",
            confidence_score=0.88,
            market_regime="normal",
            risk_context={"symbol_max_leverage": 100},
        )
        self.assertEqual(result["final_leverage"], 50)

    def test_pepe_default_cap_applies(self):
        engine = RiskControlEngine(_FakeLedger(), _FakePnlTracker())
        result = engine.calculate_final_leverage(
            symbol="1000PEPEUSDT",
            fleet="PEPE",
            confidence_score=0.95,
            market_regime="normal",
            risk_context={"symbol_max_leverage": 100},
        )
        self.assertEqual(result["final_leverage"], 20)

    def test_alert_red_caps_to_3x(self):
        engine = RiskControlEngine(_FakeLedger(), _FakePnlTracker())
        result = engine.calculate_final_leverage(
            symbol="BTCUSDT",
            fleet="BTC",
            confidence_score=0.95,
            market_regime="alert_red",
            risk_context={"symbol_max_leverage": 100},
        )
        self.assertEqual(result["final_leverage"], 3)


if __name__ == "__main__":
    unittest.main()
