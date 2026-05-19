import unittest

from backend.agents.advisory_services import AdvisoryServices


class AgentAdvisoryServicesTests(unittest.TestCase):
    def setUp(self):
        self.service = AdvisoryServices()

    def test_builds_news_understanding(self):
        payload = self.service.build_news_understanding(
            normalized_events=[
                {"bucket": "crypto", "impact": "HIGH", "quality_score": 0.8, "major": True, "targets": ["BTC"], "sentiment": "NEGATIVE"},
                {"bucket": "macro", "impact": "LOW", "quality_score": 0.6, "major": False, "targets": ["ALL"], "sentiment": "NEUTRAL"},
            ],
            truth_layer_status={"fresh_for_ai": True, "degraded_market_contexts": []},
            market_context={"BTC": {"market_regime": "normal"}},
        )
        self.assertEqual(payload["event_count"], 2)
        self.assertEqual(payload["major_event_count"], 1)
        self.assertTrue(payload["truth_ready"])

    def test_builds_multi_agent_proposals(self):
        payload = self.service.build_multi_agent_proposals(
            normalized_events=[
                {"targets": ["BTC"], "sentiment": "NEGATIVE"},
                {"targets": ["BTC"], "sentiment": "NEGATIVE"},
                {"targets": ["ETH"], "sentiment": "POSITIVE"},
            ],
            market_context={"BTC": {"market_regime": "wide_spread"}, "ETH": {"market_regime": "normal"}},
            truth_layer_status={"futures_ready_for_ai": True},
        )
        self.assertIn("world_channel", payload)
        self.assertEqual(len(payload["world_channel"]), 2)
        btc_row = next(item for item in payload["world_channel"] if item["agent"] == "BTC")
        self.assertEqual(btc_row["priority"], "high")

    def test_builds_station_learning_exchange(self):
        payload = self.service.build_station_learning_exchange(
            meetings=[{"meeting_id": "m1", "time": "2026-05-18 12:00:00"}],
            normalized_events=[{"impact": "HIGH", "quality_score": 0.9, "title": "event"}],
            market_context={"BTC": {"symbol": "BTCUSDT", "market_regime": "normal", "funding_risk": "normal", "slippage_risk": "normal", "liquidation_risk": "none"}},
            learning_status={"calibration_snapshot": {"fleet_adjustments": {"BTC": {"failure_focus": ["over_leverage"], "confidence_penalty": 0.1, "leverage_cap": 10}}}},
            radar_scan={"candidates": [{"symbol": "BTCUSDT", "candidate_side": "LONG", "candidate_score": 78.0, "reason": "healthy_structure"}], "whale_watch": []},
            portfolio_status={"reserve_action": "hold", "notional_utilization": 0.4, "same_side_concentration": 0.5},
        )
        self.assertIn("station_shares", payload)
        self.assertIn("cross_station_lessons", payload)
        self.assertIn("opportunity_board", payload)

    def test_station_learning_exchange_includes_hedge_governance_when_needed(self):
        payload = self.service.build_station_learning_exchange(
            meetings=[],
            normalized_events=[],
            market_context={},
            learning_status={"calibration_snapshot": {"fleet_adjustments": {}}},
            radar_scan={"candidates": [], "whale_watch": []},
            portfolio_status={
                "reserve_action": "increase_reserve",
                "notional_utilization": 1.1,
                "same_side_concentration": 0.9,
                "hedge_recommendations": [{"reason": "portfolio_concentration_or_utilization_high"}],
            },
        )
        lesson_types = {item["lesson_type"] for item in payload["cross_station_lessons"]}
        self.assertIn("hedge_governance", lesson_types)


if __name__ == "__main__":
    unittest.main()
