"""Tests for NEXUS_FORMAL_QUALIFICATION_INFRASTRUCTURE_V1 — synthetic only."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_autonomy.formal_qualification_infrastructure_v1 import (
    INFRA_STATUS_BLOCKED_READY,
    SCHEMA_ID,
    FormalQualificationInfrastructureV1,
    run_infrastructure_dry_run,
    synthetic_candidate_fixture,
    synthetic_interval_fixture,
    write_immutable_artifacts,
)
from backend.nexus_autonomy.qualification_checksums import (
    compute_candidate_checksum,
    compute_parameter_checksum,
    compute_semantic_checksum,
    stamp_checksums,
    validate_checksums,
)
from backend.nexus_autonomy.qualification_interval_registry import (
    IntervalRecord,
    IntervalRegistry,
    assert_future_data_excluded,
    build_empty_registries,
    prove_oos_non_consumption,
)
from backend.nexus_autonomy.qualification_promotion_sm import (
    QUALIFICATION_STAGES,
    STAGE_STATUS_BLOCKED,
    FounderAuthorizationGate,
    PromotionStateMachine,
)


def test_schema_and_blocked_ready_status():
    summary = run_infrastructure_dry_run()
    assert summary["schema"] == SCHEMA_ID
    assert summary["status"] == INFRA_STATUS_BLOCKED_READY
    assert summary["Qualification_Infrastructure_status"] == INFRA_STATUS_BLOCKED_READY
    assert summary["all_stages_blocked"] is True


def test_all_stages_default_blocked():
    summary = run_infrastructure_dry_run()
    assert list(summary["stage_order"]) == list(QUALIFICATION_STAGES)
    for stage in QUALIFICATION_STAGES:
        assert summary["stages"][stage] == STAGE_STATUS_BLOCKED
    # Required stage names from Founder directive
    required = {
        "CANDIDATE_FREEZE",
        "REPLAY",
        "CHRONOLOGICAL_WALK_FORWARD",
        "CONCENTRATION_REVIEW",
        "COST_STRESS",
        "RISK_REVIEW",
        "UNTOUCHED_OOS_RESERVATION",
        "OOS_EXECUTION_AUTHORIZATION",
        "DEMO_ELIGIBILITY",
    }
    assert required == set(QUALIFICATION_STAGES)


def test_candidate_semantic_parameter_checksums():
    raw = synthetic_candidate_fixture()
    stamped = stamp_checksums(raw)
    assert stamped["candidate_checksum"] == compute_candidate_checksum(stamped)
    assert stamped["semantic_checksum"] == compute_semantic_checksum(stamped)
    assert stamped["parameter_checksum"] == compute_parameter_checksum(stamped)
    assert validate_checksums(stamped) == []

    tampered = dict(stamped)
    tampered["parameters"] = {**stamped["parameters"], "lookback": 999}
    assert "parameter_checksum_mismatch" in validate_checksums(tampered)


def test_interval_registries_present():
    summary = run_infrastructure_dry_run()
    regs = summary["registries"]
    for kind in ("data", "consumed", "reserved"):
        assert kind in regs
        assert regs[kind]["interval_count"] >= 1
        assert len(regs[kind]["checksum"]) == 64


def test_future_data_exclusion():
    as_of = 1_700_000_000_000
    bad = assert_future_data_excluded(
        proposed_start_ms=as_of - 1000,
        proposed_end_ms=as_of + 86_400_000,
        as_of_ms=as_of,
    )
    assert bad["allowed"] is False
    assert bad["status"] == "FUTURE_DATA_VIOLATION"

    good = assert_future_data_excluded(
        proposed_start_ms=as_of - 10 * 86_400_000,
        proposed_end_ms=as_of - 5 * 86_400_000,
        as_of_ms=as_of,
    )
    assert good["allowed"] is True
    assert good["future_data_excluded"] is True


def test_oos_non_consumption_proof():
    regs = synthetic_interval_fixture()
    proof = prove_oos_non_consumption(
        reserved=regs["reserved"],
        consumed=regs["consumed"],
        data=regs["data"],
    )
    assert proof["proven"] is True
    assert proof["status"] == "OOS_NON_CONSUMPTION_PROVEN"
    assert proof["oos_executed"] is False
    assert proof["formal_walk_forward_executed"] is False

    # Inject consumption of reserved window → must fail
    regs["consumed"].add(
        IntervalRecord(
            interval_id="BAD_CONSUME",
            label="illegal",
            start_ms=regs["reserved"].intervals[0].start_ms,
            end_ms=regs["reserved"].intervals[0].end_ms,
            category="consumed",
        )
    )
    bad = prove_oos_non_consumption(
        reserved=regs["reserved"],
        consumed=regs["consumed"],
        data=regs["data"],
    )
    assert bad["proven"] is False
    assert bad["status"] == "OOS_NON_CONSUMPTION_FAILED"


def test_founder_authorization_gate_fail_closed():
    gate = FounderAuthorizationGate()
    missing = gate.evaluate(None)
    assert missing["authorized"] is False
    assert missing["reason"] == "FOUNDER_AUTHORIZATION_MISSING"

    # Even well-formed explicit request is denied in V1 dry-run
    denied = gate.evaluate(
        {
            "founder_authorization_token": "fake-token-not-real",
            "actor": "founder",
            "scope": "formal_qualification_v1",
            "explicit_authorize": True,
        }
    )
    assert denied["authorized"] is False
    assert denied["reason"] == "FOUNDER_AUTHORIZATION_DENIED"


def test_promotion_state_machine_never_promotes():
    sm = PromotionStateMachine()
    sm.mark_infrastructure_ready()
    sm.register_synthetic_candidate("SYNTHETIC_QUAL_CANDIDATE_V1")
    sm.request_founder_authorization(None)
    for stage in QUALIFICATION_STAGES:
        result = sm.attempt_advance_stage(stage)
        assert result["allowed"] is False
        assert sm.stages[stage] == STAGE_STATUS_BLOCKED
    promote = sm.attempt_promote()
    assert promote["allowed"] is False
    assert promote["selected_strategy"] is None
    assert sm.state == "PROMOTION_BLOCKED"
    assert sm.selected_strategy is None
    assert sm.formal_walk_forward_executed is False
    assert sm.oos_executed is False
    assert sm.demo_eligibility is False


def test_no_real_execution_flags():
    summary = run_infrastructure_dry_run()
    assert summary["formal_walk_forward_executed"] is False
    assert summary["oos_executed"] is False
    assert summary["demo_order_count"] == 0
    assert summary["exchange_write_attempt_count"] == 0
    assert summary["selected_strategy"] is None
    assert summary["strategy_promoted"] is False
    assert summary["demo_eligibility"] is False
    assert summary["candidate"]["fixture_only"] is True
    assert summary["candidate"]["selected"] is False


def test_stage_advance_blocked_on_orchestrator():
    infra = FormalQualificationInfrastructureV1()
    summary = infra.bootstrap_synthetic()
    proofs = summary["proofs"]
    for stage in QUALIFICATION_STAGES:
        assert proofs["stage_advance_attempts"][stage]["allowed"] is False
    assert proofs["promote_attempt"]["allowed"] is False


def test_write_immutable_artifacts(tmp_path: Path):
    summary = run_infrastructure_dry_run()
    paths = write_immutable_artifacts(summary, root=tmp_path)
    status = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert status["schema"] == SCHEMA_ID
    assert status["status"] == INFRA_STATUS_BLOCKED_READY
    assert status["formal_walk_forward_executed"] is False
    assert status["oos_executed"] is False
    assert status["selected_strategy"] is None

    stages = json.loads(paths["stages"].read_text(encoding="utf-8"))
    assert all(v == STAGE_STATUS_BLOCKED for v in stages["stages"].values())

    checksums = json.loads(paths["checksums"].read_text(encoding="utf-8"))
    assert checksums["fixture_only"] is True
    assert checksums["selected"] is False
    assert len(checksums["candidate_checksum"]) == 64


def test_registry_checksum_stable():
    a = build_empty_registries()
    a["data"].add(
        IntervalRecord("A", "a", 100, 200, "data")
    )
    b = IntervalRegistry(kind="data")
    b.add(IntervalRecord("A", "a", 100, 200, "data"))
    assert a["data"].checksum() == b.checksum()
