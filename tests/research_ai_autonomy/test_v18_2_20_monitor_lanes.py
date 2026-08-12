# -*- coding: utf-8 -*-
"""V18.2.20 — founder monitor separates REAL BYBIT vs LOCAL_SIM vs SHADOW."""
from backend.nexus_research_ai_autonomy.autonomy_runtime import ResearchAutonomyRuntime
from backend.nexus_research_ai_autonomy.fast_path import (
    ProvenanceRecordingTransport,
    SimulatedDemoTransport,
)


def test_monitor_lanes_local_simulation_default():
    rt = ResearchAutonomyRuntime()
    snap = rt.monitor_snapshot()
    lanes = snap["execution_lanes"]
    assert lanes["labels_separated"] is True
    assert set(lanes.keys()) >= {"REAL_BYBIT", "LOCAL_SIMULATION", "SHADOW", "active_lane", "labels_separated"}
    assert lanes["active_lane"] in {"REAL_BYBIT", "LOCAL_SIMULATION", "SHADOW"}


def test_monitor_lanes_after_sim_order():
    rt = ResearchAutonomyRuntime()
    wrap = ProvenanceRecordingTransport(inner=SimulatedDemoTransport())
    rt.fast_path.transport = wrap
    wrap.send_research_order({"symbol": "ETHUSDT", "side": "Buy", "qty": 0.01})
    snap = rt.monitor_snapshot()
    assert snap["execution_lanes"]["active_lane"] == "LOCAL_SIMULATION"
    assert snap["execution_lanes"]["LOCAL_SIMULATION"] is True
    assert snap["execution_lanes"]["REAL_BYBIT"] is False
    assert snap["latency"]["lane"] == "LOCAL_SIMULATION"


def test_generalization_audit_no_oos_reuse():
    from backend.nexus_strategy_engine.generalization_audit import (
        audit_dev_wf_stability,
        freeze_new_ca4_oos_hash,
        preregister_ca4_mechanisms,
    )

    prior = {
        "NEW_ALPHA_CA3": {
            "eval_rows": [
                {
                    "candidate_id": "V18_CA3_H01_HORIZON_COST",
                    "strategy_family": "TREND",
                    "metrics": {
                        "trade_count": 397,
                        "net_expectancy": 0.4,
                        "gross_expectancy": 0.9,
                        "cost_to_gross_edge_ratio": 0.4,
                        "development_status": "DISCOVERY_PROMISING",
                        "break_even_cost_multiplier": 1.7,
                    },
                },
                {
                    "candidate_id": "V18_CA3_H01_SPREAD_FLOOR",
                    "strategy_family": "TREND",
                    "metrics": {
                        "trade_count": 115,
                        "net_expectancy": -0.9,
                        "gross_expectancy": -0.4,
                        "cost_to_gross_edge_ratio": 0.97,
                        "development_status": "DISCOVERY_NO_GROSS_EDGE",
                    },
                },
            ],
            "best_candidate": {
                "candidate_id": "V18_CA3_H01_HORIZON_COST",
                "break_even_cost_multiplier": 1.7,
                "net_under_cost_multipliers": {
                    "net_at_1.0x": 0.4,
                    "net_at_2.0x": -0.17,
                },
            },
            "formal_WF": {
                "candidate_id": "V18_CA3_H01_HORIZON_COST",
                "evaluation": {
                    "metrics": {
                        "largest_regime_profit_contribution": 0.54,
                        "turnover_events_per_trade": 2.07,
                        "development_fold_count": 5,
                        "positive_development_fold_count": 4,
                        "net_under_cost_multipliers": {
                            "net_at_1.0x": 0.4,
                            "net_at_2.0x": -0.17,
                        },
                    }
                },
            },
            "OOS": {
                "untouched_oos_hash": "c6453764e6d7632a6b743b65a08f9f56375b2bc1895e367b07c057bed4ab8f4a",
                "metrics": {
                    "trade_count": 0,
                    "zero_trade_root_cause": "IMPLEMENTATION_ERROR",
                    "candidate_funnel": {"bars_scanned": 0},
                },
            },
            "sealed_splits": {
                "prior_consumed_oos_hash": "fc5ccac1591164e88eeee310867b009a33940654c7262d13745d358df018dfae",
                "untouched_oos_hash": "c6453764e6d7632a6b743b65a08f9f56375b2bc1895e367b07c057bed4ab8f4a",
            },
        }
    }
    audit = audit_dev_wf_stability(prior)
    assert audit["audit_complete"] is True
    assert audit["oos_peek_for_optimization"] is False
    assert "PIPELINE_IMPLEMENTATION" in audit["primary_root_causes"]
    assert "COST_MARGIN_TOO_THIN" in audit["primary_root_causes"]

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        prereg = preregister_ca4_mechanisms(audit, out_path=Path(td) / "prereg.json", max_n=4)
        assert prereg["variant_count"] <= 4
        assert prereg["blind_ca4_evaluation_executed"] is False
        assert all(v["candidate_id"].startswith("V18_CA4_") for v in prereg["variants"])
        oos = freeze_new_ca4_oos_hash(
            prior_ca2_hash="fc5ccac1591164e88eeee310867b009a33940654c7262d13745d358df018dfae",
            prior_ca3_hash="c6453764e6d7632a6b743b65a08f9f56375b2bc1895e367b07c057bed4ab8f4a",
            data_end_ms=1785663000000,
            out_path=Path(td) / "oos.json",
        )
        assert oos["oos_reuse"] is False
        assert oos["oos_executed"] is False
        assert oos["untouched_oos_hash"] not in {
            "fc5ccac1591164e88eeee310867b009a33940654c7262d13745d358df018dfae",
            "c6453764e6d7632a6b743b65a08f9f56375b2bc1895e367b07c057bed4ab8f4a",
        }
