"""Founder R3 E/F remediation — two-pass adversarial negative tests."""
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

from tools.review.r3_ef_remediation.probes import (
    REMEDIATION_FINDING_IDS,
    probe_checkpoint_counter_drift,
    probe_critic_before_reasoner,
    probe_founder_auth_spoof,
    probe_lesson_gate_still_hard,
    probe_nested_future_timestamp,
    probe_oos_seal_regeneration,
    probe_promotion_still_blocked,
    run_pass1,
    run_pass2,
)
from tools.review.r3_ef_remediation.run_r3_ef_remediation_verification import ARTIFACT_REL


def test_r3_e_checkpoint_counter_drift_fixed():
    finding = probe_checkpoint_counter_drift()
    assert finding["status"] == "PASS"
    assert finding["evidence"]["integrity_status"] == "COUNTER_DRIFT"
    assert finding["evidence"]["groq_success_count_used"] != 999
    assert finding["evidence"]["quality_gates_passed"] is False


def test_r3_e_critic_before_reasoner_fixed():
    finding = probe_critic_before_reasoner()
    assert finding["status"] == "PASS"
    assert finding["evidence"]["critic_dispatch_allowed"] is False
    assert finding["evidence"]["critic_reason"] == "REASONER_SUCCESS_REQUIRED"


def test_r3_f_nested_future_timestamp_fixed():
    finding = probe_nested_future_timestamp()
    assert finding["status"] == "PASS"
    assert finding["evidence"]["allowed"] is False
    assert finding["evidence"]["violation_count"] >= 3


def test_r3_f_oos_seal_regeneration_fixed():
    finding = probe_oos_seal_regeneration()
    assert finding["status"] == "PASS"
    assert finding["evidence"]["seal2_status"] == "SEAL_REGENERATION_REJECTED_RESERVED_MUTATION"


def test_r3_f_founder_auth_spoof_fixed():
    finding = probe_founder_auth_spoof()
    assert finding["status"] == "PASS"
    assert finding["evidence"]["spoof_rejected"] is True
    assert finding["evidence"]["promote_consults_founder_gate"] is True
    assert finding["evidence"]["promote_allowed"] is False


def test_lesson_gate_not_weakened():
    finding = probe_lesson_gate_still_hard()
    assert finding["status"] == "PASS"


def test_promotion_blocked_ready_preserved():
    finding = probe_promotion_still_blocked()
    assert finding["status"] == "PASS"


def test_two_pass_remediation_stable_and_clears_integration_block():
    pass1 = run_pass1()
    pass2 = run_pass2(pass1)
    assert pass1["fail_count"] == 0
    assert pass2["stability"]["unstable_count"] == 0
    assert pass2["recommendation"] == "PASS_WITH_NOTES"
    assert pass2["critical_open"] == []
    assert pass2["high_open"] == []
    for fid in REMEDIATION_FINDING_IDS:
        assert pass2["remediation_status"][fid] == "FIXED", fid


def test_runner_writes_immutable_artifacts():
    script = ROOT / "tools/review/r3_ef_remediation/run_r3_ef_remediation_verification.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    out = json.loads(proc.stdout)
    assert out["recommendation"] == "PASS_WITH_NOTES"
    assert all(v == "FIXED" for v in out["remediation_status"].values())
    artifact_dir = ROOT / ARTIFACT_REL
    for name in (
        "status.json",
        "summary.json",
        "findings.json",
        "recommendation.json",
        "pass1_adversarial.json",
        "pass2_verification.json",
        "remediation_matrix.json",
    ):
        path = artifact_dir / name
        assert path.is_file(), path
        json.loads(path.read_text(encoding="utf-8"))
