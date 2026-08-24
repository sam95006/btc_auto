"""Autonomous execution failure-mode E2E — offline contract and workflow DAG."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_demo_execution.durable_order_ledger import ALLOWED_TRANSITIONS, make_order_link_id
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP
from tools.ci.p2_failure_mode_e2e_qualification import (
    FailureModeRuntime,
    ProductionTransitionLedger,
    run,
    scenario_a_submit_timeout,
    scenario_b_duplicate_idempotency,
    scenario_c_partial_fill,
    scenario_d_cancel_race,
    scenario_e_process_restart,
    scenario_f_orphan,
    scenario_g_kill_switch,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/founder_approved_bybit_demo_failure_mode_e2e_qualification.yml"
MIGRATION_0007 = ROOT / "backend/nexus_persistence_pg/migrations/0007_p2_research_learning_store.sql"
RMG = ROOT / "backend/nexus_demo_execution/p2_run8_learning_closure.py"
P1_QUAL = ROOT / "backend/nexus_demo_execution/p1_qualification.py"


def test_full_matrix_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        monkeypatch.setenv(key, "false")
    evidence = run()
    assert evidence["FAILURE_MODE_E2E_PASS"] is True
    assert evidence["FAILURE_MODE_E2E_IMPLEMENTED"] is True
    assert evidence["SUBMIT_TIMEOUT_UNKNOWN_OUTCOME_PASS"] is True
    assert evidence["UNKNOWN_OUTCOME_BLIND_RETRY_FALSE"] is True
    assert evidence["EXACT_ORDERLINK_RECONCILIATION_PASS"] is True
    assert evidence["DUPLICATE_RETRY_IDEMPOTENCY_PASS"] is True
    assert evidence["PARTIAL_FILL_STATE_PASS"] is True
    assert evidence["PARTIAL_FILL_POSITION_TRUTH_PASS"] is True
    assert evidence["PARTIAL_FILL_ACCOUNTING_PASS"] is True
    assert evidence["CANCEL_FILL_RACE_PASS"] is True
    assert evidence["MONOTONIC_ORDER_STATE_PASS"] is True
    assert evidence["PROCESS_RESTART_RECOVERY_PASS"] is True
    assert evidence["RESTART_DUPLICATE_ORDER_FALSE"] is True
    assert evidence["ORPHAN_INTENT_DETECTED"] is True
    assert evidence["ORPHAN_BLOCKS_NEW_ENTRY"] is True
    assert evidence["ORPHAN_RECONCILIATION_PASS"] is True
    assert evidence["KILL_SWITCH_ORDERING_PASS"] is True
    assert evidence["POST_KILL_NEW_ENTRY_COUNT"] == 0
    assert evidence["DURABLE_LEDGER_INVARIANTS_PASS"] is True
    assert evidence["RISK_ENGINE_FINAL_AUTHORITY_PASS"] is True
    assert evidence["REPEAT_MISTAKE_GUARD_UNCHANGED"] is True
    assert evidence["create_order_calls"] == 0
    assert evidence["exchange_write_call_count"] == 0
    blob = json.dumps(evidence)
    assert "api-demo.bybit.com" not in blob
    assert "create_market_order" not in blob


def test_a_timeout_does_not_blind_retry() -> None:
    result = scenario_a_submit_timeout()
    assert result["UNKNOWN_OUTCOME_BLIND_RETRY_FALSE"] is True
    assert result["EXACT_ORDERLINK_RECONCILIATION_PASS"] is True
    assert result["SUBMIT_TIMEOUT_UNKNOWN_OUTCOME_PASS"] is True


def test_b_duplicate_same_link() -> None:
    assert scenario_b_duplicate_idempotency()["DUPLICATE_RETRY_IDEMPOTENCY_PASS"] is True


def test_c_partial_fill_qty_truth() -> None:
    result = scenario_c_partial_fill()
    assert result["PARTIAL_FILL_STATE_PASS"] is True
    assert result["PARTIAL_FILL_POSITION_TRUTH_PASS"] is True
    assert result["PARTIAL_FILL_ACCOUNTING_PASS"] is True


def test_d_cancel_fill_race_monotonic() -> None:
    result = scenario_d_cancel_race()
    assert result["CANCEL_FILL_RACE_PASS"] is True
    assert result["MONOTONIC_ORDER_STATE_PASS"] is True
    assert "FILLED" in result["fill_path_states"]
    assert "CANCELLED" in result["cancel_path_states"]


def test_e_restart_reconciles_before_create() -> None:
    result = scenario_e_process_restart()
    assert result["PROCESS_RESTART_RECOVERY_PASS"] is True
    assert result["RESTART_DUPLICATE_ORDER_FALSE"] is True


def test_f_orphan_blocks_new_entry() -> None:
    result = scenario_f_orphan()
    assert result["ORPHAN_INTENT_DETECTED"] is True
    assert result["ORPHAN_BLOCKS_NEW_ENTRY"] is True
    assert result["ORPHAN_RECONCILIATION_PASS"] is True


def test_g_kill_blocks_new_entries() -> None:
    result = scenario_g_kill_switch()
    assert result["KILL_SWITCH_ORDERING_PASS"] is True
    assert result["POST_KILL_NEW_ENTRY_COUNT"] == 0


def test_no_latest_row_order_lookup() -> None:
    runtime = FailureModeRuntime()
    intent = runtime._intent(order_intent_id="fm_lookup")
    link = runtime.persist_intent(intent)
    runtime.submit(intent, order_link_id=link)
    assert runtime.exchange.find_order(symbol="BTCUSDT") is None
    assert runtime.exchange.find_order(symbol="BTCUSDT", order_id="", order_link_id="") is None
    exact = runtime.exchange.find_order(symbol="BTCUSDT", order_link_id=link)
    assert exact is not None
    assert exact["orderLinkId"] == link


def test_production_transition_rules_enforced() -> None:
    ledger = ProductionTransitionLedger()
    runtime = FailureModeRuntime(ledger=ledger)
    intent = runtime._intent(order_intent_id="fm_illegal")
    runtime.persist_intent(intent)
    with pytest.raises(ValueError, match="invalid_transition"):
        ledger.transition(intent.order_intent_id, "FILLED", source="illegal")
    assert "CANCELLED" not in ALLOWED_TRANSITIONS.get("FILLED", set())


def test_order_link_id_is_production_helper() -> None:
    link = make_order_link_id("c", "d", "i")
    assert link.startswith("nx-")
    assert len(link) <= 36


def test_hard_risk_constants_untouched() -> None:
    assert FIXED_LEVERAGE == 25
    assert float(MARGIN_PER_TRADE_CAP) == 20.0


def test_workflow_is_founder_dispatch_and_disarmed() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "QUALIFY_NEXUS_BYBIT_DEMO_FAILURE_MODE_E2E" in source
    assert "python -m tools.ci.p2_failure_mode_e2e_qualification" in source
    assert "p2_historical_p1_p2_regression_lock" in source
    assert "RUN_ONE_BYBIT_DEMO_TRADE" not in source
    assert "ensure_p2_migration_zeabur_service" not in source
    for flag in ("MAINNET", "REAL_MONEY", "EXCHANGE_WRITE", "DEMO_AUTONOMOUS_ENABLED", "AUTONOMOUS_SEND"):
        assert f'{flag}: "false"' in source or f"{flag}=false" in source


def test_does_not_import_real_write_client() -> None:
    source = (ROOT / "tools/ci/p2_failure_mode_e2e_qualification.py").read_text(encoding="utf-8")
    assert "demo_write_client" not in source
    assert "create_market_order" not in source
    assert "if test_mode" not in source


def test_frozen_surfaces_not_rewritten_by_this_module() -> None:
    assert MIGRATION_0007.is_file()
    sql = MIGRATION_0007.read_text(encoding="utf-8")
    assert "DROP TABLE" not in sql.upper()
    assert "policy_truth" in RMG.read_text(encoding="utf-8")
    assert "P1QualificationRunner" in P1_QUAL.read_text(encoding="utf-8")
