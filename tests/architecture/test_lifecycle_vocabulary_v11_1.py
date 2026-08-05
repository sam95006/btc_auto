"""CI tests for V11.1 lifecycle vocabulary unification.

Negative tests prove incompatible cross-lifecycle combinations cannot validate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_contracts.lifecycle.adapters import (
    ADAPTER_CONTRACT_ID,
    ControlPlaneSessionAdapter,
    adapter_contract_present,
    map_session_to_control,
)
from backend.nexus_contracts.lifecycle.blocked_ambiguous import blocked_ambiguous_policy
from backend.nexus_contracts.lifecycle.compatibility import (
    terminal_pair_status,
)
from backend.nexus_contracts.lifecycle.invariants import validate_snapshot
from backend.nexus_contracts.lifecycle.ontology import (
    LIFECYCLE_SCOPES,
    ONTOLOGY_VERSION,
    build_ontology,
)
from tools.architecture.check_contract_drift import run_drift_checks
from tools.architecture.run_authority_consolidation import run_pass


ROOT = Path(__file__).resolve().parents[2]


def test_ontology_keeps_scopes_separate():
    ont = build_ontology()
    assert ont["policy"]["collapse_to_single_fsm"] is False
    assert ont["version"] == ONTOLOGY_VERSION
    ids = {s.scope_id for s in LIFECYCLE_SCOPES}
    assert ids >= {
        "decision",
        "session",
        "intent",
        "order",
        "position",
        "reflection",
        "control_plane",
    }
    # Distinct owners for Session vs ControlPlane
    by = ont["by_scope"]
    assert by["session"]["owner_module"] != by["control_plane"]["owner_module"]


def test_adapter_contract_present_and_bans_silent_homonym():
    assert adapter_contract_present() is True
    adapter = ControlPlaneSessionAdapter()
    assert adapter.contract_id == ADAPTER_CONTRACT_ID
    hom = adapter.assert_no_silent_homonym("RUNNING")
    assert hom["homonym"] is True
    assert hom["silent_identity_allowed"] is False
    assert adapter.is_compatible("COMPLETED", "STOPPED")
    assert not adapter.is_compatible("COMPLETED", "KILLED")
    assert "STOPPED" in map_session_to_control("COMPLETED")


def test_neg_decision_closed_position_open():
    r = validate_snapshot(
        {"decision_state": "CLOSED", "position_state": "OPEN", "position_qty": "1"}
    )
    assert r["valid"] is False
    assert any(v["code"] == "INV_DECISION_CLOSED_POSITION_OPEN" for v in r["violations"])


def test_neg_session_completed_unresolved_intent():
    r = validate_snapshot(
        {
            "session_state": "COMPLETED",
            "intent_state": "WORKING",
            "position_state": "NONE",
        }
    )
    assert r["valid"] is False
    assert any(
        v["code"] == "INV_SESSION_COMPLETED_UNRESOLVED_INTENT" for v in r["violations"]
    )


def test_neg_reflection_complete_before_exit():
    r = validate_snapshot(
        {
            "reflection_state": "COMPLETE",
            "decision_state": "MONITORING",
            "exit_evidence": False,
        }
    )
    assert r["valid"] is False
    assert any(
        v["code"] == "INV_REFLECTION_COMPLETE_BEFORE_EXIT" for v in r["violations"]
    )


def test_neg_position_closed_residual_qty():
    r = validate_snapshot({"position_state": "CLOSED", "position_qty": "0.25"})
    assert r["valid"] is False
    assert any(v["code"] == "INV_POSITION_CLOSED_RESIDUAL_QTY" for v in r["violations"])


def test_pos_compatible_terminal_flat():
    r = validate_snapshot(
        {
            "decision_state": "CLOSED",
            "session_state": "COMPLETED",
            "intent_state": "FILLED",
            "order_state": "FILLED",
            "position_state": "CLOSED",
            "position_qty": "0",
            "reflection_state": "COMPLETE",
            "exit_evidence": True,
            "control_plane_state": "STOPPED",
        }
    )
    assert r["valid"] is True
    assert r["critical_count"] == 0


def test_terminal_compatibility_table_mission_rows():
    assert (
        terminal_pair_status("decision", "CLOSED", "position", "OPEN") == "incompatible"
    )
    assert (
        terminal_pair_status("session", "COMPLETED", "intent", "WORKING")
        == "incompatible"
    )
    assert (
        terminal_pair_status("reflection", "COMPLETE", "decision", "MONITORING")
        == "incompatible"
    )
    assert (
        terminal_pair_status("session", "COMPLETED", "control_plane", "STOPPED")
        == "compatible"
    )


def test_blocked_ambiguous_semantics():
    pol = blocked_ambiguous_policy()
    assert "BLOCKED" in pol["tokens"]
    assert "BLOCKED_AMBIGUOUS" in pol["tokens"]
    assert pol["tokens"]["BLOCKED_AMBIGUOUS"]["adjudication_required"] is True
    assert any(
        f["action"] == "silent_resume_from_BLOCKED_AMBIGUOUS" and f["allowed"] is False
        for f in pol["forbidden"]
    )


def test_drift_dual_lifecycle_resolved():
    report = run_drift_checks(ROOT)
    critical = {
        f["code"] for f in report["findings"] if f.get("severity") == "critical"
    }
    codes = {f["code"] for f in report["findings"]}
    assert "DUAL_LIFECYCLE_VOCABULARY" not in critical
    assert "DUAL_LIFECYCLE_VOCABULARY_SCOPED" in codes


def test_consolidation_lifecycle_multi_scope_resolved(tmp_path: Path):
    summary = run_pass(ROOT, tmp_path, "test_pass")
    lifecycle_blockers = [
        b
        for b in summary.get("blockers") or []
        if b.get("domain") == "lifecycle"
        and b.get("code") in {"MULTI_SCOPE_AUTHORITY", "MULTI_SCOPE_AUTHORITY_LIFECYCLE"}
    ]
    assert lifecycle_blockers == []


@pytest.mark.parametrize(
    "snapshot,code",
    [
        (
            {"decision_state": "CLOSED", "order_state": "ACCEPTED"},
            "INV_DECISION_CLOSED_NONTERMINAL_ORDER",
        ),
        (
            {"session_state": "COMPLETED", "position_state": "OPEN", "position_qty": "1"},
            "INV_SESSION_COMPLETED_OPEN_POSITION",
        ),
        (
            {"intent_state": "FILLED", "order_state": "CANCELLED"},
            "INV_INTENT_RESOLVED_ORDER_CONSISTENCY",
        ),
    ],
)
def test_additional_negative_invariants(snapshot, code):
    r = validate_snapshot(snapshot)
    assert any(v["code"] == code for v in r["violations"])
