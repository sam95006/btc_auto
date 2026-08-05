"""Tests for V15-B Mechanism Execution Compiler."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_mechanism_execution_compiler.adversarial import run_adversarial_review
from backend.nexus_mechanism_execution_compiler.artifacts import (
    build_summary_payload,
    write_immutable_artifacts,
)
from backend.nexus_mechanism_execution_compiler.campaign import run_compiler_campaign
from backend.nexus_mechanism_execution_compiler.compiler import (
    assert_executors_distinct,
    compile_all_executors,
    executor_catalog,
)
from backend.nexus_mechanism_execution_compiler.constants import (
    EXPECTED_MECHANISM_COUNT,
    HARD_BANS,
    MIN_EXECUTOR_COUNT,
    REQUIRED_EXECUTOR_FIELDS,
)
from backend.nexus_mechanism_execution_compiler.replay import assert_replay_stable
from backend.nexus_mechanism_lab_v4.catalog import SPECS


def test_compiles_all_42_distinct_executors() -> None:
    contracts = compile_all_executors()
    assert_executors_distinct(contracts)
    assert len(contracts) == EXPECTED_MECHANISM_COUNT
    assert len(contracts) >= MIN_EXECUTOR_COUNT
    assert len(SPECS) == EXPECTED_MECHANISM_COUNT
    assert {c.mechanism_id for c in contracts} == {s.mechanism_id for s in SPECS}
    catalog = executor_catalog()
    assert len(catalog) == len(contracts)
    for row in catalog:
        for field in REQUIRED_EXECUTOR_FIELDS:
            assert row.get(field)


def test_campaign_hard_bans_and_no_claims() -> None:
    report = run_compiler_campaign(pass_id=1)
    assert report["mechanism_executor_count"] == 42
    assert report["qualification_ready_count"] == 0
    assert report["edge_claim_count"] == 0
    assert report["profitability_claim_count"] == 0
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_executed"] is False
    assert report["oos_consumed"] is False
    assert report["demo_order_count"] == 0
    assert report["shadow_order_count"] == 0
    assert report["exchange_write_attempt_count"] == 0
    assert report["mainnet_touch_count"] == 0
    assert report["profitability_claimed"] is False
    assert report["edge_claimed"] is False
    assert report["qualified_claimed"] is False
    assert report["pr27_merge_attempted"] is False
    assert report["auto_integrate_attempted"] is False
    assert report["status_json_written"] is False
    assert set(HARD_BANS).issubset(set(report["hard_bans"]))
    for e in report["executors"]:
        assert e["qualified"] is False
        assert e["qualification_ready"] is False
        assert e["edge_claimed"] is False
        assert e["profitability_claimed"] is False
        assert e["data_lineage"] == "SYNTHETIC_DEVELOPMENT_FIXTURE"
        assert e["negative_test_covered"] is True
        assert e["economic_rationale_linkage"]["mechanism_id"] == e["mechanism_id"]


def test_deterministic_replay_stable() -> None:
    stab = assert_replay_stable()
    assert stab["ok"] is True
    assert stab["executor_count"] == 42
    r1 = run_compiler_campaign(pass_id=1)
    r2 = run_compiler_campaign(pass_id=2)
    assert r1["campaign_digest"] == r2["campaign_digest"]
    assert r1["code_checksum"] == r2["code_checksum"]


def test_two_pass_adversarial() -> None:
    r1 = run_compiler_campaign(pass_id=1)
    a1 = run_adversarial_review(r1, pass_name="pass_1")
    r2 = run_compiler_campaign(pass_id=2)
    a2 = run_adversarial_review(r2, pass_name="pass_2")
    assert a1["pass_ok"] is True
    assert a2["pass_ok"] is True
    assert a1["remaining_count"] == 0
    assert a2["remaining_count"] == 0
    assert a1["critical_remaining"] == 0
    assert a2["critical_remaining"] == 0
    assert a1["high_remaining"] == 0
    assert a2["high_remaining"] == 0
    assert a2["qualification_ready_count"] == 0
    assert a2["mechanism_executor_count"] == 42


def test_artifacts_without_status_json(tmp_path: Path) -> None:
    report = run_compiler_campaign(pass_id=2)
    a1 = run_adversarial_review(report, pass_name="pass_1")
    a2 = run_adversarial_review(report, pass_name="pass_2")
    paths = write_immutable_artifacts(report, [a1, a2], root=tmp_path)
    assert paths["campaign_report"].is_file()
    assert paths["executor_catalog"].is_file()
    assert paths["campaign_summary"].is_file()
    assert not (tmp_path / "artifacts" / "readiness" / "immutable" / "v15_mechanism_execution_compiler" / "status.json").exists()
    assert list(
        (tmp_path / "artifacts" / "readiness" / "immutable" / "v15_mechanism_execution_compiler").glob(
            "*_status.json"
        )
    ) == []
    summary = build_summary_payload(report, [a1, a2], root=tmp_path)
    assert summary["qualification_ready_count"] == 0
    assert summary["status_json_written"] is False
    assert summary["mechanism_executor_count"] == 42
