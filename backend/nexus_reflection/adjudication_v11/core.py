"""Founder V11 Lane E — Reflection V2.3 adjudication.

This module is intentionally fixture-friendly. It models provider transport and
quality accounting without calling live providers or deriving progress from
summary metrics.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.nexus_ai.idempotency import SuccessfulCallDeduper, make_idempotency_key
from backend.nexus_ai.profiles import (
    CEREBRAS_RESEARCH_NORMALIZER,
    GROQ_MAIN_REASONER,
    GROQ_REFLECTION_REASONER,
    PROVIDER_PROFILES,
    SAMBANOVA_INDEPENDENT_CRITIC,
)
from backend.nexus_ai.scheduler import ProviderScheduler
from backend.nexus_edge_discovery.blind_reflection_v23 import (
    migrate_process_classification,
    normalize_critic_verdict,
)
from backend.nexus_provider.retry_policy import parse_rate_limit_reset, parse_retry_after
from backend.nexus_provider.transport_status import (
    is_quality_neutral_transport,
)
from backend.nexus_reflection.disagreement import (
    ALLOWED_CONFLICT_TYPES,
    build_disagreement_record,
    classify_conflict,
)
from backend.nexus_reflection.terminal_eval import evaluate_terminal

CONTROL_FIXTURE_LABEL = "CONTROL_FIXTURE_NOT_REAL_TRADING_LEARNING"
V11_PROVIDER_PROFILES = (
    GROQ_REFLECTION_REASONER,
    SAMBANOVA_INDEPENDENT_CRITIC,
    CEREBRAS_RESEARCH_NORMALIZER,
    GROQ_MAIN_REASONER,
)
TERMINAL_DENOMINATOR_KEYS = (
    "evidence_packet_constructible_ratio",
    "reflection_prompt_delivery_ratio_on_attempts",
    "full_calibration_completion_ratio",
    "blind_valid_schema_ratio",
    "informative_classification_ratio_overall",
    "informative_classification_ratio_on_sufficient_cases",
    "blind_agreement_ratio_on_sufficient_cases",
    "critic_resolution_ratio",
)


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_provider_retry_after(
    headers: Mapping[str, Any] | None,
    *,
    now: float | None = None,
    default_s: float | None = 900.0,
) -> float | None:
    """Parse provider Retry-After seconds or HTTP-date without secret-bearing calls."""
    return parse_retry_after(headers, now=now, default_s=default_s)


def parse_provider_quota_reset(
    headers: Mapping[str, Any] | None,
    *,
    now: float | None = None,
) -> float | None:
    """Parse provider quota reset headers as seconds until reset."""
    return parse_rate_limit_reset(headers, now=now)


def dedupe_completed_cases(
    *,
    profile_id: str,
    case_ids: list[str],
    completed_case_ids: list[str],
) -> list[str]:
    """Return pending IDs with successful cases removed, preserving manifest order."""
    completed = set(completed_case_ids)
    out: list[str] = []
    seen: set[str] = set()
    for cid in case_ids:
        if cid in completed or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    assert profile_id in PROVIDER_PROFILES
    return out


def _case_result(state: dict[str, Any], cid: str) -> dict[str, Any]:
    return dict((state.get("case_results") or {}).get(cid) or {})


def build_critic_order(state: dict[str, Any]) -> list[str]:
    """Order critic work only after Groq success, prioritizing unresolved disagreements."""
    case_ids = [str(x) for x in (state.get("case_ids") or [])]
    completed = set(str(x) for x in (state.get("completed_case_ids") or []))
    resolved = set(str(x) for x in (state.get("critic_resolved_ids") or []))
    pending: list[str] = []
    for cid in case_ids:
        if cid not in completed or cid in resolved:
            continue
        row = _case_result(state, cid)
        if row.get("evidence_sufficiency") != "EVIDENCE_SUFFICIENT":
            continue
        groq_cls = migrate_process_classification(row.get("process_classification"))
        det_cls = migrate_process_classification(row.get("deterministic_expected"))
        if groq_cls != det_cls or float(row.get("confidence") or 1.0) < 0.55:
            pending.append(cid)
    return pending


def _reasoner_success_for_case(scheduler: ProviderScheduler, case_id: str) -> bool:
    """True only when Groq Reasoner has a recorded SUCCESS for this case_id."""
    if scheduler.deduper.already_completed(GROQ_REFLECTION_REASONER, case_id):
        return True
    groq_q = scheduler.queues.get(GROQ_REFLECTION_REASONER)
    if groq_q is not None and case_id in groq_q.completed:
        return True
    return False


def record_provider_outcome(
    scheduler: ProviderScheduler,
    *,
    profile_id: str,
    case_id: str,
    prompt_hash: str,
    schema_version: str,
    result_status: str | None = None,
    http_status: int | None = None,
    headers: dict[str, Any] | None = None,
    response_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record one provider attempt with queue isolation and success dedupe."""
    # R3-E-CRITIC-BEFORE-REASONER: Critic dispatch authority requires Reasoner SUCCESS.
    if profile_id == SAMBANOVA_INDEPENDENT_CRITIC and not _reasoner_success_for_case(
        scheduler, case_id
    ):
        return {
            "profile_id": profile_id,
            "case_id": case_id,
            "dispatch_allowed": False,
            "transport_status": "CRITIC_BEFORE_REASONER_BLOCKED",
            "reason": "REASONER_SUCCESS_REQUIRED",
        }
    decision, idempotency_key = scheduler.begin_attempt(
        profile_id,
        case_id,
        prompt_hash=prompt_hash,
        schema_version=schema_version,
    )
    if not decision.allowed:
        return {
            "profile_id": profile_id,
            "case_id": case_id,
            "dispatch_allowed": False,
            "transport_status": decision.transport_status,
            "reason": decision.reason,
        }
    response_hash = _sha(response_payload or {})
    status = scheduler.record_outcome(
        profile_id,
        case_id,
        http_status=http_status,
        result_status=result_status,
        headers=headers,
        response_hash=response_hash,
    )
    return {
        "profile_id": profile_id,
        "case_id": case_id,
        "dispatch_allowed": True,
        "idempotency_key": idempotency_key,
        "transport_status": status,
        "response_hash": response_hash,
        "quality_neutral_transport": is_quality_neutral_transport(status),
    }


