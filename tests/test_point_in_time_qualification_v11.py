"""Tests for Founder V11 point-in-time qualification infrastructure."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_qualification.pit_v11.infrastructure import (
    OOS_FALSE_FLAGS,
    PIT_STATUS_BLOCKED_READY,
    QUALIFICATION_STAGES,
    SCHEMA_ID,
    STAGE_STATUS_BLOCKED_READY,
    FounderAuthorizationGate,
    IntervalRecord,
    IntervalRegistry,
    PromotionStateMachine,
    PointInTimeQualificationV11,
    build_oos_cryptographic_seal,
    prove_future_data_exclusion,
    prove_oos_non_consumption,
    run_point_in_time_qualification_dry_run,
    semantic_checksums,
    sha_obj,
    synthetic_candidate_fixture,
    synthetic_dataset_lineage,
    synthetic_interval_registries,
    write_immutable_artifacts,
)


def test_status_and_all_stages_blocked_ready() -> None:
    summary = run_point_in_time_qualification_dry_run()
    assert summary["schema"] == SCHEMA_ID
    assert summary["status"] == PIT_STATUS_BLOCKED_READY
    assert summary["all_stages_blocked_ready"] is True
    assert list(summary["stage_order"]) == list(QUALIFICATION_STAGES)
    assert all(status == STAGE_STATUS_BLOCKED_READY for status in summary["stages"].values())


def test_dataset_lineage_has_point_in_time_timestamps() -> None:
    as_of = 1_700_000_000_000
    summary = run_point_in_time_qualification_dry_run(as_of_ms=as_of)
    lineage = summary["dataset_lineage"]
    assert lineage["fixture_only"] is True
    assert lineage["real_market_data"] is False
    assert lineage["source_timestamp_ms"] < lineage["retrieval_timestamp_ms"] < lineage["as_of_ms"]
    assert lineage["availability_timestamp_ms"] <= lineage["as_of_ms"]
    for record in lineage["records"]:
        assert record["source_timestamp_ms"] <= record["retrieval_timestamp_ms"]
        assert record["availability_timestamp_ms"] <= as_of
        assert record["available_as_of_ms"] <= as_of


def test_future_data_exclusion_detects_violations() -> None:
    as_of = 1_700_000_000_000
    dataset = synthetic_dataset_lineage(as_of_ms=as_of)
    ok = prove_future_data_exclusion(dataset, as_of_ms=as_of)
    assert ok["allowed"] is True
    assert ok["future_data_excluded"] is True

    bad = dict(dataset)
    bad["records"] = [dict(dataset["records"][0], availability_timestamp_ms=as_of + 1)]
    violation = prove_future_data_exclusion(bad, as_of_ms=as_of)
    assert violation["allowed"] is False
    assert violation["status"] == "FUTURE_DATA_VIOLATION"


def test_candidate_parameter_code_dataset_semantic_checksums() -> None:
    candidate = synthetic_candidate_fixture()
    dataset = synthetic_dataset_lineage()
    checksums = semantic_checksums(candidate, dataset, "code-sha")
    assert len(checksums["candidate_checksum"]) == 64
    assert len(checksums["candidate_semantic_checksum"]) == 64
    assert len(checksums["parameter_checksum"]) == 64
    assert checksums["code_checksum"] == "code-sha"
    assert checksums["dataset_checksum"] == dataset["dataset_checksum"]
    assert checksums["dataset_semantic_checksum"] == dataset["dataset_semantic_checksum"]

    tampered = dict(candidate)
    tampered["parameters"] = {**candidate["parameters"], "lookback": 999}
    assert semantic_checksums(tampered, dataset, "code-sha")["parameter_checksum"] != checksums["parameter_checksum"]


def test_interval_registries_consumed_reserved_and_stable_checksums() -> None:
    regs = synthetic_interval_registries()
    assert set(regs) == {"consumed", "reserved", "availability"}
    assert regs["consumed"].to_dict()["interval_count"] == 1
    assert regs["reserved"].to_dict()["interval_count"] == 1
    assert len(regs["reserved"].checksum()) == 64

    clone = IntervalRegistry("reserved")
    source = regs["reserved"].intervals[0]
    clone.add(IntervalRecord(**source.to_dict()))
    assert clone.checksum() == regs["reserved"].checksum()


def test_oos_non_consumption_proof_fails_on_overlap() -> None:
    regs = synthetic_interval_registries()
    proof = prove_oos_non_consumption(regs)
    assert proof["proven"] is True
    assert proof["oos_consumed"] is False
    assert proof["oos_executed"] is False
    assert proof["formal_walk_forward_executed"] is False

    reserved = regs["reserved"].intervals[0]
    regs["consumed"].add(
        IntervalRecord("BAD_OVERLAP", "bad_overlap", reserved.start_ms, reserved.end_ms, "consumed")
    )
    bad = prove_oos_non_consumption(regs)
    assert bad["proven"] is False
    assert bad["status"] == "OOS_NON_CONSUMPTION_FAILED"


def test_oos_cryptographic_seal_is_deterministic_and_unconsumed() -> None:
    regs = synthetic_interval_registries()
    dataset = synthetic_dataset_lineage()
    checksums = semantic_checksums(synthetic_candidate_fixture(), dataset, "code-sha")
    seal = build_oos_cryptographic_seal(regs, checksums)
    expected_payload = {
        "reserved_registry_checksum": regs["reserved"].checksum(),
        "candidate_checksum": checksums["candidate_checksum"],
        "dataset_semantic_checksum": checksums["dataset_semantic_checksum"],
        "status": "SEALED_NOT_CONSUMED",
        "fixture_only": True,
    }
    assert seal["seal"] == sha_obj(expected_payload)
    assert seal["oos_revealed_to_candidate"] is False
    assert seal["oos_consumed"] is False


def test_founder_authorization_gate_fails_closed() -> None:
    gate = FounderAuthorizationGate()
    missing = gate.evaluate(None)
    assert missing["authorized"] is False
    assert missing["reason"] == "FOUNDER_AUTHORIZATION_MISSING"

    denied = gate.evaluate({"founder_authorization_token": "fake", "scope": "founder_v11_pit_qualification"})
    assert denied["authorized"] is False
    assert denied["reason"] == "FOUNDER_AUTHORIZATION_DENIED_BLOCKED_ONLY_V11"


def test_promotion_state_machine_never_promotes() -> None:
    sm = PromotionStateMachine()
    result = sm.attempt_promote()
    assert result["allowed"] is False
    assert result["selected_strategy"] is None
    assert result["formal_walk_forward_executed"] is False
    assert result["oos_executed"] is False
    assert result["demo_order_count"] == 0
    assert all(status == STAGE_STATUS_BLOCKED_READY for status in sm.stages.values())


def test_required_no_execution_flags() -> None:
    summary = PointInTimeQualificationV11().bootstrap_synthetic()
    assert summary["formal_walk_forward_executed"] is False
    assert summary["demo_order_count"] == 0
    assert summary["exchange_write_attempt_count"] == 0
    assert summary["selected_strategy"] is None
    assert summary["strategy_selected"] is False
    assert summary["strategy_promoted"] is False
    assert summary["demo_eligibility"] is False
    for flag in OOS_FALSE_FLAGS:
        assert summary[flag] is False


def test_write_immutable_artifacts(tmp_path: Path) -> None:
    summary = run_point_in_time_qualification_dry_run()
    paths = write_immutable_artifacts(summary, root=tmp_path)
    assert set(paths) == {
        "status",
        "dataset_lineage",
        "semantic_checksums",
        "interval_registries",
        "oos_cryptographic_seal",
        "oos_non_consumption_proof",
        "founder_authorization_gate",
        "promotion_state_machine",
        "stage_matrix",
        "summary",
    }
    status = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert status["status"] == PIT_STATUS_BLOCKED_READY
    assert status["formal_walk_forward_executed"] is False
    assert status["oos_executed"] is False
    assert status["demo_order_count"] == 0

    stage_matrix = json.loads(paths["stage_matrix"].read_text(encoding="utf-8"))
    assert all(value == STAGE_STATUS_BLOCKED_READY for value in stage_matrix["stages"].values())
