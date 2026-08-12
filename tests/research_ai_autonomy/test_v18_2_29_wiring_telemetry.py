from __future__ import annotations

from backend.nexus_research_ai_autonomy.adaptive_profit_capture import (
    summarize_adaptive_capture_from_lifecycle,
)
from backend.nexus_research_ai_autonomy.stop_loss_audit_v29 import audit_stop_loss_quality


def test_adaptive_not_activated_when_mfe_zero_fields_always_present():
    lifecycle = {
        "symbol": "BLUAIUSDT",
        "side": "LONG",
        "exit_reason": "STOP_LOSS",
        "path_excursion": {"mfe_usdt": 0.0, "mae_usdt": -1.09},
        "exact_pnl_accounting": {"total_fees": 0.77, "calculated_net_pnl": -0.48},
        "stop_distance_pct": 0.4,
        "notional_usdt": 350.0,
    }
    out = summarize_adaptive_capture_from_lifecycle(lifecycle)
    assert out["evaluated"] is True
    assert out["adaptive_action"] == "NOT_ACTIVATED"
    assert out["profit_lock_level"] is None
    assert out["protected_pnl_floor"] is None
    assert out["profit_lock_started_at"] is None
    assert out["reason"] == "NO_MEANINGFUL_POSITIVE_MFE"
    # Keys must exist even when null — distinguish "not triggered" from "not executed".
    for k in (
        "evaluated",
        "adaptive_action",
        "profit_lock_level",
        "protected_pnl_floor",
        "profit_lock_started_at",
        "remaining_edge",
        "continuation_score",
        "giveback_risk",
        "mfe_usdt",
        "reason",
    ):
        assert k in out


def test_stop_quality_block_always_has_required_keys():
    lifecycle = {
        "symbol": "BLUAIUSDT",
        "side": "LONG",
        "stop_distance_pct": 0.4,
        "notional_usdt": 350.0,
        "prepared_decision_horizon": {"atr_pct": 2.5},
        "exact_pnl_accounting": {"total_fees": 0.766},
        "expected_net_target_usdt": 1.54,
        "path_excursion": {"mae_usdt": -1.23},
    }
    out = audit_stop_loss_quality(lifecycle)
    for k in (
        "stop_quality",
        "stop_distance_pct",
        "noise_band",
        "fee_to_target_ratio",
        "fee_to_stop_ratio",
        "not_available_reason",
    ):
        assert k in out
    assert out["stop_quality"] == "EVALUATED"
    assert out["noise_band"] is None
    assert "noise_band" in out["not_available_reason"]
    assert out["fee_to_stop_ratio"] == 0.766 / 1.4
    assert out["fee_to_target_ratio"] == 0.766 / 1.54


def test_empty_lifecycle_still_emits_stop_and_adaptive_shapes():
    stop = audit_stop_loss_quality(None)
    adaptive = summarize_adaptive_capture_from_lifecycle(None)
    assert stop["stop_quality"] == "NOT_EVALUATED"
    assert "not_available_reason" in stop
    assert adaptive["evaluated"] is False
    assert adaptive["adaptive_action"] is None
    assert adaptive["reason"] == "no_completed_lifecycle"