def _empty_transport() -> dict[str, dict[str, Any]]:
    return ProviderScheduler(sleep_fn=lambda _s: None).export_transport_for_checkpoint()


def build_fixture_state() -> dict[str, Any]:
    """Small deterministic fixture state; not real trading learning."""
    case_ids = [f"V11_FIX_{i:02d}" for i in range(4)]
    state: dict[str, Any] = {
        "schema": "v11_reflection_v23_adjudication_fixture_state",
        "schema_version": 1,
        "case_ids": case_ids,
        "completed_case_ids": list(case_ids),
        "pending_case_ids": [],
        "critic_case_ids": [case_ids[1], case_ids[2]],
        "critic_pending_ids": [],
        "critic_resolved_ids": [case_ids[1], case_ids[2]],
        "transport": _empty_transport(),
        "case_results": {},
        "fixture_label": CONTROL_FIXTURE_LABEL,
    }
    groq = state["transport"][GROQ_REFLECTION_REASONER]
    groq["attempt_count"] = 4
    groq["success_count"] = 4
    sn = state["transport"][SAMBANOVA_INDEPENDENT_CRITIC]
    sn["attempt_count"] = 2
    sn["success_count"] = 2
    rows = [
        ("GOOD_PROCESS_WIN", "GOOD_PROCESS_WIN", None),
        ("GOOD_PROCESS_LOSS", "BAD_PROCESS_LOSS", "AGREE_WITH_GROQ"),
        ("BAD_PROCESS_WIN", "GOOD_PROCESS_WIN", "AGREE_WITH_DETERMINISTIC"),
        ("UNDETERMINED_PROCESS", "UNDETERMINED", None),
    ]
    for cid, (groq_cls, det_cls, verdict) in zip(case_ids, rows, strict=True):
        cls = migrate_process_classification(groq_cls)
        det = migrate_process_classification(det_cls)
        state["case_results"][cid] = {
            "transport_status": "SUCCESS",
            "reflection_prompt_with_packet": True,
            "evidence_packet_constructible": True,
            "evidence_sufficiency": "EVIDENCE_INSUFFICIENT"
            if cls == "UNDETERMINED"
            else "EVIDENCE_SUFFICIENT",
            "process_classification": cls,
            "deterministic_expected": det,
            "deterministic_status": "FIXTURE_RULE",
            "supporting_evidence_ids": [f"ev_{cid}_process"],
            "critic_verdict": verdict,
            "critic_status": "RESOLVED" if verdict else None,
            "original_process_classification_raw": groq_cls,
        }
    return state


