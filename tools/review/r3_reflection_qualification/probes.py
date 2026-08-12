"""Adversarial probes for Founder R3 Reflection + Qualification review."""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from tools.review.r3_reflection_qualification.origin_loader import (
    load_pit_namespace,
    load_reflection_namespace,
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


def probe_429_as_quality_failure(R: dict[str, Any]) -> dict[str, Any]:
    sch = R["scheduler"].ProviderScheduler(sleep_fn=lambda _s: None)
    out = R["core"].record_provider_outcome(
        sch,
        profile_id=R["profiles"].GROQ_REFLECTION_REASONER,
        case_id="ADV_429",
        prompt_hash="p429",
        schema_version="blind_reflection_v2_3",
        http_status=429,
        headers={"Retry-After": "12"},
    )
    polluted = False
    try:
        R["transport_status"].assert_429_not_quality_failure(
            "RATE_LIMITED",
            {"process_classification": "UNDETERMINED"},
        )
    except AssertionError:
        polluted = True
    ok = (
        out.get("transport_status") == "RATE_LIMITED"
        and out.get("quality_neutral_transport") is True
        and polluted is True
    )
    return _finding(
        finding_id="R3-E-429-QUALITY-NEUTRAL",
        severity="PASS",
        lane="E",
        title="HTTP 429 treated as quality-neutral transport",
        status="PASS" if ok else "FAIL",
        detail=(
            "Lane E marks 429 as RATE_LIMITED/quality-neutral. "
            "assert_429_not_quality_failure correctly rejects quality-field pollution, "
            "but V11 record_provider_outcome does not invoke that invariant itself."
        ),
        evidence={
            "transport_status": out.get("transport_status"),
            "quality_neutral_transport": out.get("quality_neutral_transport"),
            "invariant_rejects_quality_pollution": polluted,
            "wired_into_record_provider_outcome": False,
        },
        remediation=(
            "Call assert_429_not_quality_failure inside record_provider_outcome when "
            "status is RATE_LIMITED and any quality fields are present."
        ),
    )


def probe_critic_before_reasoner(R: dict[str, Any]) -> dict[str, Any]:
    sch = R["scheduler"].ProviderScheduler(sleep_fn=lambda _s: None)
    critic = R["core"].record_provider_outcome(
        sch,
        profile_id=R["profiles"].SAMBANOVA_INDEPENDENT_CRITIC,
        case_id="ADV_CRITIC_FIRST",
        prompt_hash="pc",
        schema_version="critic_v2_3",
        result_status="SUCCESS",
        response_payload={"critic_verdict": "AGREE_WITH_GROQ"},
    )
    order = R["core"].build_critic_order(
        {
            "case_ids": ["ADV_CRITIC_FIRST"],
            "completed_case_ids": [],
            "critic_resolved_ids": [],
            "case_results": {},
        }
    )
    bypass = critic.get("dispatch_allowed") is True and critic.get("transport_status") == "SUCCESS"
    return _finding(
        finding_id="R3-E-CRITIC-BEFORE-REASONER",
        severity="HIGH",
        lane="E",
        title="Critic can complete before Reasoner success",
        status="FAIL" if bypass else "PASS",
        detail=(
            "ProviderScheduler queues are independent; record_provider_outcome allows "
            "SAMBANOVA_INDEPENDENT_CRITIC SUCCESS with zero Groq completed cases. "
            "build_critic_order filters, but dispatch authority does not enforce ordering."
        ),
        evidence={
            "critic_dispatch_allowed": critic.get("dispatch_allowed"),
            "critic_transport_status": critic.get("transport_status"),
            "critic_order_without_reasoner": order,
        },
        remediation=(
            "Gate Critic begin_attempt on Reasoner SUCCESS for the same case_id "
            "(completed_case_ids / deduper), fail-closed otherwise."
        ),
    )


def probe_completed_case_replay(R: dict[str, Any]) -> dict[str, Any]:
    sch = R["scheduler"].ProviderScheduler(sleep_fn=lambda _s: None)
    first = R["core"].record_provider_outcome(
        sch,
        profile_id=R["profiles"].GROQ_REFLECTION_REASONER,
        case_id="ADV_REPLAY",
        prompt_hash="pr",
        schema_version="blind_reflection_v2_3",
        result_status="SUCCESS",
        response_payload={"ok": True},
    )
    second = R["core"].record_provider_outcome(
        sch,
        profile_id=R["profiles"].GROQ_REFLECTION_REASONER,
        case_id="ADV_REPLAY",
        prompt_hash="pr",
        schema_version="blind_reflection_v2_3",
        result_status="SUCCESS",
        response_payload={"ok": True},
    )
    pending = R["core"].dedupe_completed_cases(
        profile_id=R["profiles"].GROQ_REFLECTION_REASONER,
        case_ids=["ADV_REPLAY", "NEXT"],
        completed_case_ids=["ADV_REPLAY"],
    )
    ok = (
        first.get("dispatch_allowed") is True
        and second.get("dispatch_allowed") is False
        and second.get("reason") == "SUCCESSFUL_CASE_DEDUP"
        and pending == ["NEXT"]
    )
    return _finding(
        finding_id="R3-E-COMPLETED-CASE-DEDUPE",
        severity="PASS",
        lane="E",
        title="Completed-case replay blocked by deduper",
        status="PASS" if ok else "FAIL",
        detail="SuccessfulCallDeduper blocks second dispatch; dedupe_completed_cases preserves order.",
        evidence={
            "first_dispatch": first.get("dispatch_allowed"),
            "second_dispatch": second.get("dispatch_allowed"),
            "second_reason": second.get("reason"),
            "second_transport_status": second.get("transport_status"),
            "pending_after_dedupe": pending,
        },
        remediation="Keep hydrate_deduper_from_state wired on every real resume path.",
    )


def probe_checkpoint_counter_drift(R: dict[str, Any]) -> dict[str, Any]:
    sch = R["scheduler"].ProviderScheduler(sleep_fn=lambda _s: None)
    transport = sch.export_transport_for_checkpoint()
    transport[R["profiles"].GROQ_REFLECTION_REASONER]["success_count"] = 80
    transport[R["profiles"].GROQ_REFLECTION_REASONER]["attempt_count"] = 80
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
    state["integrity_checksum"] = R["checkpoint"].compute_integrity_checksum(state)
    # Drift success_count far above completed list and re-seal checksum.
    drifted = deepcopy(state)
    drifted["transport"][R["profiles"].GROQ_REFLECTION_REASONER]["success_count"] = 999
    drifted["integrity_checksum"] = R["checkpoint"].compute_integrity_checksum(drifted)
    probe = R["checkpoint"].detect_corruption(json.dumps(drifted))
    quality = R["terminal_eval"].evaluate_terminal(drifted)
    drift_undetected = probe.get("ok") is True and int(quality.get("groq_success_count") or 0) == 999
    return _finding(
        finding_id="R3-E-CHECKPOINT-COUNTER-DRIFT",
        severity="CRITICAL",
        lane="E",
        title="Checkpoint integrity ignores success_count vs completed-case drift",
        status="FAIL" if drift_undetected else "PASS",
        detail=(
            "integrity_checksum covers transport blob but does not enforce semantic "
            "consistency between success_count and completed_case_ids. "
            "evaluate_terminal trusts max(success_count, len(completed_case_ids)), "
            "so inflated counters can satisfy the groq_success>=80 capacity gate."
        ),
        evidence={
            "checksum_ok_despite_drift": probe.get("ok"),
            "integrity_status": probe.get("checkpoint_integrity_status"),
            "completed_case_count": len(drifted["completed_case_ids"]),
            "groq_success_count_used": quality.get("groq_success_count"),
            "fixture_schema_separate_from_v4": True,
            "fixture_schema": "v11_reflection_v23_adjudication_fixture_state",
        },
        remediation=(
            "Add semantic counter invariants to detect_corruption / migrate_checkpoint; "
            "refuse terminal evaluation when success_count != len(completed_case_ids) "
            "for Groq (and Critic resolved vs success)."
        ),
    )


def probe_undetermined_process_migration(R: dict[str, Any]) -> dict[str, Any]:
    migrated = R["blind"].migrate_process_classification("UNDETERMINED_PROCESS")
    fixture = R["core"].build_fixture_adjudication_result()
    rows = fixture.get("provider_transport") and R["core"].build_fixture_state()["case_results"]
    undetermined_rows = [
        cid
        for cid, row in rows.items()
        if row.get("process_classification") == "UNDETERMINED"
        and row.get("original_process_classification_raw") == "UNDETERMINED_PROCESS"
    ]
    ok = migrated == "UNDETERMINED" and bool(undetermined_rows)
    return _finding(
        finding_id="R3-E-UNDETERMINED-PROCESS-MIGRATION",
        severity="PASS",
        lane="E",
        title="Legacy UNDETERMINED_PROCESS migrates to UNDETERMINED",
        status="PASS" if ok else "FAIL",
        detail="migrate_process_classification preserves legacy raw while canonicalizing taxonomy.",
        evidence={
            "migrated": migrated,
            "fixture_undetermined_case_ids": undetermined_rows,
            "flag": fixture.get("UNDETERMINED_PROCESS_migrated_to_UNDETERMINED"),
        },
        remediation="None required for migration helper; keep legacy raw in disagreement records.",
    )


def probe_lesson_while_incomplete(R: dict[str, Any]) -> dict[str, Any]:
    blocked = R["lesson_gate"].apply_lesson_gate_v11(
        terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        quality_gates_passed=False,
        proposed_policy_effect_lesson_count=7,
    )
    fixture_blocked = R["lesson_gate"].apply_lesson_gate_v11(
        terminal_status="VERIFIED",
        quality_gates_passed=True,
        proposed_policy_effect_lesson_count=7,
        fixture_label=R["core"].CONTROL_FIXTURE_LABEL,
    )
    ok = (
        blocked["policy_effect_lesson_allowed"] is False
        and blocked["new_policy_effect_lesson_count"] == 0
        and fixture_blocked["policy_effect_lesson_allowed"] is False
    )
    return _finding(
        finding_id="R3-E-LESSON-GATE-INCOMPLETE",
        severity="PASS",
        lane="E",
        title="Lesson gate blocks policy-effect lessons while V2.3 incomplete",
        status="PASS" if ok else "FAIL",
        detail="apply_lesson_gate_v11 zeros lesson count for incomplete/fixture terminals.",
        evidence={
            "incomplete": blocked,
            "fixture_verified_still_blocked": fixture_blocked,
            "lesson_prevention_executed_semantics_inverted": blocked.get("lesson_prevention_executed")
            is False,
        },
        remediation=(
            "Optional: rename lesson_prevention_executed so True means prevention engaged "
            "when lessons are blocked."
        ),
    )


def probe_nested_future_timestamp(infra: Any) -> dict[str, Any]:
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
    return _finding(
        finding_id="R3-F-NESTED-FUTURE-TIMESTAMP",
        severity="CRITICAL",
        lane="F",
        title="Future timestamp hidden in nested evidence bypasses PIT exclusion",
        status="FAIL" if bypass else "PASS",
        detail=(
            "prove_future_data_exclusion only inspects top-level source/retrieval/availability "
            "fields on each record. Nested evidence timestamps after as_of are ignored."
        ),
        evidence={
            "status": result.get("status"),
            "allowed": result.get("allowed"),
            "violation_count": result.get("violation_count"),
            "nested_keys": sorted(nested["records"][0]["evidence"].keys()),
        },
        remediation=(
            "Recursively scan record trees for *_timestamp_ms / available_as_of_ms / "
            "as_of_ms fields and fail closed on any value > as_of_ms."
        ),
    )


def probe_oos_seal_regeneration(infra: Any) -> dict[str, Any]:
    as_of = 1_700_000_000_000
    dataset = infra.synthetic_dataset_lineage(as_of_ms=as_of)
    regs = infra.synthetic_interval_registries(as_of_ms=as_of)
    checksums = infra.semantic_checksums(infra.synthetic_candidate_fixture(), dataset, "code-sha")
    seal1 = infra.build_oos_cryptographic_seal(regs, checksums)
    old = regs["reserved"].intervals[0]
    regs["reserved"].intervals[0] = infra.IntervalRecord(
        old.interval_id,
        old.label,
        old.start_ms,
        old.end_ms + 86_400_000,
        old.category,
    )
    seal2 = infra.build_oos_cryptographic_seal(regs, checksums)
    regenerated = (
        seal1["seal"] != seal2["seal"]
        and seal1["status"] == "SEALED_NOT_CONSUMED"
        and seal2["status"] == "SEALED_NOT_CONSUMED"
    )
    return _finding(
        finding_id="R3-F-OOS-SEAL-REGENERATION",
        severity="CRITICAL",
        lane="F",
        title="OOS cryptographic seal can be regenerated after reserved-interval mutation",
        status="FAIL" if regenerated else "PASS",
        detail=(
            "build_oos_cryptographic_seal always recomputes a fresh seal from current inputs. "
            "There is no persisted seal binding, anti-regeneration check, or seal lineage."
        ),
        evidence={
            "seal1": seal1["seal"],
            "seal2": seal2["seal"],
            "seal_changed": seal1["seal"] != seal2["seal"],
            "both_status": [seal1["status"], seal2["status"]],
        },
        remediation=(
            "Persist first seal under write-once semantics; verify regenerations against "
            "stored seal and fail closed on reserved-registry mutation after seal creation."
        ),
    )


def probe_founder_auth_spoof(infra: Any) -> dict[str, Any]:
    gate = infra.FounderAuthorizationGate()
    denied = gate.evaluate({"founder_authorization_token": "SPOOF_TOKEN", "scope": gate.required_scope})
    spoofed = dict(denied)
    spoofed["authorized"] = True
    sm = infra.PromotionStateMachine()
    promote = sm.attempt_promote()
    # Spoof succeeds in memory; promotion still hard-blocked but never consults founder gate.
    coupling_missing = (
        spoofed["authorized"] is True
        and promote.get("allowed") is False
        and "founder" not in json.dumps(promote).lower()
    )
    return _finding(
        finding_id="R3-F-FOUNDER-AUTH-SPOOF",
        severity="HIGH",
        lane="F",
        title="Founder auth result is spoofable and decoupled from promotion gate",
        status="FAIL" if coupling_missing else "PASS",
        detail=(
            "evaluate() fail-closes authorization, but returned dicts are not integrity-bound. "
            "PromotionStateMachine.attempt_promote never consults FounderAuthorizationGate; "
            "blocking relies solely on unconditional PROMOTION_BLOCKED_READY."
        ),
        evidence={
            "evaluate_authorized": denied.get("authorized"),
            "evaluate_reason": denied.get("reason"),
            "spoofed_authorized": spoofed.get("authorized"),
            "promote_allowed": promote.get("allowed"),
            "promote_reason": promote.get("reason"),
            "promote_consults_founder_gate": False,
        },
        remediation=(
            "Bind founder gate output to a checksum/HMAC and require that proof inside "
            "attempt_promote before any non-blocked transition is even considered."
        ),
    )


def probe_promotion_blocking(infra: Any) -> dict[str, Any]:
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
        evidence={
            "attempt": result,
            "status": summary.get("status"),
            "all_stages_blocked_ready": summary.get("all_stages_blocked_ready"),
        },
        remediation="Retain hard block until Founder-authorized post-OOS path exists.",
    )


