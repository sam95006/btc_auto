"""OOS maturity gate + partial-cache research ban + approval reuse ban."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_demo_execution.h3_oos_policy_freeze import load_frozen_policy, load_oos_reservation
from backend.nexus_demo_execution.oos_maturity_gate import (
    STATUS_NOT_MATURE,
    assess_reservation_maturity,
    assert_not_using_partial_oos_in_research,
)


H3E = "bca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33"
H3D = "d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7"


def _reservation() -> dict:
    return json.loads((ROOT / "artifacts/readiness/OOS_H3_UNTOUCHED_V1_RESERVATION.json").read_text(encoding="utf-8"))


def test_future_reservation_blocks_before_network_download():
    r = _reservation()
    # Force "now" before reserved_end
    m = assess_reservation_maturity(reservation=r, now_ms=int(r["reserved_end"]) - 1)
    assert m.status == STATUS_NOT_MATURE
    assert m.reservation_window_closed is False
    assert m.future_oos_execution_allowed is False
    assert m.prior_founder_approval_reuse_allowed is False


def test_open_reservation_returns_window_not_mature():
    r = _reservation()
    m = assess_reservation_maturity(reservation=r)
    assert m.status == STATUS_NOT_MATURE
    assert m.reason == "RESERVED_END_IS_IN_THE_FUTURE"


def test_closed_reservation_still_requires_completed_max_timeframe_candle():
    r = _reservation()
    end = int(r["reserved_end"])
    # Immediately after reserved_end ms, 240m candle containing end may still be open.
    m = assess_reservation_maturity(reservation=r, now_ms=end + 1)
    assert m.reservation_window_closed is True
    # Depending on alignment, max TF may still be open; execution must not be allowed until closed+lag+coverage.
    if not m.maximum_timeframe_closed:
        assert m.future_oos_execution_allowed is False
        assert m.status == STATUS_NOT_MATURE


def test_incomplete_symbol_coverage_blocks_execution():
    r = _reservation()
    end = int(r["reserved_end"])
    # Far past end + lag, but incomplete coverage
    now = end + 7 * 24 * 3600 * 1000
    coverage = {f"{s}_{iv}": 0.5 for s in r["symbols"] for iv in r["intervals"]}
    m = assess_reservation_maturity(
        reservation=r,
        now_ms=now,
        coverage_ratio_by_symbol_timeframe=coverage,
        missing_interval_count=10,
        actual_record_count=100,
    )
    assert m.reservation_window_closed is True
    assert m.all_symbol_timeframe_coverage_complete is False
    assert m.future_oos_execution_allowed is False


def test_no_consumed_registry_before_execution():
    reg = json.loads(
        (ROOT / "artifacts/readiness/immutable/h3_oos_v1/consumed_oos_registry_entry.json").read_text(encoding="utf-8")
    )
    assert reg["status"] == "NOT_CONSUMED"
    assert reg["classification"] == "NOT_CONSUMED_EXECUTION_NOT_STARTED"
    assert reg.get("execution_started") in (False, None)


def test_partial_cache_cannot_enter_research_pipeline():
    with pytest.raises(RuntimeError, match="PRELIMINARY_PARTIAL_NOT_FOR_ANALYSIS"):
        assert_not_using_partial_oos_in_research(
            r"G:\我的雲端硬碟\btc_bot\.nexus_runtime\oos\OOS_H3_UNTOUCHED_V1_RESERVED\market_cache\x.json"
        )


def test_no_automatic_reuse_of_prior_founder_approval():
    r = load_oos_reservation()
    assert r.get("prior_founder_approval_exhausted") is True
    assert r.get("next_execution_requires_new_founder_phrase") is True
    m = assess_reservation_maturity(reservation=r)
    assert m.prior_founder_approval_reuse_allowed is False


def test_semantic_correction_not_performance_failure():
    corr = json.loads(
        (ROOT / "artifacts/readiness/immutable/h3_oos_v1/semantic_correction_window_not_mature.json").read_text(
            encoding="utf-8"
        )
    )
    assert corr["corrected_status"] == "OOS_WINDOW_NOT_MATURE"
    assert corr["stop_class"] == "PREMATURE_DATA_GATE_STOP"
    assert "OOS_PERFORMANCE_FAILED" in corr["not_equivalent_to"]
    assert corr["partial_data_used_for_tuning"] is False
    assert corr["partial_data_used_for_performance_analysis"] is False


def test_policies_still_frozen():
    assert load_frozen_policy("H3E_OOS_POLICY_V1_FROZEN")["policy_checksum"] == H3E
    assert load_frozen_policy("H3D_OOS_POLICY_V1_FROZEN")["policy_checksum"] == H3D


def test_wallet_reconciliation_preserves_unknown_residuals():
    path = ROOT / "artifacts/readiness/immutable/wallet_delta_forensic/wallet_delta_forensic_report.json"
    assert path.is_file()
    rep = json.loads(path.read_text(encoding="utf-8"))
    assert abs(float(rep["remaining_unattributed_delta"]) - (-0.97052039)) <= 1e-8
    assert abs(float(rep["remaining_unattributed_delta"])) > float(rep["reconciliation_tolerance"])
    assert rep["wallet_delta_classification"] in {
        "WALLET_DELTA_FULLY_ATTRIBUTED",
        "WALLET_DELTA_PARTIALLY_ATTRIBUTED",
        "WALLET_DELTA_UNATTRIBUTED_API_HISTORY_INCOMPLETE",
        "WALLET_DELTA_UNATTRIBUTED_ACCOUNT_EPOCH_MISMATCH",
        "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST",
    }
    assert rep["trading_db_status"] == "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED"
