"""Two-pass adversarial review for V14-G Lesson Prevention Proof V2."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_lesson_prevention_v2.constants import HARD_BANS, SCHEMA_TWO_PASS


def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def adversarial_pass1(bundle: dict[str, Any]) -> dict[str, Any]:
    """Pass 1: hunt for false claims, gate bypasses, and classification bugs."""
    findings: list[dict[str, str]] = []
    gate = bundle.get("real_gate") or {}
    mech = bundle.get("mechanics") or {}
    ckpt = bundle.get("checkpoint") or {}

    if gate.get("REAL_LESSON_PREVENTION_STATUS") != "BLOCKED" and not ckpt.get("V2_3_complete"):
        findings.append(
            {
                "id": "P1_REAL_STATUS_NOT_BLOCKED",
                "severity": "critical",
                "detail": "REAL_LESSON_PREVENTION_STATUS must be BLOCKED while V2.3 incomplete",
            }
        )
    if mech.get("misrepresented_as_real_learning"):
        findings.append(
            {
                "id": "P1_FIXTURE_AS_REAL",
                "severity": "critical",
                "detail": "fixture mechanics misrepresented as real learning",
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
    matrix = (mech.get("classification_matrix") or {})
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
                "detail": "fixture matrix missing required process classes",
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
    # Ban inventory must be present
    missing_bans = [b for b in HARD_BANS if b not in (bundle.get("hard_bans") or [])]
    if missing_bans:
        findings.append(
            {
                "id": "P1_HARD_BAN_INVENTORY",
                "severity": "high",
                "detail": f"missing hard bans: {','.join(missing_bans[:3])}",
            }
        )

    critical = [f for f in findings if f["severity"] == "critical"]
    return {
        "pass": 1,
        "findings": findings,
        "critical_count": len(critical),
        "pass_ok": len(critical) == 0 and mech.get("mechanics_proof_status") == "PASS",
        "digest": _digest(
            {
                "gate_status": gate.get("REAL_LESSON_PREVENTION_STATUS"),
                "mech": mech.get("mechanics_proof_status"),
                "findings": [f["id"] for f in findings],
            }
        ),
    }


def adversarial_pass2(bundle: dict[str, Any], pass1: dict[str, Any]) -> dict[str, Any]:
    """Pass 2: re-verify after remediation; residuals must be empty for criticals."""
    recheck = adversarial_pass1(bundle)
    residuals = [
        f
        for f in recheck["findings"]
        if f["severity"] == "critical"
        or f["id"] in {x["id"] for x in pass1.get("findings") or []}
    ]
    # After remediation, only accept empty critical residuals.
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
        "pass_ok": len(critical_residuals) == 0 and bundle.get("mechanics", {}).get("mechanics_proof_status") == "PASS",
        "digest": recheck["digest"],
        "pass1_digest": pass1.get("digest"),
        "digests_match": recheck["digest"] == pass1.get("digest"),
        "note": "residuals_list_is_critical_only",
        "pass1_noncritical_echo": [f["id"] for f in residuals if f["severity"] != "critical"],
    }


def run_two_pass(bundle: dict[str, Any]) -> dict[str, Any]:
    p1 = adversarial_pass1(bundle)
    # Remediation is structural in-code; Pass 2 re-evaluates the same corrected bundle.
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