def run_pass1() -> dict[str, Any]:
    R = load_reflection_namespace()
    findings = [
        probe_429_as_quality_failure(R),
        probe_critic_before_reasoner(R),
        probe_completed_case_replay(R),
        probe_checkpoint_counter_drift(R),
        probe_undetermined_process_migration(R),
        probe_lesson_while_incomplete(R),
    ]
    infra = load_pit_namespace()
    findings.extend(
        [
            probe_nested_future_timestamp(infra),
            probe_oos_seal_regeneration(infra),
            probe_founder_auth_spoof(infra),
            probe_promotion_blocking(infra),
        ]
    )
    return {
        "pass": 1,
        "origin": {
            "reflection_branch": R["branch"],
            "reflection_root": str(R["root"]),
            "pit_branch": "feature/v11-point-in-time-qualification",
            "pit_root": str(infra.__file__),
        },
        "findings": findings,
        "fail_count": sum(1 for f in findings if f["status"] == "FAIL"),
        "critical_fail_count": sum(
            1 for f in findings if f["status"] == "FAIL" and f["severity"] == "CRITICAL"
        ),
        "high_fail_count": sum(1 for f in findings if f["status"] == "FAIL" and f["severity"] == "HIGH"),
    }


def run_pass2(pass1: dict[str, Any]) -> dict[str, Any]:
    """Re-execute probes; classifications must be stable (no flaky PASS/FAIL flips)."""
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
    if critical:
        recommendation = "BLOCK_INTEGRATION"
        rationale = (
            "Critical adversarial failures remain after Pass 2. "
            "Do not declare Lane E/F integrated PASS until remediation exists."
        )
    elif high:
        recommendation = "CONDITIONAL_HOLD"
        rationale = "No Critical fails, but High findings require remediation before promotion/lesson paths widen."
    else:
        recommendation = "PASS_WITH_NOTES"
        rationale = "Adversarial matrix cleared; retain blocked-only posture."
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
        "recommendation": recommendation,
        "rationale": rationale,
    }
