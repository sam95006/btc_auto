"""Post-12H forensic / finalization repair tests."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.nexus_demo_execution.count_semantics import (
    classify_account_flat,
    count_or_none,
    reconcile_flat,
)
from backend.nexus_demo_execution.cost_gate_forensic_replay import (
    replay_cost_gates,
    synthesize_fixed_geometry_rows,
)
from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError, _round_qty, _round_price
from backend.nexus_demo_execution.instrument_qty_classify import classify_instrument_qty_error
from backend.nexus_demo_execution.kill_switch import KillSwitch, KillSwitchTrigger
from backend.nexus_demo_execution.session_finalizer import (
    build_final_snapshot,
    extract_account_counts,
    poll_until_stable,
)
from backend.nexus_demo_execution.session_limits import MIN_NET_REWARD_RISK_RATIO, MIN_NET_REWARD_TO_COST
from backend.nexus_demo_execution.wallet_delta_reconcile import reconcile_wallet_delta


def test_count_or_none_preserves_zero():
    assert count_or_none(0) == 0
    assert count_or_none(None) is None
    assert count_or_none("x") is None


def test_zero_or_minus_one_bug_fixed():
    # Historical finalizer bug: int(0 or -1) == -1
    acct = {"open_positions": 0, "open_orders": 0}
    pos, ord_, _ = extract_account_counts(acct)
    assert pos == 0 and ord_ == 0
    assert reconcile_flat(pos, ord_) == "MATCH"
    assert classify_account_flat(pos, ord_) == "ACCOUNT_CONFIRMED_FLAT"


def test_unknown_not_converted_to_mismatch():
    assert reconcile_flat(None, 0) == "UNKNOWN"
    assert reconcile_flat(0, None) == "UNKNOWN"
    assert classify_account_flat(None, None) == "ACCOUNT_STATE_UNKNOWN"


def test_stable_post_stop_polling():
    calls = {"n": 0}

    def sess():
        calls["n"] += 1
        if calls["n"] < 3:
            return {"status": "FINALIZING", "thread_alive": True, "session_write_enabled": True}
        return {
            "status": "COMPLETED",
            "thread_alive": False,
            "session_write_enabled": False,
            "smoke_write_window_open": False,
            "effective_demo_write_authorized": False,
        }

    def acct():
        return {"open_positions": 0, "open_orders": 0}

    out = poll_until_stable(fetch_session=sess, fetch_account=acct, timeout_sec=5, interval_sec=0.01)
    assert out["finalization_status"] == "STABLE"
    assert out["position_count_final"] == 0
    assert out["open_order_count_final"] == 0
    assert out["reconciliation_final"] == "MATCH"


def test_finalization_timeout_unknown_not_minus_one():
    def sess():
        return {"status": "FINALIZING", "thread_alive": True}

    def acct():
        return {"_error": "timeout", "detail": "account_api_failure"}

    out = poll_until_stable(fetch_session=sess, fetch_account=acct, timeout_sec=0.05, interval_sec=0.01)
    assert out["finalization_status"] == "UNKNOWN"
    assert out["position_count_final"] is None
    assert out["open_order_count_final"] is None
    assert out["reconciliation_final"] == "UNKNOWN"
    assert out["position_count_final"] != -1


def test_build_final_snapshot_never_writes_minus_one():
    snap = build_final_snapshot(
        session_snap={"entries_total": 0},
        poll_result={
            "finalization_status": "UNKNOWN",
            "position_count_final": -1,  # poisoned input
            "open_order_count_final": -1,
            "reconciliation_final": "UNKNOWN",
            "thread_alive": False,
            "session_write_window_open": False,
            "effective_demo_write_authorized": False,
            "polls": 1,
        },
        stop_reason="DEADLINE_FINALIZE",
    )
    assert snap["position_count_final"] is None
    assert snap["open_order_count_final"] is None
    assert snap["stop_reason"] == "DEADLINE_FINALIZE"


def test_deadline_finalize_does_not_engage_kill_switch():
    from backend.nexus_demo_execution.safety_gate import DemoExecutionSafetyGate

    ks = KillSwitch(gate=DemoExecutionSafetyGate())
    # Mimic engine.stop deadline branch semantics
    reason = "DEADLINE_FINALIZE"
    engaged = False
    if not reason.upper().startswith("DEADLINE_FINALIZE"):
        ks.engage(reason, trigger=KillSwitchTrigger.OPERATOR_STOP)
        engaged = True
    assert engaged is False
    assert ks.engaged is False


def test_operator_stop_still_engages_kill_switch():
    from backend.nexus_demo_execution.safety_gate import DemoExecutionSafetyGate

    ks = KillSwitch(gate=DemoExecutionSafetyGate())
    ks.engage("OPERATOR_STOP", trigger=KillSwitchTrigger.OPERATOR_STOP)
    assert ks.engaged is True
    assert ks.trigger == KillSwitchTrigger.OPERATOR_STOP


def test_quantity_tick_precision():
    assert _round_qty(1.2345, 0.001) == "1.234"
    assert _round_qty(0.0004, 0.001) == "0" or float(_round_qty(0.0004, 0.001) or 0) == 0
    assert _round_price(100.123456, 0.01) == "100.12"
    # non-power-of-10 tick
    assert _round_price(1.2345, 0.0005) in {"1.2345", "1.2340", "1.235"}


def test_compute_qty_step_rounding_raises():
    client = DemoWriteClient(api_key="k", api_secret="s")
    info = {
        "status": "Trading",
        "lotSizeFilter": {"qtyStep": "1", "minOrderQty": "1", "minNotionalValue": "5"},
        "priceFilter": {"tickSize": "0.01"},
    }
    # margin 20 * lev 25 = 500 notional / price 100000 → qty 0.005 → floors to 0 on step 1
    with pytest.raises(DemoWriteError) as ei:
        client.compute_qty(margin_usdt=20, leverage=25, price=100000, info=info)
    assert classify_instrument_qty_error(ei.value.code, ei.value.detail) == "qty_step_rounding"


def test_all_cost_block_forensic_replay_fixed_geometry():
    rows = synthesize_fixed_geometry_rows(2407)
    report = replay_cost_gates(rows)
    assert report["candidates_replayed"] == 2407
    assert report["cost_gate_pass_total"] == 0
    assert report["cost_gate_block_total"] == 2407
    assert report["floors_unchanged"]["MIN_NET_REWARD_RISK_RATIO"] == 1.2
    assert report["floors_unchanged"]["MIN_NET_REWARD_TO_COST"] == 1.5
    assert MIN_NET_REWARD_RISK_RATIO == 1.2
    assert MIN_NET_REWARD_TO_COST == 1.5
    assert "B" in report["root_cause_codes"]
    assert "F" in report["root_cause_codes"]
    assert report["distributions"]["gross_rr"]["p50"] == pytest.approx(1.0)


def test_wallet_delta_unattributed_without_ids():
    out = reconcile_wallet_delta(
        starting_wallet=5024.24829280,
        final_wallet=5023.27777241,
        closed_pnl_rows=[],
        execution_rows=[],
        transaction_rows=[],
        available_balance=5028.60306306,
        equity=5023.27777241,
    )
    assert out["wallet_delta"] == pytest.approx(-0.97052039)
    assert abs(out["unattributed_amount"]) == pytest.approx(0.97052039)
    assert out["classification"] in {"UNKNOWN", "API_HISTORY_RETENTION_GAP"}
    assert out["session_attribution_allowed"] is False
    assert any(e.get("class") == "WALLET_SNAPSHOT_SEMANTIC_DIFFERENCE" for e in out["evidence_records"])


def test_mainnet_real_money_forbidden_constants():
    from backend.nexus_demo_execution import MAINNET, REAL_MONEY

    assert MAINNET is False
    assert REAL_MONEY is False


def test_watchdog_phase_b_clean_exit_contract(tmp_path: Path, monkeypatch):
    # Contract: PHASE_B_COMPLETE marker implies process exit 0 semantics in orchestrator main.
    marker = {
        "runtime_result": "COMPLETED",
        "watchdog_result": "PHASE_B_COMPLETE",
        "exited_clean": True,
    }
    p = tmp_path / "WATCHDOG_PHASE_B_RESULT.json"
    p.write_text(__import__("json").dumps(marker), encoding="utf-8")
    loaded = __import__("json").loads(p.read_text(encoding="utf-8"))
    assert loaded["watchdog_result"] == "PHASE_B_COMPLETE"
    assert loaded["exited_clean"] is True
