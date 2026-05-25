import unittest

from backend.monitoring.maturity_radar_service import MaturityRadarService


class MaturityRadarTests(unittest.TestCase):
    def test_five_dimensions_present(self):
        service = MaturityRadarService()
        report = service.build_report(
            {
                "system": {"trading_paused": False},
                "growth_mode": {"block_new_entries": False},
                "truth_layer_status": {"futures_ready_for_ai": True},
                "llm_status": {"enabled": True, "providers_ready": True},
                "capital": {"source": "binance_rest"},
                "live_sync": {"updated_at_ms": 9999999999999, "news_count": 3},
                "decision_summary": {"futures_enabled": True, "always_on_trading": True, "trade_count": 2},
                "learning_status": {
                    "trade_journal_count": 2,
                    "calibration_snapshot": {
                        "fleet_adjustments": {
                            "RADAR": {
                                "symbol_cooldown": {"DOGEUSDT": {"active": True}},
                            }
                        }
                    },
                    "learning_reviews": {
                        "auto_apply": True,
                        "counts": {"applied": 1},
                        "patch_outcomes": [],
                        "applied_patches": [],
                    },
                },
                "upgrade_pipeline": {
                    "trade_proposals": [],
                    "decision_traces": [{"trace_id": "t1"}],
                    "learning_reviews": {"auto_apply": True, "patch_outcomes": []},
                },
                "meeting_execution_directives": {"blocked_fleets": []},
                "agent_advisory": {"multi_agent": {}, "radar_llm_proposals": {"count": 1}},
                "decision_audit": [
                    {"approved": True, "decision_source": "llm_proposer"},
                    {"approved": False, "reject_reason": "test"},
                ],
            },
            embedded_worker_started=True,
        )
        self.assertEqual(len(report["dimensions"]), 5)
        for key in MaturityRadarService.DIMENSIONS:
            self.assertIn(key, report["dimensions"])
            self.assertGreaterEqual(report["dimensions"][key], 65.0)


if __name__ == "__main__":
    unittest.main()
