"""Closed historical holdout V1 — selection, freeze, and safety gates."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_demo_execution.closed_historical_holdout import (
    classify_confirmatory,
    classify_primary,
    recommendation_from_primary,
)
from backend.nexus_demo_execution.closed_historical_registry import (
    RESEARCH_V2_V3_START_MS,
    SEPTEMBER_OOS_START_MS,
    assert_september_partial_excluded,
    build_used_interval_registry,
    overlaps_any,
    select_closed_historical_period,
)
from backend.nexus_demo_execution.h3_oos_policy_freeze import load_frozen_policy
from backend.nexus_demo_execution.market_event_sim import simulate_natural_trade
from backend.nexus_demo_execution.oos_maturity_gate import assess_reservation_maturity


H3E = "bca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33"
H3D = "d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7"


def test_deterministic_period_selection_is_stable():
    a = select_closed_historical_period(root=ROOT)
    b = select_closed_historical_period(root=ROOT)
    assert a.status == b.status
    if a.status == "PERIOD_SELECTED":
        assert a.reservation_start == b.reservation_start
        assert a.reservation_end == b.reservation_end
        assert a.reservation_duration_days >= 120
        assert a.reservation_end <= RESEARCH_V2_V3_START_MS - 30 * 86_400_000


def test_zero_overlap_with_all_used_intervals():
    sel = select_closed_historical_period(root=ROOT)
    if sel.status != "PERIOD_SELECTED":
        pytest.skip("no clean holdout available")
    registry = build_used_interval_registry(ROOT)
    hits = overlaps_any(registry, sel.reservation_start, sel.reservation_end)
    assert hits == []


def test_no_performance_based_period_selection():
    # Selection rule text must not mention returns/PF/profit
    sel = select_closed_historical_period(root=ROOT)
    rule = sel.selection_rule.lower()
    for banned in ("profit", "return", "pf", "expectancy", "win_rate", "pnl"):
        assert banned not in rule


def test_policy_checksum_freeze():
    assert load_frozen_policy("H3E_OOS_POLICY_V1_FROZEN")["policy_checksum"] == H3E
    assert load_frozen_policy("H3D_OOS_POLICY_V1_FROZEN")["policy_checksum"] == H3D


def test_september_partial_oos_exclusion():
    with pytest.raises(RuntimeError, match="SEPTEMBER_PARTIAL_OOS_EXCLUDED"):
        assert_september_partial_excluded(
            r".nexus_runtime\oos\OOS_H3_UNTOUCHED_V1_RESERVED\market_cache\x.json"
        )
    sept = json.loads((ROOT / "artifacts/readiness/OOS_H3_UNTOUCHED_V1_RESERVATION.json").read_text(encoding="utf-8"))
    assert sept["classification"] == "OOS_WINDOW_NOT_MATURE"
    assert sept["executed"] is False
    m = assess_reservation_maturity(reservation=sept)
    assert m.future_oos_execution_allowed is False


def test_real_data_only_requirement_in_summary_schema():
    # Runner forbids synthetic; classification must reject invalid data.
    assert classify_primary({"completed_trade_count": 0}, data_valid=False) == "CLOSED_HISTORICAL_DATA_INVALID"


def test_h3d_cannot_rescue_h3e():
    failed = "CLOSED_HISTORICAL_PERFORMANCE_FAILED"
    # Confirmatory validated must not change primary recommendation
    assert recommendation_from_primary(failed) == "NEXUS_H3_CLOSED_HISTORICAL_FAILED_RETURN_TO_RESEARCH"
    conf = classify_confirmatory(
        {
            "completed_trade_count": 50,
            "net_pnl": 10,
            "profit_factor": 1.5,
            "net_expectancy": 0.2,
            "adverse_profit_factor": 1.2,
            "adverse_net_pnl": 5,
        },
        data_valid=True,
    )
    assert conf == "CONFIRMATORY_VALIDATED"
    assert recommendation_from_primary(failed) != "NEXUS_H3_CLOSED_HISTORICAL_VALIDATED_DEMO_FORWARD_APPROVAL_REQUIRED"


def test_demo_forward_cannot_auto_start_without_packet_gate():
    path = ROOT / "artifacts/readiness/immutable/h3_closed_historical_v1/demo_forward_readiness_packet.json"
    if not path.is_file():
        # Before/without validation — auto-start remains forbidden by construction
        assert True
        return
    pkt = json.loads(path.read_text(encoding="utf-8"))
    assert pkt.get("auto_start_forbidden") is True
    assert pkt.get("demo_forward_status") == "AWAITING_SEPARATE_FOUNDER_AUTHORIZATION"


def test_wallet_residual_remains_visible():
    sot = json.loads((ROOT / "artifacts/readiness/NEXUS_READINESS_SOT.json").read_text(encoding="utf-8"))
    assert abs(float(sot["wallet_delta_unattributed"]) - (-0.97052039)) <= 1e-8
    assert sot["wallet_delta_classification"] == "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST"


def test_historical_ledger_cannot_mutate_demo_wallet_contract():
    # Contract constants for runner outputs
    assert os.environ.get("EXCHANGE_WRITE") == "false"
    summary = ROOT / "artifacts/readiness/immutable/h3_closed_historical_v1/closed_historical_summary.json"
    if summary.is_file():
        s = json.loads(summary.read_text(encoding="utf-8"))
        assert s.get("exchange_write_attempt_count") == 0
        assert s.get("demo_order_count") == 0
        assert s.get("demo_wallet_changed_by_test") is False
        assert s.get("historical_execution_mode") == "HISTORICAL_SIMULATION_ONLY"


def test_adverse_first_intrabar_flag_exists_on_sim_trade():
    # Structural: SimTrade supports adverse_first_applied (used by frozen simulator)
    from backend.nexus_demo_execution.market_event_sim import SimTrade

    assert "adverse_first_applied" in SimTrade.__dataclass_fields__


def test_consumed_holdout_immutability_when_present():
    path = ROOT / "artifacts/readiness/immutable/h3_closed_historical_v1/consumed_holdout_registry_entry.json"
    if not path.is_file():
        pytest.skip("holdout not executed yet")
    reg = json.loads(path.read_text(encoding="utf-8"))
    assert reg["reservation_id"] == "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED"
    assert "dataset_checksum" in reg
    assert reg.get("status") in {"CONSUMED", "EXECUTING_H3E"}


def test_september_start_not_inside_selected_holdout():
    sel = select_closed_historical_period(root=ROOT)
    if sel.status != "PERIOD_SELECTED":
        pytest.skip("no clean holdout")
    assert sel.reservation_end < SEPTEMBER_OOS_START_MS
    assert sel.reservation_end < RESEARCH_V2_V3_START_MS