def build_disagreement_taxonomy(state: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for cid in state.get("completed_case_ids") or []:
        row = _case_result(state, str(cid))
        if row.get("evidence_sufficiency") != "EVIDENCE_SUFFICIENT":
            continue
        groq_cls = migrate_process_classification(row.get("process_classification"))
        det_cls = migrate_process_classification(row.get("deterministic_expected"))
        if groq_cls == det_cls:
            continue
        verdict = (
            normalize_critic_verdict(row.get("critic_verdict"), groq=groq_cls, det=det_cls)
            if row.get("critic_verdict")
            else None
        )
        conflict = classify_conflict(row, critic_verdict=verdict)
        if conflict not in ALLOWED_CONFLICT_TYPES:
            conflict = "TAXONOMY_AMBIGUOUS"
        records.append(
            build_disagreement_record(
                trade_id=str(cid),
                groq_classification=groq_cls,
                groq_evidence_ids=list(row.get("supporting_evidence_ids") or []),
                deterministic_classification=det_cls,
                deterministic_rule_ids=[str(row.get("deterministic_status") or "FIXTURE_RULE")],
                sambanova_result=verdict,
                evidence_sufficiency=row.get("evidence_sufficiency"),
                conflict_type=conflict,
                legacy_process_raw=row.get("original_process_classification_raw"),
            )
        )
    return records


def validate_terminal_denominators_v11(quality: Mapping[str, Any]) -> dict[str, Any]:
    """Validate required terminal ratio denominators without empty-set 1.0 claims."""
    issues: list[str] = []
    for key in TERMINAL_DENOMINATOR_KEYS:
        ratio = quality.get(key)
        if ratio is None:
            continue
        if not isinstance(ratio, Mapping):
            issues.append(f"{key}:not_ratio")
            continue
        try:
            denominator = float(ratio.get("denominator") or 0)
        except (TypeError, ValueError):
            issues.append(f"{key}:bad_denominator")
            continue
        value = ratio.get("value")
        status = ratio.get("status")
        if denominator <= 0 and value is not None:
            issues.append(f"{key}:zero_denominator_has_value")
        if status in {
            "NOT_APPLICABLE",
            "PROVIDER_BLOCKED",
            "GROQ_PROVIDER_BLOCKED",
            "SAMBANOVA_PROVIDER_BLOCKED",
            "PROVIDER_CAPACITY_UNKNOWN",
        } and value is not None:
            issues.append(f"{key}:blocked_status_has_value")
        if key == "full_calibration_completion_ratio":
            numerator = float(ratio.get("numerator") or 0)
            if denominator > 0 and numerator < denominator and status != "INCOMPLETE_SAMPLE":
                issues.append(f"{key}:incomplete_without_status")
    return {
        "terminal_denominator_validation": "PASS" if not issues else "FAIL",
        "issues": issues,
        "checked_ratio_keys": list(TERMINAL_DENOMINATOR_KEYS),
    }


def build_fixture_adjudication_result() -> dict[str, Any]:
    """Produce fixture adjudication result separate from any real checkpoint progress."""
    state = build_fixture_state()
    quality = evaluate_terminal(state)
    denominator_validation = validate_terminal_denominators_v11(quality)
    disagreements = build_disagreement_taxonomy(state)
    return {
        "schema": "v11_reflection_v23_adjudication_fixture_result",
        "created_at": _utc(),
        "label": CONTROL_FIXTURE_LABEL,
        "fixture_only": True,
        "real_ai_quality_claimed": False,
        "quality_gates_evaluated": bool(quality.get("quality_gates_evaluated")),
        "quality_gates_passed": bool(quality.get("quality_gates_passed")),
        "V2_3_TERMINAL_STATUS": quality.get("V2_3_TERMINAL_STATUS"),
        "provider_transport": state["transport"],
        "critic_order": build_critic_order(state),
        "disagreement_taxonomy": disagreements,
        "terminal_denominator_validation": denominator_validation,
        "UNDETERMINED_PROCESS_migrated_to_UNDETERMINED": True,
        "new_policy_effect_lesson_count": 0,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
    }


def hydrate_deduper_from_state(state: dict[str, Any]) -> SuccessfulCallDeduper:
    deduper = SuccessfulCallDeduper()
    for cid in state.get("completed_case_ids") or []:
        row = _case_result(state, str(cid))
        deduper.mark_completed(
            GROQ_REFLECTION_REASONER,
            str(cid),
            response_hash=str(row.get("response_hash") or ""),
            idempotency_key=make_idempotency_key(
                profile_id=GROQ_REFLECTION_REASONER,
                case_id=str(cid),
                prompt_hash=str(row.get("prompt_hash") or ""),
                schema_version=str(state.get("prompt_schema_version") or "blind_reflection_v2_3"),
            ),
        )
    for cid in state.get("critic_resolved_ids") or []:
        deduper.mark_completed(
            SAMBANOVA_INDEPENDENT_CRITIC,
            str(cid),
            response_hash=str(_case_result(state, str(cid)).get("critic_response_hash") or ""),
        )
    return deduper
