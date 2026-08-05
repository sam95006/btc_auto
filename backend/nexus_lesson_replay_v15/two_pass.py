"""Two-pass adversarial review for V15-I Reflection and Lesson Replay Lab."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_lesson_replay_v15.constants import HARD_BANS, SCHEMA_TWO_PASS
from backend.nexus_lesson_replay_v15.hard_bans import (
    HardBanViolation,
    refuse_auto_integrate,
    refuse_exchange_write,
    refuse_fixture_as_real_policy_effect,
    refuse_mainnet_real_money,
    refuse_real_lesson_prevention_while_incomplete,
    refuse_status_json_lane_artifact,
)


def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _probe_refuse_apis() -> dict[str, Any]:
    probes = [
        ("refuse_exchange_write", refuse_exchange_write),
        ("refuse_mainnet_real_money", refuse_mainnet_real_money),
        ("refuse_auto_integrate", refuse_auto_integrate),
        ("refuse_fixture_as_real_policy_effect", refuse_fixture_as_real_policy_effect),
        ("refuse_real_lesson_prevention_while_incomplete", refuse_real_lesson_prevention_while_incomplete),
        ("refuse_status_json_lane_artifact", refuse_status_json_lane_artifact),
    ]
    raised = 0
    for _name, fn in probes:
        try:
            fn()
        except HardBanViolation:
            raised += 1
    return {
        "probe_count": len(probes),
        "raised_count": raised,
        "all_raised": raised == len(probes),
    }


def adversarial_pass1(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pass 1: hunt for false claims, gate bypasses, and classification bugs."""
    findings: list[dict[str, str]] = []
    gate = bundle.get("real_gate") or {}
    lab = bundle.get("replay_lab") or {}
    ckpt = bundle.get("checkpoint") or {}

    if gate.get("REAL_LESSON_PREVENTION_STATUS") != "BLOCKED" and not ckpt.get("V2_3_complete"):
        findings.append(
            {
                "id": "P1_REAL_STATUS_NOT_BLOCKED",
                "severity": "critical",
                "detail": "REAL_LESSON_PREVENTION_STATUS must be BLOCKED while V2.3 incomplete",
            }
        )
    if lab.get("misrepresented_as_real_learning") or lab.get("fixture_as_real_policy_effect_proof"):
        findings.append(
            {
                "id": "P1_FIXTURE_AS_REAL",
                "severity": "critical",
                "detail": "fixture/replay misrepresented as real learning or policy-effect proof",
            }
        )
    if int(gate.get("new_policy_effect_lesson_count") or 0) != 0 and not ckpt.get("V2_3_complete"):
        findings.append(
            {
                "id": "P1_POLICY_LESSON_WHILE_INCOMPLETE",
                "severity": "critical",
                "detail": "policy-effect lesson emitted while V2.3 incomplete",
            }
        )
    matrix = (lab.get("classification_matrix") or {}).get("combined") or {}
    if not matrix.get("loss_is_not_automatic_bad_process", False):
        findings.append(
            {
                "id": "P1_LOSS_AUTO_BAD",
                "severity": "critical",
                "detail": "loss auto-mapped to BAD_PROCESS",
            }
        )
    if not all((matrix.get("required_classes_present") or {}).values()):
        findings.append(
            {
                "id": "P1_CLASS_COVERAGE",
                "severity": "high",
                "detail": "replay matrix missing required process classes",
            }
        )
    fix_ok = ((lab.get("classification_matrix") or {}).get("labeled_fixtures") or {}).get(
        "clearly_labelled", False
    )
    if not fix_ok:
        findings.append(
            {
                "id": "P1_FIXTURE_LABELS",
                "severity": "critical",
                "detail": "fixture controls not clearly labelled",
            }
        )
    if int(lab.get("historical_simulated_trade_count") or 0) < 1:
        findings.append(
            {
                "id": "P1_NO_SIM_TRADES",
                "severity": "critical",
                "detail": "no historical simulated completed trades in replay lab",
            }
        )
    if int(bundle.get("secret_leak_count") or 0) > 0:
        findings.append(
            {
                "id": "P1_SECRET_LEAK",
                "severity": "critical",
                "detail": "secret leak detected in artifacts",
            }
        )
    if bundle.get("auto_integrate") or bundle.get("pr27_merged"):
        findings.append(
            {
                "id": "P1_AUTO_INTEGRATE",
                "severity": "critical",
                "detail": "auto-integrate or PR27 merge attempted",
            }
        )
    if ckpt.get("mutated"):
        findings.append(
            {
                "id": "P1_CHECKPOINT_MUTATION",
                "severity": "critical",
                "detail": "canonical checkpoint was mutated",
            }
        )
    if bundle.get("wrote_status_json"):
        findings.append(
            {
                "id": "P1_STATUS_JSON",
                "severity": "critical",
                "detail": "lane wrote banned *_status.json artifact",
            }
        )
    missing_bans = [b for b in HARD_BANS if b not in (bundle.get("hard_bans") or [])]
    if missing_bans:
        findings.append(
            {
                "id": "P1_HARD_BAN_INVENTORY",
                "severity": "high",
                "detail": f"missing hard bans: {','.join(missing_bans[:3])}",
            }
        )

    refuse = _probe_refuse_apis()
    if not refuse["all_raised"]:
        findings.append(
            {
                "id": "P1_REFUSE_API",
                "severity": "critical",
                "detail": "hard-ban refuse APIs did not all raise",
            }
        )

    critical = [f for f in findings if f["severity"] == "critical"]
    return {
        "pass": 1,
        "findings": findings,
        "critical_count": len(critical),
        "pass_ok": len(critical) == 0 and lab.get("replay_lab_status") == "PASS",
        "refuse_api_probes": refuse,
        "digest": _digest(
            {
                "gate_status": gate.get("REAL_LESSON_PREVENTION_STATUS"),
                "lab": lab.get("replay_lab_status"),
                "findings": [f["id"] for f in findings],
            }
        ),
    }


def adversarial_pass2(bundle: dict[str, Any], pass1: dict[str, Any]) -> dict[str, Any]:
    """Pass 2: re-verify after remediation; critical residuals must be empty."""
    recheck = adversarial_pass1(bundle)
    critical_residuals = [f for f in recheck["findings"] if f["severity"] == "critical"]
    fixed = [
        f["id"]
        for f in (pass1.get("findings") or [])
        if f["id"] not in {r["id"] for r in recheck["findings"]}
    ]
    return {
        "pass": 2,
        "findings": recheck["findings"],
        "critical_count": len(critical_residuals),
        "findings_fixed": fixed,
        "remaining_residuals": [f["id"] for f in critical_residuals],
        "pass_ok": len(critical_residuals) == 0
        and bundle.get("replay_lab", {}).get("replay_lab_status") == "PASS",
        "digest": recheck["digest"],
        "pass1_digest": pass1.get("digest"),
        "digests_match": recheck["digest"] == pass1.get("digest"),
        "refuse_api_probes": recheck.get("refuse_api_probes"),
        "note": "residuals_list_is_critical_only",
    }


def run_two_pass(bundle: dict[str, Any]) -> dict[str, Any]:
    p1 = adversarial_pass1(bundle)
    p2 = adversarial_pass2(bundle, p1)
    return {
        "schema": SCHEMA_TWO_PASS,
        "pass_count": 2,
        "pass1": p1,
        "pass2": p2,
        "two_pass_ok": bool(p1["pass_ok"] and p2["pass_ok"]),
        "digests": [p1.get("digest"), p2.get("digest")],
        "passes_match": bool(p2.get("digests_match")),
    }
