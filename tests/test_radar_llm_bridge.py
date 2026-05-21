import unittest

from backend.governance.radar_llm_proposal_bridge import RadarLlmProposalBridge
from backend.trading.radar_dispatch_service import RadarDispatchService
from config.radar_dispatch_config import CORE_FLEET_SYMBOLS


class RadarLlmBridgeTests(unittest.TestCase):
    def test_parse_excludes_core_fleets(self):
        bridge = RadarLlmProposalBridge(RadarDispatchService(), llm_gateway=None)
        scan = {"market_board": [{"symbol": "XRPUSDT", "candidate_score": 60}]}
        llm = {
            "output": {
                "radar_orders": [
                    {"symbol": "BTCUSDT", "side": "BUY", "confidence": 0.9, "rationale": "x"},
                    {"symbol": "XRPUSDT", "side": "BUY", "confidence": 0.7, "rationale": "ok"},
                ]
            }
        }
        proposals = bridge.parse_llm_output(llm, scan)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["symbol"], "XRPUSDT")
        self.assertNotIn(proposals[0]["symbol"], CORE_FLEET_SYMBOLS)


if __name__ == "__main__":
    unittest.main()
