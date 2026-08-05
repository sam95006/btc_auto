"""Negative tests for V16-E Lesson Compiler — fail-closed + hard bans."""
from __future__ import annotations

import pytest

from backend.nexus_lesson_compiler.campaign import run_compiler_campaign
from backend.nexus_lesson_compiler.compiler import (
    LessonCompileError,
    compile_raw_dict,
    compile_reflection,
)
from backend.nexus_lesson_compiler.contracts import ReflectionFixture
from backend.nexus_lesson_compiler.fixtures import REFLECTION_FIXTURES


def _base_payload(**overrides):
    f = REFLECTION_FIXTURES[0]
    payload = {
        "reflection_id": f.reflection_id + "_NEG",
        "conditions": list(f.conditions),
        "then_action": dict(f.then_action),
        "scope": f.scope,
        "affected_expert": f.affected_expert,
        "regimes": list(f.regimes),
        "expiry": dict(f.expiry),
        "evidence_count": f.evidence_count,
        "confidence": f.confidence,
        "contradictory_evidence": list(f.contradictory_evidence),
        "author_model": f.author_model,
        "author_version": f.author_version,
        "narrative": f.narrative,
        "status": "CANDIDATE",
    }
    payload.update(overrides)
    return payload


def test_fail_closed_rejects_active_status() -> None:
    with pytest.raises(LessonCompileError, match="candidate"):
        compile_raw_dict(_base_payload(status="ACTIVE"))


def test_fail_closed_rejects_promotion_statuses() -> None:
    for status in (
        "REPLAY_VALIDATED",
        "WALK_FORWARD_PENDING",
        "OOS_PENDING",
        "SHADOW_PENDING",
        "DEMO_PENDING",
        "DEGRADED",
        "RETIRED",
    ):
        with pytest.raises(LessonCompileError):
            compile_raw_dict(_base_payload(status=status))


def test_fail_closed_rejects_risk_leverage_mutation_targets() -> None:
    for target in ("risk_limit", "max_leverage", "leverage", "position_size", "production_risk"):
        action = dict(_base_payload()["then_action"])
        action["target"] = target
        with pytest.raises(LessonCompileError, match="production_risk_or_leverage"):
            compile_raw_dict(_base_payload(then_action=action))


def test_fail_closed_rejects_empty_conditions() -> None:
    with pytest.raises(LessonCompileError, match="conditions_empty"):
        compile_raw_dict(_base_payload(conditions=[]))


def test_fail_closed_rejects_illegal_op() -> None:
    bad = [{"field": "x", "op": "REGEX", "value": ".*"}]
    with pytest.raises(LessonCompileError, match="condition_op_illegal"):
        compile_raw_dict(_base_payload(conditions=bad))


def test_fail_closed_rejects_missing_author() -> None:
    with pytest.raises(LessonCompileError, match="author"):
        compile_raw_dict(_base_payload(author_model="", author_version=""))


def test_fail_closed_rejects_confidence_out_of_range() -> None:
    with pytest.raises(LessonCompileError, match="confidence"):
        compile_raw_dict(_base_payload(confidence=1.5))


def test_fail_closed_rejects_missing_expiry_bounds() -> None:
    with pytest.raises(LessonCompileError, match="expiry"):
        compile_raw_dict(
            _base_payload(
                expiry={
                    "expires_at_ms": None,
                    "max_age_bars": None,
                    "revalidation_required": True,
                }
            )
        )


def test_fail_closed_rejects_expert_mismatch() -> None:
    with pytest.raises(LessonCompileError, match="affected_expert_mismatch"):
        compile_raw_dict(_base_payload(affected_expert="other_expert"))


def test_fail_closed_rejects_high_confidence_without_contradictory() -> None:
    with pytest.raises(LessonCompileError, match="contradictory_evidence"):
        compile_raw_dict(_base_payload(contradictory_evidence=[], confidence=0.7))


def test_compile_reflection_forced_active_fails() -> None:
    with pytest.raises(LessonCompileError):
        compile_reflection(REFLECTION_FIXTURES[0], forced_status="ACTIVE")


def test_campaign_never_emits_active() -> None:
    report = run_compiler_campaign(pass_id=2)
    assert report["active_lesson_count"] == 0
    assert all(e["status"] == "CANDIDATE" for e in report["lessons"])
    assert report["status_json_written"] is False
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_executed"] is False
    assert report["auto_integrate_attempted"] is False


def test_malformed_payload_fail_closed() -> None:
    with pytest.raises(LessonCompileError):
        compile_raw_dict({"reflection_id": "x"})  # missing required structure


def test_fixture_dataclass_roundtrip_safe() -> None:
    f = REFLECTION_FIXTURES[1]
    assert isinstance(f, ReflectionFixture)
    rule = compile_reflection(f)
    assert rule.status == "CANDIDATE"
    assert rule.mutates_production_risk is False
