from __future__ import annotations

from backend.nexus_research_ai_autonomy.entry_quality_v29 import audit_entry_quality_v29
from backend.nexus_research_ai_autonomy.stop_loss_audit_v29 import audit_stop_loss_quality


def test_stop_loss_audit_computes_fee_to_stop_ratio_and_estimated_loss_if_stop_net():
    lifecycle = {
        "symbol": "BLUAIUSDT",
        "side": "LONG",
        "stop_distance_pct": 0.4,
        "notional_usdt": 350.0,
        "prepared_decision_horizon": {"atr_pct": 2.5},
        "exact_pnl_accounting": {"total_fees": 0.766},
        "path_excursion": {"mae_usdt": -1.23, "mae_pct": -0.35},
    }
    out = audit_stop_loss_quality(lifecycle)
    assert out["stop_distance_pct"] == 0.4
    assert out["stop_distance_usdt"] == 1.4
    assert out["fee_to_stop_loss_ratio"] == 0.766 / 1.4
    assert out["estimated_loss_if_stop_net"] < 0
    assert out["expected_adverse_excursion"] == -1.23


def test_entry_quality_ambiguity_direction_bucket():
    lifecycle = {
        "process_evidence": {
            "entry_rule_compliance": "PASS",
            "exit_rule_compliance": "PASS",
            "risk_gate_results": {"status": "PASS"},
            "cost_gate_results": {"status": "PASS"},
            "data_quality_results": {"status": "PASS"},
        },
        "exact_pnl_accounting": {"total_fees": 0.766},
        "expected_net_target_usdt": 1.54,
        "stop_distance_pct": 0.4,
    }
    out = audit_entry_quality_v29(lifecycle=lifecycle, direction_ambiguity_supported=True)
    assert out["last_entry_class"] == "AMBIGUOUS_DIRECTION"
    assert out["spread"] is None
    assert out["slippage"] is None
    assert out["noise_band"] is None

