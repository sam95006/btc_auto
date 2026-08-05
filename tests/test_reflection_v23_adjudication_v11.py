"""Tests for Founder V11 Lane E Reflection V2.3 adjudication."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["NEXUS_AI_MOCK"] = "1"

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_ai.scheduler import ProviderScheduler
from backend.nexus_provider.circuit_breaker import ProviderCircuitBreaker
from backend.nexus_reflection.adjudication_v11 import (
    CONTROL_FIXTURE_LABEL,
    build_critic_order,
    build_fixture_adjudication_result,
    dedupe_completed_cases,
    parse_provider_quota_reset,
    parse_provider_retry_after,
    record_provider_outcome,
    validate_terminal_denominators_v11,
)
from backend.nexus_reflection.adjudication_v11.core import build_disagreement_taxonomy
from backend.nexus_reflection.lesson_gate_v11 import apply_lesson_gate_v11


def test_provider_specific_queues_retry_after_quota_and_circuit():
    now = 1_750_000_000.0
    assert parse_provider_retry_after({"Retry-After": "12"}, now=now) == 12.0
    assert parse_provider_quota_reset({"x-ratelimit-reset": str(now + 30)}, now=now) == 30.0

    scheduler = ProviderScheduler(
        breaker=ProviderCircuitBreaker(failure_threshold=1),
        sleep_fn=lambda _s: None,
        time_fn=lambda: now,
    )
    scheduler.enqueue(GROQ_REFLECTION_REASONER, ["a"])
    scheduler.enqueue(SAMBANOVA_INDEPENDENT_CRITIC, ["b"])
    groq = record_provider_outcome(
        scheduler,
        profile_id=GROQ_REFLECTION_REASONER,
        case_id="a",
        prompt_hash="p1",
        schema_version="blind_reflection_v2_3",
        http_status=429,
        headers={"Retry-After": "15"},
    )
    samba = record_provider_outcome(
        scheduler,
        profile_id=SAMBANOVA_INDEPENDENT_CRITIC,
        case_id="b",
        prompt_hash="p2",
        schema_version="critic_v2_3",
        result_status="SUCCESS",
        response_payload={"critic_verdict": "BOTH_SUPPORTED"},
    )
    snap = scheduler.snapshot()
    assert groq["transport_status"] == "RATE_LIMITED"
    assert groq["quality_neutral_transport"] is True
    assert samba["transport_status"] == "SUCCESS"
    assert snap[GROQ_REFLECTION_REASONER]["HTTP_429_count"] == 1
    assert snap[SAMBANOVA_INDEPENDENT_CRITIC]["success_count"] == 1
    assert snap[GROQ_REFLECTION_REASONER]["circuit_breaker"]["state"] == "OPEN"
    assert snap[SAMBANOVA_INDEPENDENT_CRITIC]["circuit_breaker"]["state"] == "CLOSED"


def test_successful_case_dedupe_and_critic_response_ordering():
    assert dedupe_completed_cases(
        profile_id=GROQ_REFLECTION_REASONER,
        case_ids=["a", "b", "c", "b"],
        completed_case_ids=["b"],
    ) == ["a", "c"]
    state = {
        "case_ids": ["a", "b", "c", "d"],
        "completed_case_ids": ["a", "b", "c"],
        "critic_resolved_ids": ["c"],
        "case_results": {
            "a": {
                "evidence_sufficiency": "EVIDENCE_SUFFICIENT",
                "process_classification": "GOOD_PROCESS_WIN",
                "deterministic_expected": "BAD_PROCESS_WIN",
                "confidence": 0.9,
            },
            "b": {
                "evidence_sufficiency": "EVIDENCE_SUFFICIENT",
                "process_classification": "GOOD_PROCESS_LOSS",
                "deterministic_expected": "GOOD_PROCESS_LOSS",
                "confidence": 0.4,
            },
            "c": {
                "evidence_sufficiency": "EVIDENCE_SUFFICIENT",
                "process_classification": "BAD_PROCESS_WIN",
                "deterministic_expected": "GOOD_PROCESS_WIN",
                "confidence": 0.9,
            },
        },
    }
    assert build_critic_order(state) == ["a", "b"]


def test_disagreement_taxonomy_and_undetermined_migration():
    result = build_fixture_adjudication_result()
    records = result["disagreement_taxonomy"]
    conflict_types = {r["conflict_type"] for r in records}
    assert "DETERMINISTIC_BASELINE_TOO_COARSE" in conflict_types
    assert "AI_MISCLASSIFICATION" in conflict_types
    assert result["UNDETERMINED_PROCESS_migrated_to_UNDETERMINED"] is True
    assert result["label"] == CONTROL_FIXTURE_LABEL
    assert result["real_ai_quality_claimed"] is False


def test_terminal_denominator_validation_blocks_fake_empty_success():
    bad = validate_terminal_denominators_v11(
        {
            "critic_resolution_ratio": {
                "numerator": 0,
                "denominator": 0,
                "value": 1.0,
                "status": "NOT_APPLICABLE",
            },
            "full_calibration_completion_ratio": {
                "numerator": 10,
                "denominator": 80,
                "value": 0.125,
                "status": "VALID",
            },
        }
    )
    assert bad["terminal_denominator_validation"] == "FAIL"
    assert "critic_resolution_ratio:zero_denominator_has_value" in bad["issues"]
    assert "full_calibration_completion_ratio:incomplete_without_status" in bad["issues"]


def test_lesson_gate_enforcement_no_policy_effect_before_verified():
    incomplete = apply_lesson_gate_v11(
        terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        quality_gates_passed=False,
        proposed_policy_effect_lesson_count=9,
    )
    assert incomplete["policy_effect_lesson_allowed"] is False
    assert incomplete["new_policy_effect_lesson_count"] == 0

    fixture = apply_lesson_gate_v11(
        terminal_status="VERIFIED",
        quality_gates_passed=True,
        proposed_policy_effect_lesson_count=9,
        fixture_label=CONTROL_FIXTURE_LABEL,
    )
    assert fixture["policy_effect_lesson_allowed"] is False
    assert fixture["lesson_prevention_blocked_reason"] == CONTROL_FIXTURE_LABEL
    assert fixture["new_policy_effect_lesson_count"] == 0


def test_runner_separates_real_checkpoint_progress_from_fixture_results():
    root = Path(__file__).resolve().parents[1]
    script = root / "tools/research/run_reflection_v23_adjudication_v11.py"
    env = dict(os.environ)
    env["NEXUS_V11_COPY_REAL_CHECKPOINT"] = "0"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    out = json.loads(proc.stdout)
    assert out["fixture_result_label"] == CONTROL_FIXTURE_LABEL
    assert out["real_checkpoint_progress"]["progress_source"] == "CHECKPOINT_FILE"
    assert out["real_checkpoint_progress"]["rebuilt_from_summary_metrics"] is False
    assert out["fixture_only"] is True
    assert out["real_ai_quality_claimed"] is False
    assert out["new_policy_effect_lesson_count"] == 0
