import unittest

from backend.fleets.paper_order_execution_engine import PaperOrderExecutionEngine
from backend.trading.r_exit_engine import ensure_r_exit_state
from backend.wallet.internal_capital_ledger import InternalCapitalLedger


class _NoopBus:
    def publish(self, *_args, **_kwargs):
        return None


class _PmStub:
    positions = {}

    def get_position(self, position_id):
        return self.positions.get(position_id)

    def reduce_position(self, position_id, close_qty, mark_price=0.0):
        position = self.positions.get(position_id)
        if not position:
            return None
        executed = min(float(position.get("quantity", 0.0) or 0.0), float(close_qty or 0.0))
        released_margin = float(position.get("margin", 0.0) or 0.0) * (executed / float(position.get("quantity", 1.0) or 1.0))
        position["quantity"] = float(position.get("quantity", 0.0) or 0.0) - executed
        position["margin"] = max(0.0, float(position.get("margin", 0.0) or 0.0) - released_margin)
        return position, released_margin, executed


class RadarLedgerReleaseTests(unittest.TestCase):
    def test_release_radar_position_without_key_error(self):
        ledger = InternalCapitalLedger()
        ledger.radar_budget = 500.0
        engine = PaperOrderExecutionEngine(ledger, _PmStub(), _NoopBus())
        position = {
            "fleet": "RADAR",
            "symbol": "XRPUSDT",
            "side": "SELL",
            "margin": 80.0,
            "quantity": 100.0,
            "entry_price": 1.0,
        }
        engine._release_margin(position, 20.0, 5.0, "partial test")
        self.assertGreater(ledger.radar_budget, 500.0)

    def test_r_exit_state_rebuilds_when_margin_was_zero(self):
        position = {
            "margin": 79.52,
            "quantity": 2887.2,
            "r_exit_state": {
                "initial_margin": 0.0,
                "initial_quantity": 2887.2,
                "risk_r_usd": 1e-6,
                "tp1_done": False,
            },
        }
        updated = ensure_r_exit_state(position)
        self.assertGreater(updated["r_exit_state"]["risk_r_usd"], 1.0)


if __name__ == "__main__":
    unittest.main()
