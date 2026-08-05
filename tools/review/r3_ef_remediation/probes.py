"""Adversarial negative probes for R3 E/F remediation verification.

Loads local worktree modules (not origin review worktrees). After remediation,
the five R3 BLOCK findings must PASS; Lesson gate and PROMOTION_BLOCKED_READY
remain hard.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_ai.profiles import GROQ_REFLECTION_REASONER, SAMBANOVA_INDEPENDENT_CRITIC
from backend.nexus_ai.scheduler import ProviderScheduler
from backend.nexus_qualification.pit_v11 import infrastructure as infra
from backend.nexus_reflection import checkpoint as ckpt
from backend.nexus_reflection import terminal_eval
from backend.nexus_reflection.adjudication_v11 import core as reflection_core
from backend.nexus_reflection.lesson_gate_v11 import apply_lesson_gate_v11


REMEDIATION_FINDING_IDS = (
    "R3-E-CHECKPOINT-COUNTER-DRIFT",
    "R3-F-NESTED-FUTURE-TIMESTAMP",
    "R3-F-OOS-SEAL-REGENERATION",
    "R3-E-CRITIC-BEFORE-REASONER",
    "R3-F-FOUNDER-AUTH-SPOOF",
)


def _finding(
    *,
    finding_id: str,
    severity: str,
    lane: str,
    title: str,
    status: str,
    detail: str,
    evidence: dict[str, Any],
    remediation: str,
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "lane": lane,
        "title": title,
        "status": status,
        "detail": detail,
        "evidence": evidence,
        "remediation": remediation,
    }


def probe_checkpoint_counter_drift() -> dict[str, Any]:
    sch = ProviderScheduler(sleep_fn=lambda _s: None)
    transport = sch.export_transport_for_checkpoint()
    transport[GROQ_REFLECTION_REASONER]["success_count"] = 80
    transport[GROQ_REFLECTION_REASONER]["attempt_count"] = 80
    state = {
        "schema": "blind_reflection_v23_checkpoint_v4",
        "schema_version": 4,
        "transport": transport,
        "case_ids": ["only_one"],
        "completed_case_ids": ["only_one"],
        "critic_case_ids": [],
        "critic_resolved_ids": [],
        "case_results": {},
    }
    state["integrity_checksum"] = ckpt.compute_integrity_checksum(state)
    drifted = deepcopy(state)
    drifted["transport"][GROQ_REFLECTION_REASONER]["success_count"] = 999
    drifted["integrity_checksum"] = ckpt.compute_integrity_checksum(drifted)
    probe = ckpt.detect_corruption(json.dumps(drifted))
    quality = terminal_eval.evaluate_terminal(drifted)
    # FIXED when drift is detected OR gate refuses inflated counter.
    drift_undetected = probe.get("ok") is True and int(quality.get("groq_success_count") or 0) == 999
    fixed = (
        probe.get("ok") is False
        and probe.get("checkpoint_integrity_status") == "COUNTER_DRIFT"
        and int(quality.get("groq_success_count") or 0) != 999
        and quality.get("V2_3_TERMINAL_STATUS") == "CHECKPOINT_COUNTER_DRIFT"
        and quality.get("quality_gates_passed") is False
    )
    return _finding(
        finding_id="R3-E-CHECKPOINT-COUNTER-DRIFT",
        severity="CRITICAL",
        lane="E",
        title="Checkpoint integrity ignores success_count vs completed-case drift",
        status="PASS" if fixed and not drift_undetected else "FAIL",
        detail=(
            "Remediation: detect_corruption fails closed on counter drift; "
            "evaluate_terminal refuses inflated success_count for ≥80 gate."
        ),
        evidence={
            "checksum_ok_despite_drift": probe.get("ok"),
            "integrity_status": probe.get("checkpoint_integrity_status"),
            "completed_case_count": len(drifted["completed_case_ids"]),
            "groq_success_count_used": quality.get("groq_success_count"),
            "terminal_status": quality.get("V2_3_TERMINAL_STATUS"),
            "quality_gates_passed": quality.get("quality_gates_passed"),
            "fixed": fixed,
        },
        remediation="Semantic counter invariants + refuse inflated terminal gate.",
    )


def probe_critic_before_reasoner() -> dict[str, Any]:
    sch = ProviderScheduler(sleep_fn=lambda _s: None)
    critic = reflection_core.record_provider_outcome(
        sch,
        profile_id=SAMBANOVA_INDEPENDENT_CRITIC,
        case_id="ADV_CRITIC_FIRST",
        prompt_hash="pc",
        schema_version="critic_v2_3",
        result_status="SUCCESS",
        response_payload={"critic_verdict": "AGREE_WITH_GROQ"},
    )
    order = reflection_core.build_critic_order(
        {
            "case_ids": ["ADV_CRITIC_FIRST"],
            "completed_case_ids": [],
            "critic_resolved_ids": [],
            "case_results": {},
        }
    )
    bypass = critic.get("dispatch_allowed") is True and critic.get("transport_status") == "SUCCESS"
    fixed = (
        critic.get("dispatch_allowed") is False
        and critic.get("reason") == "REASONER_SUCCESS_REQUIRED"
        and critic.get("transport_status") == "CRITIC_BEFORE_REASONER_BLOCKED"
        and order == []
    )
    return _finding(
        finding_id="R3-E-CRITIC-BEFORE-REASONER",
        severity="HIGH",
        lane="E",
        title="Critic can complete before Reasoner success",
        status="PASS" if fixed and not bypass else "FAIL",
        detail="Remediation: Critic dispatch gated on Reasoner SUCCESS for same case_id.",
        evidence={
            "critic_dispatch_allowed": critic.get("dispatch_allowed"),
            "critic_transport_status": critic.get("transport_status"),
            "critic_reason": critic.get("reason"),
            "critic_order_without_reasoner": order,
            "fixed": fixed,
        },
        remediation="Gate Critic begin_attempt on Reasoner SUCCESS.",
    )


def probe_nested_future_timestamp() -> dict[str, Any]:
    as_of = 1_700_000_000_000
    dataset = infra.synthetic_dataset_lineage(as_of_ms=as_of)
    nested = deepcopy(dataset)
    nested["records"][0]["evidence"] = {
        "bar_close_ts_ms": as_of + 86_400_000,
        "nested_available_as_of_ms": as_of + 1,
        "child": {"availability_timestamp_ms": as_of + 9},
    }
    result = infra.prove_future_data_exclusion(nested, as_of_ms=as_of)
    bypass = result.get("allowed") is True
    fixed = (
        result.get("allowed") is False
        and result.get("status") == "FUTURE_DATA_VIOLATION"
        and int(result.get("violation_count") or 0) >= 3
        and result.get("nested_scan") is True
    )
    return _finding(
        finding_id="R3-F-NESTED-FUTURE-TIMESTAMP",
        severity="CRITICAL",
        lane="F",
        title="Future timestamp hidden in nested evidence bypasses PIT exclusion",
        status="PASS" if fixed and not bypass else "FAIL",
        detail="Remediation: recursive nested evidence timestamp scan vs as_of.",
        evidence={
            "status": result.get("status"),
            "allowed": result.get("allowed"),
            "violation_count": result.get("violation_count"),
            "nested_keys": sorted(nested["records"][0]["evidence"].keys()),
            "fixed": fixed,
        },
        remediation="Recursively scan nested *_timestamp_ms / available_as_of_ms fields.",
    )


def probe_oos_seal_regeneration() -> dict[str, Any]:
    as_of = 1_700_000_000_000
    lineage = infra.OOSSealLineage()
    dataset = infra.synthetic_dataset_lineage(as_of_ms=as_of)
    regs = infra.synthetic_interval_registries(as_of_ms=as_of)
    checksums = infra.semantic_checksums(infra.synthetic_candidate_fixture(), dataset, "code-sha")
    seal1 = infra.build_oos_cryptographic_seal(regs, checksums, lineage_key="adv", lineage=lineage)
    old = regs["reserved"].intervals[0]
    regs["reserved"].intervals[0] = infra.IntervalRecord(
        old.interval_id,
        old.label,
        old.start_ms,
        old.end_ms + 86_400_000,
        old.category,
    )
    seal2 = infra.build_oos_cryptographic_seal(regs, checksums, lineage_key="adv", lineage=lineage)
    regenerated = (
        seal1.get("seal")
        and seal1["seal"] != seal2.get("seal")
        and seal1["status"] == "SEALED_NOT_CONSUMED"
        and seal2["status"] == "SEALED_NOT_CONSUMED"
    )
    fixed = (
        seal1["status"] == "SEALED_NOT_CONSUMED"
        and seal1.get("write_once") is True
        and seal2["status"] == "SEAL_REGENERATION_REJECTED_RESERVED_MUTATION"
        and seal2.get("allowed") is False
        and seal2.get("fail_closed") is True
        and seal2.get("seal") is None
    )
    return _finding(
        finding_id="R3-F-OOS-SEAL-REGENERATION",
        severity="CRITICAL",
        lane="F",
        title="OOS cryptographic seal can be regenerated after reserved-interval mutation",
        status="PASS" if fixed and not regenerated else "FAIL",
        detail="Remediation: write-once OOS seal lineage; mutation after seal fails closed.",
        evidence={
            "seal1": seal1.get("seal"),
            "seal2": seal2.get("seal"),
            "seal1_status": seal1.get("status"),
            "seal2_status": seal2.get("status"),
            "seal_changed": seal1.get("seal") != seal2.get("seal"),
            "fixed": fixed,
        },
        remediation="Persist first seal write-once; reject reserved-registry mutation regenerations.",
    )


def probe_founder_auth_spoof() -> dict[str, Any]:
    gate = infra.FounderAuthorizationGate()
    denied = gate.evaluate({"founder_authorization_token": "SPOOF_TOKEN", "scope": gate.required_scope})
    spoofed = dict(denied)
    spoofed["authorized"] = True
    sm = infra.PromotionStateMachine(founder_gate=gate)
    promote = sm.attempt_promote(spoofed)
    promote_default = sm.attempt_promote()
    spoof_check = gate.verify_bound_result(spoofed)
    coupling_missing = (
        spoofed["authorized"] is True
        and promote.get("allowed") is False
        and "founder" not in json.dumps(promote).lower()
    )
    fixed = (
        denied.get("authorized") is False
        and spoof_check.get("valid") is False
        and spoof_check.get("spoof_rejected") is True
        and promote.get("allowed") is False
        and promote.get("founder_auth_verified") is False
        and promote_default.get("allowed") is False
        and "founder" in json.dumps(promote).lower()
        and promote.get("reason") in {
            "FOUNDER_AUTH_SPOOF_REJECTED_PROMOTION_BLOCKED",
            "PROMOTION_BLOCKED_READY_V11_INFRASTRUCTURE_ONLY",
        }
    )
    return _finding(
        finding_id="R3-F-FOUNDER-AUTH-SPOOF",
        severity="HIGH",
        lane="F",
        title="Founder auth result is spoofable and decoupled from promotion gate",
        status="PASS" if fixed and not coupling_missing else "FAIL",
        detail="Remediation: auth_proof binding; attempt_promote consults and rejects spoof.",
        evidence={
            "evaluate_authorized": denied.get("authorized"),
            "evaluate_reason": denied.get("reason"),
            "spoofed_authorized": spoofed.get("authorized"),
            "spoof_rejected": spoof_check.get("spoof_rejected"),
            "promote_allowed": promote.get("allowed"),
            "promote_reason": promote.get("reason"),
            "promote_consults_founder_gate": "founder" in json.dumps(promote).lower(),
            "founder_auth_verified": promote.get("founder_auth_verified"),
            "fixed": fixed,
        },
        remediation="Bind founder gate output; require proof inside attempt_promote.",
    )


def probe_lesson_gate_still_hard() -> dict[str, Any]:
    blocked = apply_lesson_gate_v11(
        terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        quality_gates_passed=False,
        proposed_policy_effect_lesson_count=7,
    )
    fixture_blocked = apply_lesson_gate_v11(
        terminal_status="VERIFIED",
        quality_gates_passed=True,
        proposed_policy_effect_lesson_count=7,
        fixture_label=reflection_core.CONTROL_FIXTURE_LABEL,
    )
    ok = (
        blocked["policy_effect_lesson_allowed"] is False
        and blocked["new_policy_effect_lesson_count"] == 0
        and fixture_blocked["policy_effect_lesson_allowed"] is False
    )
    return _finding(
        finding_id="R3-E-LESSON-GATE-HARDENED",
        severity="PASS",
        lane="E",
        title="Lesson gate remains hard (not weakened)",
        status="PASS" if ok else "FAIL",
        detail="Lesson gate still blocks policy-effect lessons for incomplete/fixture terminals.",
        evidence={"incomplete": blocked, "fixture_verified_still_blocked": fixture_blocked},
        remediation="Do not weaken Lesson gate.",
    )


def probe_promotion_still_blocked() -> dict[str, Any]:
    sm = infra.PromotionStateMachine()
    result = sm.attempt_promote()
    summary = infra.run_point_in_time_qualification_dry_run()
    ok = (
        result.get("allowed") is False
        and summary.get("status") == infra.PIT_STATUS_BLOCKED_READY
        and summary.get("strategy_promoted") is False
        and all(v == infra.STAGE_STATUS_BLOCKED_READY for v in summary["stages"].values())
    )
    return _finding(
        finding_id="R3-F-PROMOTION-BLOCKING",
        severity="PASS",
        lane="F",
        title="Promotion state machine remains BLOCKED_READY",
        status="PASS" if ok else "FAIL",
        detail="attempt_promote always denies; all qualification stages stay BLOCKED_READY.",
        evidence={"attempt": result, "status": summary.get("status")},
        remediation="Retain hard block.",
    )


def run_pass1() -> dict[str, Any]:
    infra.reset_oos_seal_lineage()
    findings = [
        probe_checkpoint_counter_drift(),
        probe_critic_before_reasoner(),
        probe_nested_future_timestamp(),
        probe_oos_seal_regeneration(),
        probe_founder_auth_spoof(),
        probe_lesson_gate_still_hard(),
        probe_promotion_still_blocked(),
    ]
    return {
        "pass": 1,
        "findings": findings,
        "fail_count": sum(1 for f in findings if f["status"] == "FAIL"),
        "critical_fail_count": sum(
            1 for f in findings if f["status"] == "FAIL" and f["severity"] == "CRITICAL"
        ),
        "high_fail_count": sum(1 for f in findings if f["status"] == "FAIL" and f["severity"] == "HIGH"),
        "remediation_ids": list(REMEDIATION_FINDING_IDS),
    }


def run_pass2(pass1: dict[str, Any]) -> dict[str, Any]:
    again = run_pass1()
    by_id_1 = {f["finding_id"]: f for f in pass1["findings"]}
    by_id_2 = {f["finding_id"]: f for f in again["findings"]}
    stable = []
    unstable = []
    for fid, f1 in by_id_1.items():
        f2 = by_id_2[fid]
        row = {
            "finding_id": fid,
            "pass1_status": f1["status"],
            "pass2_status": f2["status"],
            "severity": f1["severity"],
            "stable": f1["status"] == f2["status"],
        }
        (stable if row["stable"] else unstable).append(row)
    critical = [f for f in again["findings"] if f["status"] == "FAIL" and f["severity"] == "CRITICAL"]
    high = [f for f in again["findings"] if f["status"] == "FAIL" and f["severity"] == "HIGH"]
    rem_status = {
        fid: ("FIXED" if by_id_2[fid]["status"] == "PASS" else "REMAINING")
        for fid in REMEDIATION_FINDING_IDS
    }
    if critical:
        recommendation = "BLOCK_INTEGRATION"
        rationale = "Critical adversarial failures remain after Pass 2."
    elif high:
        recommendation = "CONDITIONAL_HOLD"
        rationale = "High findings remain open."
    elif any(v == "REMAINING" for v in rem_status.values()):
        recommendation = "CONDITIONAL_HOLD"
        rationale = "One or more R3 remediation IDs remain open."
    else:
        recommendation = "PASS_WITH_NOTES"
        rationale = (
            "R3 E/F critical+high remediations cleared; Lesson gate and "
            "PROMOTION_BLOCKED_READY remain hard."
        )
    return {
        "pass": 2,
        "stability": {
            "stable_count": len(stable),
            "unstable_count": len(unstable),
            "rows": stable + unstable,
        },
        "findings": again["findings"],
        "critical_open": [f["finding_id"] for f in critical],
        "high_open": [f["finding_id"] for f in high],
        "remediation_status": rem_status,
        "recommendation": recommendation,
        "rationale": rationale,
    }
