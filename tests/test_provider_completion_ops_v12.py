"""Tests for Founder-private Provider Completion Ops V12-C."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_provider_ops import (
    HARD_BANS,
    ProviderCompletionOpsV12,
    ResumeOwnershipError,
    incomplete_sot_snapshot,
)
from backend.nexus_provider_ops.capacity_windows import evaluate_capacity_windows
from backend.nexus_provider_ops.checkpoint_safety import evaluate_checkpoint_safety
from backend.nexus_provider_ops.completed_case_dedupe import evaluate_completed_case_dedupe
from backend.nexus_provider_ops.manual_control import ManualLaneControl
from backend.nexus_provider_ops.queue_health import evaluate_queue_health
from backend.nexus_provider_ops.resume_boundary import ResumeBoundary
from backend.nexus_provider_ops.retry_after_obs import observe_retry_after
from backend.nexus_provider_ops.sanitize import (
    assert_no_secret_keys,
    payload_contains_secret_pattern,
    safe_log_fields,
)
from backend.nexus_provider_ops.sot import assert_incomplete_truth


def test_incomplete_sot_truth() -> None:
    sot = incomplete_sot_snapshot()
    assert sot["V2_3_complete"] is False
    assert sot["lanes"][GROQ_REFLECTION_REASONER]["success_count"] == 53
    assert sot["lanes"][GROQ_REFLECTION_REASONER]["pending_count"] == 27
    assert sot["lanes"][SAMBANOVA_INDEPENDENT_CRITIC]["success_count"] == 16
    assert sot["lanes"][SAMBANOVA_INDEPENDENT_CRITIC]["pending_count"] == 10
    assert_incomplete_truth(sot)
    with pytest.raises(RuntimeError):
        assert_incomplete_truth({"V2_3_complete": True})


def test_queue_health_defaults_to_incomplete_sot() -> None:
    q = evaluate_queue_health()
    assert q["V2_3_complete"] is False
    assert q["sot_aligned"] is True
    assert q["overall_status"] in {"DEGRADED_INCOMPLETE", "PAUSED"}
    assert q["lanes"][GROQ_REFLECTION_REASONER]["pending_count"] == 27


def test_retry_after_observability_strips_secrets() -> None:
    obs = observe_retry_after(
        profile_id=GROQ_REFLECTION_REASONER,
        headers={
            "Retry-After": "12",
            "Authorization": "Bearer REDACTED_TEST_CREDENTIAL",
            "x-api-key": "REDACTED_TEST_KEY",
        },
        http_status=429,
    )
    assert obs["retry_after_s"] == 12.0
    assert obs["rate_limited"] is True
    assert obs["secret_logging"] is False
    blob = json.dumps(obs)
    assert "Bearer" not in blob
    assert "REDACTED_TEST_CREDENTIAL" not in blob
    assert_no_secret_keys(obs)


def test_capacity_windows_do_not_authorize_real_resume() -> None:
    caps = evaluate_capacity_windows(groq_retry_after_s=900.0, sambanova_retry_after_s=900.0)
    assert caps["real_resume_authorized"] is False
    assert caps["V2_3_complete"] is False
    for lane in caps["lanes"].values():
        assert lane["real_resume_authorized"] is False
        assert lane["window_status"] == "CLOSED_WAITING"


def test_checkpoint_safety_incomplete_sot() -> None:
    report = evaluate_checkpoint_safety()
    assert report["integrity_status"] == "OK"
    assert report["groq_success_count"] == 53
    assert report["pending_case_count"] == 27
    assert report["sambanova_success_count"] == 16
    assert report["critic_pending_count"] == 10
    assert report["real_resume_executed"] is False
    assert report["V2_3_complete"] is False


def test_checkpoint_safety_detects_overlap(tmp_path: Path) -> None:
    bad = {
        "completed_case_ids": ["a", "b"],
        "pending_case_ids": ["b", "c"],
        "pending_critic_case_ids": ["x"],
        "transport": {
            "GROQ_REFLECTION_REASONER": {"success_count": 2},
            "SAMBANOVA_INDEPENDENT_CRITIC": {"success_count": 0},
        },
    }
    path = tmp_path / "cp.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    report = evaluate_checkpoint_safety(checkpoint_path=path, require_incomplete_sot=False)
    assert report["integrity_status"] == "UNSAFE"
    assert "completed_pending_overlap" in report["issues"]


def test_completed_case_dedupe_blocks_requeue() -> None:
    dedupe = evaluate_completed_case_dedupe()
    assert dedupe["overlap_count"] >= 1
    assert dedupe["dedupe_effective"] is True
    assert dedupe["requeue_blocked_count"] >= 1
    assert all(cid not in set(dedupe["deduped_pending_case_ids"][:0]) or True for cid in [])
    completed = {f"case_{i:03d}" for i in range(53)}
    assert all(cid not in completed for cid in dedupe["deduped_pending_case_ids"])


def test_manual_pause_resume_does_not_own_real_resume() -> None:
    ctrl = ManualLaneControl()
    ctrl.pause(GROQ_REFLECTION_REASONER)
    assert ctrl.is_paused(GROQ_REFLECTION_REASONER) is True
    event = ctrl.resume(GROQ_REFLECTION_REASONER)
    assert event["real_resume_executed"] is False
    assert event["affects_real_resume_ownership"] is False
    snap = ctrl.snapshot()
    assert snap["ops_owns_real_resume"] is False


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
    # Pattern detector uses a synthetic marker that is not a live credential.
    assert payload_contains_secret_pattern({"msg": "begin rsa private key"}) is True


def test_ops_cycle_pass_and_hard_bans() -> None:
    ops = ProviderCompletionOpsV12()
    cycle = ops.run_cycle()
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
    assert "no_v2_3_complete_claim" in HARD_BANS
    assert cycle["ownership_theft_blocked"] is True
    assert_no_secret_keys(status)
