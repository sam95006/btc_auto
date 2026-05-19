import unittest

from backend.trading.r_exit_engine import RExitEngine, build_r_exit_state


class RExitEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = RExitEngine()

    def _position(self, unrealized, tp1=False, tp2=False, stop_at_be=False):
        return {
            "side": "BUY",
            "entry_price": 100.0,
            "quantity": 1.0,
            "margin": 100.0,
            "unrealized_pnl": unrealized,
            "r_exit_state": {
                **build_r_exit_state(100.0, 1.0),
                "tp1_done": tp1,
                "tp2_done": tp2,
                "stop_at_be": stop_at_be,
            },
        }

    def test_stop_loss_at_minus_1r(self):
        action = self.engine.evaluate(self._position(-10.5), 100.0)
        self.assertIsNotNone(action)
        self.assertEqual(action["type"], "full")
        self.assertEqual(action["exit_class"], "stop_loss")

    def test_tp1_partial_at_plus_1r(self):
        action = self.engine.evaluate(self._position(10.5), 110.0)
        self.assertEqual(action["type"], "partial")
        self.assertEqual(action["tp_tag"], "TP1")
        self.assertAlmostEqual(action["fraction"], 0.30)

    def test_tp3_full_at_plus_3r(self):
        action = self.engine.evaluate(self._position(31.0, tp1=True, tp2=True), 130.0)
        self.assertEqual(action["type"], "full")
        self.assertEqual(action["reason"], "r_exit_tp3")

    def test_break_even_after_tp1(self):
        action = self.engine.evaluate(self._position(-0.5, tp1=True, stop_at_be=True), 99.5)
        self.assertEqual(action["exit_class"], "break_even")


class RadarDispatchServiceTests(unittest.TestCase):
    def test_eligible_candidates_skip_core_symbols(self):
        from backend.trading.radar_dispatch_service import RadarDispatchService

        service = RadarDispatchService()
        radar_scan = {
            "candidates": [
                {"symbol": "BTCUSDT", "candidate_score": 80, "reason": "healthy_structure", "candidate_side": "LONG"},
                {"symbol": "DOGEUSDT", "candidate_score": 70, "reason": "healthy_structure", "candidate_side": "SHORT"},
            ]
        }
        eligible = service.eligible_candidates(radar_scan)
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]["symbol"], "DOGEUSDT")


if __name__ == "__main__":
    unittest.main()
