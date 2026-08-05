"""Tests for Founder-private Reflection V2.3 Completion Ops V13-B."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_v23_completion_ops import (
    HARD_BANS,
    ResumeOwnershipError,
    V23CompletionOpsV13,
    incomplete_sot_snapshot,
)
from backend.nexus_v23_completion_ops.atomic_checkpoint import (
    atomic_write_checkpoint,
    validate_semantic_counters,
)
from backend.nexus_v23_completion_ops.dedupe_critic import (
    evaluate_completed_case_dedupe,
    evaluate_critic_ordering,
)
from backend.nexus_v23_completion_ops.gates import (
    evaluate_lesson_quality_gates,
    evaluate_terminal_denominators_ops,
)
from backend.nexus_v23_completion_ops.pause_resume import SafePauseResume
from backend.nexus_v23_completion_ops.preflight import fixture_provider_preflight, run_lane_preflights
from backend.nexus_v23_completion_ops.provider_windows import (
    evaluate_provider_windows,
    report_capacity_status,
)
from backend.nexus_v23_completion_ops.queue_health import evaluate_queue_health
from backend.nexus_v23_completion_ops.resume_boundary import ResumeBoundary
from backend.nexus_v23_completion_ops.retry_quota_obs import observe_retry_and_quota
from backend.nexus_v23_completion_ops.sanitize import (
    assert_no_secret_keys,
    payload_contains_secret_pattern,
    safe_log_fields,
)
from backend.nexus_v23_completion_ops.sot import assert_incomplete_truth, synthetic_incomplete_checkpoint


def test_incomplete_sot_truth_matches_checkpoint_approx() -> None:
    sot = incomplete_sot_snapshot(verify_checkpoint=True)
    assert sot["V2_3_complete"] is False
    groq = sot["lanes"][GROQ_REFLECTION_REASONER]
    sn = sot["lanes"][SAMBANOVA_INDEPENDENT_CRITIC]
    assert groq["success_count"] == 53
    assert groq["pending_count"] == 27
    assert sn["success_count"] == 16
    assert sn["pending_count"] == 10
    assert_incomplete_truth(sot)
    with pytest.raises(RuntimeError):
        assert_incomplete_truth({"V2_3_complete": True})


def test_provider_preflight_fixture_only_no_secrets() -> None:
    pf = fixture_provider_preflight(
        GROQ_REFLECTION_REASONER,
        headers={
            "Retry-After": "60",
            "x-ratelimit-reset": "90",
            "Authorization": "Bearer REDACTED_TEST_CREDENTIAL",
        },
    )
    assert pf["real_provider_call_executed"] is False
    assert pf["mode"] == "SANITIZED_FIXTURE"
    assert pf["retry_after_s"] == 60.0
    assert pf["quota_reset_s"] == 90.0
    blob = json.dumps(pf)
    assert "Bearer" not in blob
    assert "REDACTED_TEST_CREDENTIAL" not in blob
    lanes = run_lane_preflights()
    assert lanes["real_provider_call_executed"] is False
    assert lanes["any_mass_batch_blocked"] is True


def test_queue_health_and_retry_quota_visibility() -> None:
    q = evaluate_queue_health(verify_checkpoint=False)
    assert q["V2_3_complete"] is False
    assert q["independent_queues"] is True
    assert q["overall_status"] in {"DEGRADED_INCOMPLETE", "PAUSED"}
    obs = observe_retry_and_quota(
        profile_id=SAMBANOVA_INDEPENDENT_CRITIC,
        headers={"Retry-After": "12", "x-ratelimit-reset": "45", "x-api-key": "REDACTED"},
        http_status=429,
    )
    assert obs["retry_after_s"] == 12.0
    assert obs["quota_reset_visible"] is True
    assert obs["quota_reset_s"] == 45.0
    assert "x-api-key" not in (obs.get("headers_observed") or {})
    assert_no_secret_keys(obs)


def test_independent_provider_windows_and_capacity_status() -> None:
    wins = evaluate_provider_windows(
        groq_quota_reset_s=900.0,
        sambanova_quota_reset_s=1200.0,
        verify_checkpoint=False,
    )
    assert wins["independent_provider_windows"] is True
    assert wins["real_resume_authorized"] is False
    g = wins["lanes"][GROQ_REFLECTION_REASONER]
    s = wins["lanes"][SAMBANOVA_INDEPENDENT_CRITIC]
    assert g["window_open_in_s"] != s["window_open_in_s"]
    cap = report_capacity_status(wins)
    assert cap["overall_capacity_status"] == "INCOMPLETE_PROVIDER_CAPACITY"
    assert cap["real_resume_authorized"] is False
    assert cap["V2_3_complete"] is False


def test_safe_pause_resume_does_not_own_real_resume() -> None:
    ctrl = SafePauseResume()
    ctrl.pause(GROQ_REFLECTION_REASONER)
    assert ctrl.is_paused(GROQ_REFLECTION_REASONER) is True
    event = ctrl.resume(GROQ_REFLECTION_REASONER)
    assert event["real_resume_executed"] is False
    assert event["affects_real_resume_ownership"] is False
    snap = ctrl.snapshot()
    assert snap["ops_owns_real_resume"] is False


def test_atomic_checkpoint_and_semantic_counters(tmp_path: Path) -> None:
    fixture = synthetic_incomplete_checkpoint()
    path = tmp_path / "cp.json"
    report = atomic_write_checkpoint(path, fixture)
    assert report["atomic_replace"] is True
    assert path.is_file()
    assert report["tmp_cleaned"] is True
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    counters = validate_semantic_counters(reloaded)
    assert counters["ok"] is True
    assert counters["groq_success_count"] == 53
    assert counters["critic_success_count"] == 16
    assert counters["fixture_sot_aligned"] is True


def test_semantic_counters_detect_drift() -> None:
    bad = synthetic_incomplete_checkpoint()
    bad["transport"][GROQ_REFLECTION_REASONER]["success_count"] = 99
    counters = validate_semantic_counters(bad)
    assert counters["ok"] is False
    assert counters["refused_inflated_counter"] is True


def test_completed_case_dedupe_and_critic_ordering() -> None:
    dedupe = evaluate_completed_case_dedupe()
    assert dedupe["overlap_count"] >= 1
    assert dedupe["dedupe_effective"] is True
    assert dedupe["requeue_blocked_count"] >= 1
    completed = {f"case_{i:03d}" for i in range(53)}
    assert all(cid not in completed for cid in dedupe["deduped_pending_case_ids"])
    critic = evaluate_critic_ordering()
    assert critic["order_only_after_reasoner_success"] is True
    assert critic["premature_blocked_count"] >= 1
    assert all(
        row["transport_status"] == "CRITIC_BEFORE_REASONER_BLOCKED"
        for row in critic["premature_critic_blocked"]
    )


def test_terminal_denominator_and_lesson_gates_while_incomplete() -> None:
    terminal = evaluate_terminal_denominators_ops()
    assert terminal["quality_eval_blocked_while_incomplete"] is True
    assert terminal["V2_3_complete"] is False
    zero = terminal["zero_denominator_probe"]
    assert zero["terminal_denominator_validation"] == "PASS"
    gates = evaluate_lesson_quality_gates()
    assert gates["policy_effect_blocked"] is True
    assert gates["new_policy_effect_lesson_count"] == 0
    assert gates["quality_eval_allowed"] is False


def test_resume_boundary_blocks_ownership_theft() -> None:
    boundary = ResumeBoundary()
    req = boundary.request_real_resume(reason="test")
    assert req["allowed"] is False
    with pytest.raises(ResumeOwnershipError):
        boundary.execute_real_resume(fn=lambda: "stolen")
    snap = boundary.snapshot()
    assert snap["ops_owns_real_resume"] is False
    assert snap["real_resume_executed_by_ops"] is False
    assert snap["blocked_attempt_count"] >= 2


def test_safe_log_fields_strips_forbidden_keys() -> None:
    cleaned = safe_log_fields({"ok": True, "api_key": "secret", "nested": {"token": "x", "n": 1}})
    assert "api_key" not in cleaned
    assert "token" not in cleaned["nested"]
    assert cleaned["nested"]["n"] == 1
    assert_no_secret_keys(cleaned)
    assert payload_contains_secret_pattern({"msg": "begin rsa private key"}) is True


def test_ops_cycle_pass_and_hard_bans(tmp_path: Path) -> None:
    ops = V23CompletionOpsV13(root=tmp_path)
    cycle = ops.run_cycle(fixture_root=tmp_path / "fixtures", verify_checkpoint=False)
    status = ops.status_from_cycle(cycle, secret_leak_count=0)
    assert status["status"] == "PASS"
    assert status["V2_3_complete"] is False
    assert status["ops_owns_real_resume"] is False
    assert status["real_resume_executed_by_ops"] is False
    assert status["groq_success_count"] == 53
    assert status["groq_pending_count"] == 27
    assert status["sambanova_success_count"] == 16
    assert status["sambanova_pending_count"] == 10
    assert "no_real_provider_resume_ownership_theft" in HARD_BANS
    assert "no_policy_effect_lessons_while_incomplete" in HARD_BANS
    assert "no_quality_eval_before_complete_denominators" in HARD_BANS
    assert "no_v2_3_complete_claim" in HARD_BANS
    assert cycle["ownership_theft_blocked"] is True
    assert cycle["background_agent_sanitized_fixtures_only"] is True
    assert_no_secret_keys(status)
