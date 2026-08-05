"""Tests for V16-E Lesson Compiler."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_lesson_compiler.adversarial import run_adversarial_review
from backend.nexus_lesson_compiler.artifacts import (
    build_summary_payload,
    write_immutable_artifacts,
)
from backend.nexus_lesson_compiler.campaign import run_compiler_campaign
from backend.nexus_lesson_compiler.compiler import (
    assert_lessons_safe,
    compile_all_lessons,
    lesson_catalog,
)
from backend.nexus_lesson_compiler.constants import (
    EXPECTED_FIXTURE_COUNT,
    HARD_BANS,
    LESSON_STATUS_CANDIDATE,
    MIN_LESSON_COUNT,
    REQUIRED_LESSON_FIELDS,
)
from backend.nexus_lesson_compiler.fixtures import REFLECTION_FIXTURES


def test_compiles_all_candidate_lessons() -> None:
    rules = compile_all_lessons()
    assert_lessons_safe(rules)
    assert len(rules) == EXPECTED_FIXTURE_COUNT
    assert len(rules) >= MIN_LESSON_COUNT
    assert len(REFLECTION_FIXTURES) == EXPECTED_FIXTURE_COUNT
    catalog = lesson_catalog()
    assert len(catalog) == len(rules)
    for row in catalog:
        assert row["status"] == LESSON_STATUS_CANDIDATE
        for field in REQUIRED_LESSON_FIELDS:
            assert field in row
        assert row["mutates_production_risk"] is False
        assert row["mutates_production_leverage"] is False
        assert row["conditions"]
        assert row["then_action"]["action_kind"]
        assert row["author_model"]
        assert row["author_version"]
        assert row["evidence_count"] >= 1
        assert 0.0 <= row["confidence"] <= 1.0


def test_founder_example_breakout_block() -> None:
    rules = {r.reflection_id: r for r in compile_all_lessons()}
    rule = rules["REFL_DEV_BREAKOUT_CROWDING_001"]
    fields = {c.field for c in rule.conditions}
    assert "volatility_regime" in fields
    assert "long_crowding" in fields
    assert "oi_confirmation" in fields
    assert rule.then_action.expert == "breakout_long"
    assert rule.then_action.action_kind == "BLOCK"
    assert rule.status == LESSON_STATUS_CANDIDATE


def test_campaign_hard_bans_and_candidate_only() -> None:
    report = run_compiler_campaign(pass_id=1)
    assert report["lesson_count"] == EXPECTED_FIXTURE_COUNT
    assert report["candidate_lesson_count"] == EXPECTED_FIXTURE_COUNT
    assert report["active_lesson_count"] == 0
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
    assert report["pr26_merge_attempted"] is False
    assert report["pr27_merge_attempted"] is False
    assert report["auto_integrate_attempted"] is False
    assert report["private_core_deploy_attempted"] is False
    assert report["production_risk_mutated"] is False
    assert report["production_leverage_mutated"] is False
    assert report["status_json_written"] is False
    assert set(HARD_BANS).issubset(set(report["hard_bans"]))
    for e in report["lessons"]:
        assert e["status"] == LESSON_STATUS_CANDIDATE
        assert e["active"] is False
        assert e["qualified"] is False
        assert e["qualification_ready"] is False
        assert e["edge_claimed"] is False
        assert e["profitability_claimed"] is False
        assert e["mutates_production_risk"] is False
        assert e["mutates_production_leverage"] is False
        assert e["data_lineage"] == "SYNTHETIC_DEVELOPMENT_FIXTURE"


def test_deterministic_three_pass_digest() -> None:
    r1 = run_compiler_campaign(pass_id=1)
    r2 = run_compiler_campaign(pass_id=2)
    r3 = run_compiler_campaign(pass_id=3)
    assert r1["campaign_digest"] == r2["campaign_digest"] == r3["campaign_digest"]
    assert r1["code_checksum"] == r2["code_checksum"] == r3["code_checksum"]


def test_three_pass_adversarial() -> None:
    r1 = run_compiler_campaign(pass_id=1)
    a1 = run_adversarial_review(r1, pass_name="pass_1")
    r2 = run_compiler_campaign(pass_id=2)
    a2 = run_adversarial_review(r2, pass_name="pass_2")
    r3 = run_compiler_campaign(pass_id=3)
    a3 = run_adversarial_review(r3, pass_name="pass_3")
    assert a1["pass_ok"] is True
    assert a2["pass_ok"] is True
    assert a3["pass_ok"] is True
    assert a1["remaining_count"] == 0
    assert a2["remaining_count"] == 0
    assert a3["remaining_count"] == 0
    assert a3["critical_remaining"] == 0
    assert a3["high_remaining"] == 0
    assert a3["active_lesson_count"] == 0
    assert a3["lesson_count"] == EXPECTED_FIXTURE_COUNT


def test_artifacts_without_status_json(tmp_path: Path) -> None:
    report = run_compiler_campaign(pass_id=3)
    a1 = run_adversarial_review(report, pass_name="pass_1")
    a2 = run_adversarial_review(report, pass_name="pass_2")
    a3 = run_adversarial_review(report, pass_name="pass_3")
    paths = write_immutable_artifacts(report, [a1, a2, a3], root=tmp_path)
    assert paths["campaign_report"].is_file()
    assert paths["lesson_catalog"].is_file()
    assert paths["adversarial_pass_3"].is_file()
    assert not (
        tmp_path / "artifacts" / "readiness" / "immutable" / "v16_lesson_compiler" / "status.json"
    ).exists()
    assert list(
        (tmp_path / "artifacts" / "readiness" / "immutable" / "v16_lesson_compiler").glob(
            "*_status.json"
        )
    ) == []
    summary = build_summary_payload(report, [a1, a2, a3], root=tmp_path)
    assert summary["qualification_ready_count"] == 0
    assert summary["active_lesson_count"] == 0
    assert summary["status_json_written"] is False
    assert summary["pass_1_ok"] and summary["pass_2_ok"] and summary["pass_3_ok"]
