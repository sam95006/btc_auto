import os
import unittest
from unittest.mock import patch

from backend.monitoring.maturity_radar_service import MaturityRadarService


class _RadarStore:
    def recent_trade_validation_events(self, limit=200):
        return [{"approved": True, "fleet": "RADAR"}] * min(limit, 20)

    def recent_decision_audit(self, limit=200):
        return []

    def recent_trade_results(self, limit=120):
        return []


class MaturityRadarTests(unittest.TestCase):
    @patch.dict(os.environ, {"NEXUS_DATA_DIR": "/data"}, clear=False)
    def test_five_dimensions_present(self):
        service = MaturityRadarService()
        report = service.build_report(
            {
                "system": {"trading_paused": False},
                "growth_mode": {
                    "block_new_entries": False,
                    "compound_reinvest": True,
                    "daily_positive_mode": True,
                    "daily_max_loss_guard": True,
                    "futures_equity": 3500,
                    "daily": {"is_positive_day": True, "compound_reinvest": True},
                    "compound": {"enabled": True, "reinvest_base_equity": 3400},
                },
                "compound_capital": {
                    "enabled": True,
                    "reinvest_base_equity": 3400,
                    "deployable_pool": 1750,
                    "live_futures_equity": 3500,
                },
                "truth_layer_status": {"futures_ready_for_ai": True},
                "llm_status": {"enabled": True, "providers_ready": True},
                "capital": {"source": "binance_rest", "futures_margin_balance": 3500},
                "ops_health": {"slo_score": 92, "status": "healthy"},
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
                    "decision_traces": [{"trace_id": "t1"}, {"trace_id": "t2"}, {"trace_id": "t3"}],
                    "learning_reviews": {"auto_apply": True, "patch_outcomes": []},
                },
                "position_ai": {"reviewed_at": "2026-05-25 12:00:00", "actions": []},
                "strategy_evolution": {"evolution_mode": "hold", "walk_forward_ready": True},
                "meeting_execution_directives": {"blocked_fleets": []},
                "agent_advisory": {"multi_agent": {}, "radar_llm_proposals": {"count": 1}},
                "decision_audit": [
                    {"approved": True, "decision_source": "llm_proposer"},
                    {"approved": False, "reject_reason": "test"},
                ],
            },
            embedded_worker_started=True,
            runtime_store=_RadarStore(),
        )
        self.assertEqual(len(report["dimensions"]), 5)
        for key in MaturityRadarService.DIMENSIONS:
            self.assertIn(key, report["dimensions"])
            self.assertGreaterEqual(report["dimensions"][key], 65.0)


if __name__ == "__main__":
    unittest.main()
