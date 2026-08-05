"""Founder R3 adversarial tests — Reflection V2.3 + Point-in-Time Qualification."""
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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.review.r3_reflection_qualification.origin_loader import (
    ORIGIN_PIT_ROOT,
    ORIGIN_REFLECTION_ROOT,
    REVIEW_ARTIFACT_REL,
)
from tools.review.r3_reflection_qualification.probes import (
    probe_429_as_quality_failure,
    probe_checkpoint_counter_drift,
    probe_completed_case_replay,
    probe_critic_before_reasoner,
    probe_founder_auth_spoof,
    probe_lesson_while_incomplete,
    probe_nested_future_timestamp,
    probe_oos_seal_regeneration,
    probe_promotion_blocking,
    probe_undetermined_process_migration,
    run_pass1,
    run_pass2,
)
from tools.review.r3_reflection_qualification.origin_loader import (
    load_pit_namespace,
    load_reflection_namespace,
)


def test_origin_worktrees_present():
    assert ORIGIN_REFLECTION_ROOT.is_dir(), ORIGIN_REFLECTION_ROOT
    assert ORIGIN_PIT_ROOT.is_dir(), ORIGIN_PIT_ROOT
    assert (ORIGIN_REFLECTION_ROOT / "backend/nexus_reflection/adjudication_v11/core.py").is_file()
    assert (ORIGIN_PIT_ROOT / "backend/nexus_qualification/pit_v11/infrastructure.py").is_file()


def test_adversarial_429_not_quality_failure():
    R = load_reflection_namespace()
    finding = probe_429_as_quality_failure(R)
    assert finding["status"] == "PASS"
    assert finding["evidence"]["quality_neutral_transport"] is True


def test_adversarial_critic_before_reasoner_is_open_gap():
    R = load_reflection_namespace()
    finding = probe_critic_before_reasoner(R)
    assert finding["status"] == "FAIL"
    assert finding["severity"] == "HIGH"
    assert finding["evidence"]["critic_dispatch_allowed"] is True


def test_adversarial_completed_case_replay_blocked():
    R = load_reflection_namespace()
    finding = probe_completed_case_replay(R)
    assert finding["status"] == "PASS"
    assert finding["evidence"]["second_reason"] == "SUCCESSFUL_CASE_DEDUP"


def test_adversarial_checkpoint_counter_drift_undetected():
    R = load_reflection_namespace()
    finding = probe_checkpoint_counter_drift(R)
    assert finding["status"] == "FAIL"
    assert finding["severity"] == "CRITICAL"
    assert finding["evidence"]["checksum_ok_despite_drift"] is True
    assert finding["evidence"]["groq_success_count_used"] == 999


def test_adversarial_undetermined_process_not_lost():
    R = load_reflection_namespace()
    finding = probe_undetermined_process_migration(R)
    assert finding["status"] == "PASS"
    assert finding["evidence"]["migrated"] == "UNDETERMINED"


def test_adversarial_lesson_blocked_while_incomplete():
    R = load_reflection_namespace()
    finding = probe_lesson_while_incomplete(R)
    assert finding["status"] == "PASS"
    assert finding["evidence"]["incomplete"]["new_policy_effect_lesson_count"] == 0


def test_adversarial_nested_future_timestamp_bypasses_exclusion():
    infra = load_pit_namespace()
    finding = probe_nested_future_timestamp(infra)
    assert finding["status"] == "FAIL"
    assert finding["severity"] == "CRITICAL"
    assert finding["evidence"]["allowed"] is True


def test_adversarial_oos_seal_regeneration():
    infra = load_pit_namespace()
    finding = probe_oos_seal_regeneration(infra)
    assert finding["status"] == "FAIL"
    assert finding["severity"] == "CRITICAL"
    assert finding["evidence"]["seal_changed"] is True


def test_adversarial_founder_auth_spoof_decoupled_from_promotion():
    infra = load_pit_namespace()
    finding = probe_founder_auth_spoof(infra)
    assert finding["status"] == "FAIL"
    assert finding["severity"] == "HIGH"
    assert finding["evidence"]["spoofed_authorized"] is True
    assert finding["evidence"]["promote_consults_founder_gate"] is False


def test_adversarial_promotion_remains_blocked():
    infra = load_pit_namespace()
    finding = probe_promotion_blocking(infra)
    assert finding["status"] == "PASS"


def test_two_pass_review_is_stable_and_blocks_integration():
    pass1 = run_pass1()
    pass2 = run_pass2(pass1)
    assert pass1["fail_count"] >= 4
    assert pass2["stability"]["unstable_count"] == 0
    assert pass2["recommendation"] == "BLOCK_INTEGRATION"
    assert "R3-E-CHECKPOINT-COUNTER-DRIFT" in pass2["critical_open"]
    assert "R3-F-NESTED-FUTURE-TIMESTAMP" in pass2["critical_open"]
    assert "R3-F-OOS-SEAL-REGENERATION" in pass2["critical_open"]


def test_runner_writes_immutable_artifacts():
    script = ROOT / "tools/review/r3_reflection_qualification/run_r3_reflection_qualification_review.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode in {0, 2}, proc.stderr
    out = json.loads(proc.stdout)
    assert out["recommendation"] == "BLOCK_INTEGRATION"
    artifact_dir = ROOT / REVIEW_ARTIFACT_REL
    for name in (
        "status.json",
        "summary.json",
        "findings.json",
        "recommendation.json",
        "pass1_adversarial.json",
        "pass2_verification.json",
    ):
        path = artifact_dir / name
        assert path.is_file(), path
        json.loads(path.read_text(encoding="utf-8"))
