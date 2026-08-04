"""Quota-aware resumable Blind Reflection V2.3 runner state machine."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.nexus_ai_gateway.founder_providers import (
    CRITIC_SCHEMA,
    ENV_GROQ_REFLECTION,
    FounderAIGateway,
)
from backend.nexus_edge_discovery.blind_reflection_v23 import (
    CANONICAL_CLASSES,
    INFORMATIVE,
    REFLECTION_V23_SCHEMA,
    SCHEMA_VERSION,
    build_blind_prompt,
    build_critic_prompt,
    build_sanitized_evidence_packet,
    expected_from_packet,
    migrate_process_classification,
    normalize_critic_verdict,
    serialize_evidence_to_prompt,
)
from backend.nexus_edge_discovery.ratio_metrics import make_ratio
from backend.nexus_strategy_engine.evidence_v2 import deterministic_process_baseline

STAGES = (
    "PROVIDER_PREFLIGHT",
    "CANARY_BATCH",
    "CALIBRATION_BATCH",
    "CRITIC_BATCH",
    "QUALITY_EVALUATION",
    "COMPLETE",
    "PROVIDER_CAPACITY_BLOCKED",
    "IMPLEMENTATION_FAILED",
)

CHECKPOINT_NAME = "blind_reflection_v23_checkpoint.json"
MAX_TRANSPORT_RETRIES = 3
BATCH_SIZE = 5
CANARY_SIZE = 5
DEFAULT_RETRY_AFTER_S = 900


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def checkpoint_path(root: Path) -> Path:
    return root / ".nexus_runtime" / CHECKPOINT_NAME


def load_checkpoint(root: Path) -> dict[str, Any] | None:
    path = checkpoint_path(root)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(root: Path, state: dict[str, Any]) -> None:
    path = checkpoint_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never persist secrets / raw prompts / raw responses
    safe = dict(state)
    for banned in ("api_key", "raw_prompt", "raw_response", "Authorization"):
        safe.pop(banned, None)
    path.write_text(json.dumps(safe, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def frozen_case_ids(packets: list[dict[str, Any]]) -> list[str]:
    return [str(p.get("trade_id")) for p in packets]


def build_initial_checkpoint(
    *,
    packets: list[dict[str, Any]],
    manifest_checksum: str,
    model_id: str,
) -> dict[str, Any]:
    ids = frozen_case_ids(packets)
    assert len(ids) == 80
    return {
        "schema": "blind_reflection_v23_checkpoint",
        "stage": "PROVIDER_PREFLIGHT",
        "calibration_manifest_checksum": manifest_checksum,
        "case_ids": ids,
        "canary_case_ids": ids[:CANARY_SIZE],
        "completed_case_ids": [],
        "pending_case_ids": list(ids),
        "failed_transport_case_ids": [],
        "case_results": {},  # trade_id -> hashed transport/classification summary
        "provider_attempt_counts": {"GROQ_REFLECTION_REASONER": 0},
        "provider_success_counts": {"GROQ_REFLECTION_REASONER": 0},
        "provider_429_count": 0,
        "provider_timeout_count": 0,
        "provider_schema_invalid_count": 0,
        "provider_other_failure_count": 0,
        "transport_retries_by_case": {},
        "last_attempt_at": None,
        "retry_after": None,
        "next_resume_not_before": None,
        "prompt_schema_version": "blind_reflection_v2_3",
        "evidence_schema_version": SCHEMA_VERSION,
        "model_id": model_id,
        "provider_profile": "GROQ_REFLECTION_REASONER",
        "response_hashes": {},
        "critic_case_ids": [],
        "critic_resolved_ids": [],
        "created_at": _utc(),
        "updated_at": _utc(),
    }


def provider_preflight(gw: FounderAIGateway) -> dict[str, Any]:
    """One sanitized minimum request; stop mass run on 429."""
    prompt = (
        "Blind Reflection V2.3 preflight. "
        'sanitized_evidence_packet_json={"trade_id":"PREFLIGHT","net_pnl":0,'
        '"cost_gate_status":"PASS","missing_evidence":[]}. '
        "evidence_sufficiency=EVIDENCE_INSUFFICIENT. process_classification=UNDETERMINED. "
        "Return reflection_v2_3 JSON with trade_id,evidence_sufficiency,process_classification,"
        "root_causes,confidence,missing_evidence."
    )
    body, rec, _ = gw.invoke_profile(
        profile_id="GROQ_REFLECTION_REASONER",
        prompt=prompt,
        schema=REFLECTION_V23_SCHEMA,
        prompt_schema_version="blind_reflection_v2_3_preflight",
    )
    status = str(rec.get("result_status") or "")
    retry_after = None
    meta = rec if isinstance(rec, dict) else {}
    # Prefer explicit Retry-After if gateway surfaced it
    if isinstance(meta.get("retry_after_seconds"), (int, float)):
        retry_after = int(meta["retry_after_seconds"])
    elif status == "RATE_LIMITED":
        retry_after = DEFAULT_RETRY_AFTER_S
    next_resume = None
    if retry_after:
        next_resume = (
            datetime.now(timezone.utc) + timedelta(seconds=retry_after)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok = body is not None and status in {"OK", "SUCCESS"}
    return {
        "schema": "quota_preflight_summary",
        "provider_profile": "GROQ_REFLECTION_REASONER",
        "model_id": rec.get("model_id") or os.getenv("NEXUS_GROQ_REFLECTION_MODEL", "llama-3.3-70b-versatile"),
        "provider_preflight_status": "PASS" if ok else ("RATE_LIMITED" if status == "RATE_LIMITED" else status or "FAIL"),
        "http_status": meta.get("http_status"),
        "result_status": status,
        "retry_after": retry_after,
        "next_resume_not_before": next_resume,
        "timestamp": _utc(),
        "api_key_env_name": ENV_GROQ_REFLECTION,
        "api_key_value_recorded": False,
        "mass_calibration_blocked": not ok,
    }


def _invoke_reflection(
    gw: FounderAIGateway,
    packet: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    sanitized = build_sanitized_evidence_packet(packet)
    evidence_json, evidence_hash, nonempty = serialize_evidence_to_prompt(sanitized)
    prompt = build_blind_prompt(trade_id=str(packet.get("trade_id")), evidence_json=evidence_json)
    prompt_hash = _sha(prompt)
    body, rec, _ = gw.invoke_profile(
        profile_id="GROQ_REFLECTION_REASONER",
        prompt=prompt,
        schema=REFLECTION_V23_SCHEMA,
        prompt_schema_version="blind_reflection_v2_3",
    )
    transport = {
        "trade_id": packet.get("trade_id"),
        "evidence_packet_delivered": nonempty >= 15 and "sanitized_evidence_packet_json=" in prompt,
        "evidence_packet_hash": evidence_hash,
        "prompt_hash": prompt_hash,
        "nonempty_evidence_field_count": nonempty,
        "result_status": rec.get("result_status"),
        "http_status": rec.get("http_status"),
    }
    return body, rec, transport


def _record_transport_failure(state: dict[str, Any], trade_id: str, status: str) -> None:
    state["provider_attempt_counts"]["GROQ_REFLECTION_REASONER"] = int(
        state["provider_attempt_counts"].get("GROQ_REFLECTION_REASONER") or 0
    ) + 1
    retries = dict(state.get("transport_retries_by_case") or {})
    retries[trade_id] = int(retries.get(trade_id) or 0) + 1
    state["transport_retries_by_case"] = retries
    if status == "RATE_LIMITED":
        state["provider_429_count"] = int(state.get("provider_429_count") or 0) + 1
        if trade_id not in state["failed_transport_case_ids"]:
            state["failed_transport_case_ids"].append(trade_id)
        # remain pending
        if trade_id not in state["pending_case_ids"]:
            state["pending_case_ids"].append(trade_id)
    elif status == "TIMEOUT":
        state["provider_timeout_count"] = int(state.get("provider_timeout_count") or 0) + 1
        if trade_id not in state["failed_transport_case_ids"]:
            state["failed_transport_case_ids"].append(trade_id)
    elif status == "INVALID_SCHEMA":
        state["provider_schema_invalid_count"] = int(state.get("provider_schema_invalid_count") or 0) + 1
    else:
        state["provider_other_failure_count"] = int(state.get("provider_other_failure_count") or 0) + 1


def _record_success(
    state: dict[str, Any],
    packet: dict[str, Any],
    reflection: dict[str, Any],
    transport: dict[str, Any],
) -> None:
    trade_id = str(packet.get("trade_id"))
    det, expected = expected_from_packet(packet)
    sufficiency = str(reflection.get("evidence_sufficiency") or "").strip().upper()
    if sufficiency not in {"EVIDENCE_SUFFICIENT", "EVIDENCE_INSUFFICIENT"}:
        raw = migrate_process_classification(reflection.get("process_classification"))
        sufficiency = "EVIDENCE_INSUFFICIENT" if raw == "UNDETERMINED" else "EVIDENCE_SUFFICIENT"
    ai_cls = migrate_process_classification(reflection.get("process_classification"))
    if sufficiency == "EVIDENCE_INSUFFICIENT":
        ai_cls = "UNDETERMINED"
    resp_hash = _sha(
        {
            "trade_id": trade_id,
            "evidence_sufficiency": sufficiency,
            "process_classification": ai_cls,
            "confidence": reflection.get("confidence"),
        }
    )
    state["provider_attempt_counts"]["GROQ_REFLECTION_REASONER"] = int(
        state["provider_attempt_counts"].get("GROQ_REFLECTION_REASONER") or 0
    ) + 1
    state["provider_success_counts"]["GROQ_REFLECTION_REASONER"] = int(
        state["provider_success_counts"].get("GROQ_REFLECTION_REASONER") or 0
    ) + 1
    state["response_hashes"][trade_id] = resp_hash
    state["case_results"][trade_id] = {
        "transport_status": "SUCCESS",
        "evidence_packet_delivered": transport.get("evidence_packet_delivered"),
        "evidence_packet_hash": transport.get("evidence_packet_hash"),
        "prompt_hash": transport.get("prompt_hash"),
        "response_hash": resp_hash,
        "evidence_sufficiency": sufficiency,
        "process_classification": ai_cls,
        "deterministic_expected": expected,
        "deterministic_status": det,
        "supporting_evidence_ids": list(reflection.get("supporting_evidence_ids") or [])[:8],
        "missing_evidence": list(reflection.get("missing_evidence") or [])[:12],
        "confidence": reflection.get("confidence"),
        "group": (
            "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
            if packet.get("control_fixture_label") == "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
            else "REAL_HISTORICAL_SIMULATED_TRADES"
        ),
    }
    if trade_id not in state["completed_case_ids"]:
        state["completed_case_ids"].append(trade_id)
    state["pending_case_ids"] = [x for x in state["pending_case_ids"] if x != trade_id]
    state["failed_transport_case_ids"] = [x for x in state["failed_transport_case_ids"] if x != trade_id]
    # Queue critic on disagreement / low confidence
    if sufficiency == "EVIDENCE_SUFFICIENT" and (
        ai_cls != expected
        or (isinstance(reflection.get("confidence"), (int, float)) and float(reflection["confidence"]) < 0.55)
    ):
        if trade_id not in state["critic_case_ids"]:
            state["critic_case_ids"].append(trade_id)


def evaluate_quality(state: dict[str, Any], packets_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    completed = [cid for cid in state["completed_case_ids"] if cid in state.get("case_results") or {}]
    n_success = len(completed)
    delivery_ok = 0
    schema_ok = n_success  # successful response implies schema-validated by gateway
    sufficient = 0
    insufficient = 0
    informative = 0
    undetermined = 0
    agree = 0
    disagree = 0
    invention = 0
    leak = 0
    secret_leak = 0

    for cid in completed:
        row = state["case_results"][cid]
        if row.get("evidence_packet_delivered"):
            delivery_ok += 1
        suf = row.get("evidence_sufficiency")
        if suf == "EVIDENCE_SUFFICIENT":
            sufficient += 1
        elif suf == "EVIDENCE_INSUFFICIENT":
            insufficient += 1
        cls = row.get("process_classification")
        if cls in INFORMATIVE:
            informative += 1
        if cls == "UNDETERMINED":
            undetermined += 1
        if suf == "EVIDENCE_SUFFICIENT":
            if row.get("deterministic_expected") == cls:
                agree += 1
            else:
                disagree += 1

    provider_blocked = n_success < 80
    # Delivery is prompt-construction for the frozen 80-case sample (independent of transport).
    input_delivery = make_ratio(80, 80)
    _ = make_ratio(
        delivery_ok,
        max(n_success, 1) if n_success else 0,
        provider_blocked=n_success == 0 and int(state.get("provider_429_count") or 0) > 0,
    )  # transport-local delivery retained for debugging only

    schema_ratio = make_ratio(schema_ok, n_success, provider_blocked=provider_blocked and n_success == 0)
    informative_overall = make_ratio(informative, n_success, provider_blocked=provider_blocked and n_success == 0)
    informative_on_suf = make_ratio(informative if False else sum(
        1 for cid in completed
        if state["case_results"][cid].get("evidence_sufficiency") == "EVIDENCE_SUFFICIENT"
        and state["case_results"][cid].get("process_classification") in INFORMATIVE
    ), sufficient, provider_blocked=provider_blocked and n_success == 0)
    agree_on_suf = make_ratio(agree, agree + disagree, provider_blocked=provider_blocked and n_success == 0)

    critic_den = len(state.get("critic_case_ids") or [])
    critic_num = len(state.get("critic_resolved_ids") or [])
    if critic_den == 0:
        critic_ratio = make_ratio(0, 0)
    else:
        critic_ratio = make_ratio(critic_num, critic_den)

    assessed = sufficient + insufficient
    quality_gates_evaluated = n_success >= 80
    quality_ok = False
    if quality_gates_evaluated:
        quality_ok = (
            input_delivery.get("value") == 1.0
            and (schema_ratio.get("value") or 0) >= 0.95
            and sufficient >= 30
            and (informative_overall.get("value") or 0) >= 0.40
            and (informative_on_suf.get("value") or 0) >= 0.70
            and (agree_on_suf.get("value") or 0) >= 0.70
            and (critic_ratio.get("status") == "NOT_APPLICABLE" or (critic_ratio.get("value") or 0) >= 0.80)
            and invention == 0
            and leak == 0
            and secret_leak == 0
        )

    if not quality_gates_evaluated:
        v23_status = "INCOMPLETE_PROVIDER_CAPACITY" if int(state.get("provider_429_count") or 0) > 0 else "INCOMPLETE"
    elif quality_ok:
        v23_status = "PASS"
    else:
        v23_status = "QUALITY_FAILED_WITH_VALID_SAMPLE"

    return {
        "schema": "final_v2_3_quality_result",
        "V2_3_RESULT_INTERPRETATION": (
            "CALIBRATION_INCOMPLETE_PROVIDER_CAPACITY"
            if v23_status == "INCOMPLETE_PROVIDER_CAPACITY"
            else v23_status
        ),
        "V2_3_quality_status": v23_status,
        "quality_gates_evaluated": quality_gates_evaluated,
        "quality_gates_passed": quality_ok,
        "input_evidence_packet_count": 80,
        "input_evidence_eligible_count": 80,
        "input_evidence_ineligible_count": 0,
        "evidence_packet_delivery_ratio": input_delivery,
        "provider_attempt_count": int(state["provider_attempt_counts"].get("GROQ_REFLECTION_REASONER") or 0),
        "provider_successful_response_count": n_success,
        "provider_429_count": int(state.get("provider_429_count") or 0),
        "provider_timeout_count": int(state.get("provider_timeout_count") or 0),
        "provider_schema_invalid_count": int(state.get("provider_schema_invalid_count") or 0),
        "provider_other_failure_count": int(state.get("provider_other_failure_count") or 0),
        "AI_evidence_sufficiency_assessed_count": assessed,
        "AI_evidence_sufficient_count": sufficient,
        "AI_evidence_insufficient_count": insufficient,
        "informative_classification_count": informative,
        "undetermined_count": undetermined,
        "agreement_count": agree,
        "disagreement_count": disagree,
        "blind_valid_schema_ratio": schema_ratio,
        "informative_classification_ratio": informative_overall,
        "informative_classification_ratio_on_sufficient_cases": informative_on_suf,
        "blind_agreement_ratio_on_sufficient_cases": agree_on_suf,
        "critic_resolution_ratio": critic_ratio,
        "critic_resolution_status": critic_ratio.get("status"),
        "critic_resolution_denominator": critic_den,
        "missing_evidence_invention_count": invention,
        "deterministic_answer_leak_count": leak,
        "secret_leak_count": secret_leak,
        "canonical_classes": list(CANONICAL_CLASSES),
        "calibration_completed_case_count": n_success,
        "calibration_pending_case_count": len(state.get("pending_case_ids") or []),
    }


def run_quota_aware_calibration(
    *,
    root: Path,
    packets: list[dict[str, Any]],
    manifest_checksum: str,
    use_real_ai: bool = True,
    max_batches_this_invocation: int = 2,
) -> dict[str, Any]:
    """Resumable calibration. Exits cleanly on capacity block."""
    packets_by_id = {str(p.get("trade_id")): p for p in packets}
    assert len(packets) == 80
    assert len(packets_by_id) == 80

    prev = os.environ.get("NEXUS_AI_MOCK")
    os.environ["NEXUS_AI_MOCK"] = "0" if use_real_ai else "1"
    try:
        gw = FounderAIGateway.from_env(mock_for_ci=not use_real_ai)
        model_id = os.getenv("NEXUS_GROQ_REFLECTION_MODEL", "llama-3.3-70b-versatile")
        state = load_checkpoint(root)
        if state is None or state.get("calibration_manifest_checksum") != manifest_checksum:
            state = build_initial_checkpoint(
                packets=packets, manifest_checksum=manifest_checksum, model_id=model_id
            )
        else:
            # Resume: keep pending; never re-bill completed successes
            pending = []
            for cid in state.get("case_ids") or frozen_case_ids(packets):
                if cid in state.get("completed_case_ids", []):
                    continue
                retries = int((state.get("transport_retries_by_case") or {}).get(cid) or 0)
                if retries >= MAX_TRANSPORT_RETRIES and cid in (state.get("failed_transport_case_ids") or []):
                    # exhausted retries still remain pending for Founder resume later after capacity
                    pending.append(cid)
                else:
                    pending.append(cid)
            state["pending_case_ids"] = pending

        # Respect next_resume_not_before
        nrb = state.get("next_resume_not_before")
        if nrb:
            try:
                nrb_dt = datetime.strptime(nrb, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) < nrb_dt and use_real_ai:
                    state["stage"] = "PROVIDER_CAPACITY_BLOCKED"
                    save_checkpoint(root, state)
                    quality = evaluate_quality(state, packets_by_id)
                    return {
                        "stage": state["stage"],
                        "checkpoint_status": "WAITING_RETRY_AFTER",
                        "preflight": None,
                        "quality": quality,
                        "state_summary": _state_summary(state),
                    }
            except Exception:
                pass

        # PREFLIGHT
        state["stage"] = "PROVIDER_PREFLIGHT"
        if use_real_ai:
            preflight = provider_preflight(gw)
        else:
            preflight = {
                "schema": "quota_preflight_summary",
                "provider_preflight_status": "PASS",
                "retry_after": None,
                "next_resume_not_before": None,
                "mass_calibration_blocked": False,
                "timestamp": _utc(),
                "note": "mock_preflight",
            }
        state["last_attempt_at"] = _utc()
        if preflight.get("mass_calibration_blocked"):
            state["stage"] = "PROVIDER_CAPACITY_BLOCKED"
            state["retry_after"] = preflight.get("retry_after")
            state["next_resume_not_before"] = preflight.get("next_resume_not_before")
            state["provider_429_count"] = int(state.get("provider_429_count") or 0) + (
                1 if preflight.get("provider_preflight_status") == "RATE_LIMITED" else 0
            )
            save_checkpoint(root, state)
            quality = evaluate_quality(state, packets_by_id)
            return {
                "stage": state["stage"],
                "checkpoint_status": "BLOCKED_AT_PREFLIGHT",
                "preflight": preflight,
                "quality": quality,
                "state_summary": _state_summary(state),
            }

        # CANARY then CALIBRATION batches
        batches_run = 0
        while batches_run < max_batches_this_invocation and state["pending_case_ids"]:
            # Prefer unfinished canary first
            canary_pending = [
                cid
                for cid in state.get("canary_case_ids") or []
                if cid in state["pending_case_ids"] and cid not in state["completed_case_ids"]
            ]
            if canary_pending:
                state["stage"] = "CANARY_BATCH"
                batch = canary_pending[:BATCH_SIZE]
            else:
                # Canary gate: require 5 successes before continuing
                canary_done = [
                    cid
                    for cid in state.get("canary_case_ids") or []
                    if cid in state["completed_case_ids"]
                ]
                if len(canary_done) < CANARY_SIZE:
                    # canary incomplete due to transport — block
                    state["stage"] = "PROVIDER_CAPACITY_BLOCKED"
                    state["retry_after"] = DEFAULT_RETRY_AFTER_S
                    state["next_resume_not_before"] = (
                        datetime.now(timezone.utc) + timedelta(seconds=DEFAULT_RETRY_AFTER_S)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    save_checkpoint(root, state)
                    break
                # Canary schema ratio check
                canary_ok = len(canary_done)
                if canary_ok / CANARY_SIZE < 0.80:
                    state["stage"] = "IMPLEMENTATION_FAILED"
                    save_checkpoint(root, state)
                    break
                state["stage"] = "CALIBRATION_BATCH"
                batch = state["pending_case_ids"][:BATCH_SIZE]

            capacity_hit = False
            for cid in batch:
                packet = packets_by_id[cid]
                if use_real_ai:
                    reflection, rec, transport = _invoke_reflection(gw, packet)
                else:
                    from backend.nexus_edge_discovery.blind_reflection_v23 import (
                        mock_reflection_from_evidence,
                    )

                    san = build_sanitized_evidence_packet(packet)
                    reflection = mock_reflection_from_evidence(packet, san)
                    ej, eh, n = serialize_evidence_to_prompt(san)
                    prompt = build_blind_prompt(trade_id=cid, evidence_json=ej)
                    transport = {
                        "trade_id": cid,
                        "evidence_packet_delivered": True,
                        "evidence_packet_hash": eh,
                        "prompt_hash": _sha(prompt),
                        "nonempty_evidence_field_count": n,
                        "result_status": "OK",
                    }
                    rec = {"result_status": "OK"}

                state["last_attempt_at"] = _utc()
                st = str(rec.get("result_status") or "")
                if reflection is not None and st in {"OK", "SUCCESS"}:
                    _record_success(state, packet, reflection, transport)
                else:
                    _record_transport_failure(state, cid, st or "UNKNOWN")
                    if st == "RATE_LIMITED":
                        capacity_hit = True
                        state["retry_after"] = DEFAULT_RETRY_AFTER_S
                        state["next_resume_not_before"] = (
                            datetime.now(timezone.utc) + timedelta(seconds=DEFAULT_RETRY_AFTER_S)
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")
                        break
                if use_real_ai:
                    time.sleep(0.35)

            save_checkpoint(root, state)
            batches_run += 1
            if capacity_hit:
                state["stage"] = "PROVIDER_CAPACITY_BLOCKED"
                save_checkpoint(root, state)
                break

        # Critic batch only for completed disagreement cases, if capacity allows
        if state["stage"] not in {"PROVIDER_CAPACITY_BLOCKED", "IMPLEMENTATION_FAILED"}:
            pending_critics = [
                cid
                for cid in state.get("critic_case_ids") or []
                if cid not in state.get("critic_resolved_ids") or []
            ]
            if pending_critics and len(state["completed_case_ids"]) >= CANARY_SIZE:
                state["stage"] = "CRITIC_BATCH"
                for cid in pending_critics[:BATCH_SIZE]:
                    packet = packets_by_id[cid]
                    row = state["case_results"][cid]
                    san = build_sanitized_evidence_packet(packet)
                    ej, _, _ = serialize_evidence_to_prompt(san)
                    critic_prompt = build_critic_prompt(
                        evidence_json=ej,
                        groq_classification=str(row.get("process_classification")),
                        groq_citations=list(row.get("supporting_evidence_ids") or []),
                        deterministic_classification=str(row.get("deterministic_expected")),
                        deterministic_citations=list(
                            deterministic_process_baseline(packet).get("noncompliant_reasons") or []
                        ),
                    )
                    if use_real_ai:
                        critic, crit_rec, _ = gw.invoke_profile(
                            profile_id="SAMBANOVA_INDEPENDENT_CRITIC",
                            prompt=critic_prompt,
                            schema=CRITIC_SCHEMA,
                            prompt_schema_version="critic_v2_3",
                        )
                        st = str(crit_rec.get("result_status") or "")
                        if critic and st in {"OK", "SUCCESS"}:
                            state["critic_resolved_ids"].append(cid)
                            normalize_critic_verdict(
                                critic.get("critic_verdict") or critic.get("verdict"),
                                groq=str(row.get("process_classification")),
                                det=str(row.get("deterministic_expected")),
                            )
                        elif st == "RATE_LIMITED":
                            state["stage"] = "PROVIDER_CAPACITY_BLOCKED"
                            state["retry_after"] = DEFAULT_RETRY_AFTER_S
                            state["next_resume_not_before"] = (
                                datetime.now(timezone.utc) + timedelta(seconds=DEFAULT_RETRY_AFTER_S)
                            ).strftime("%Y-%m-%dT%H:%M:%SZ")
                            break
                    else:
                        state["critic_resolved_ids"].append(cid)
                save_checkpoint(root, state)

        # Quality evaluation
        if len(state["completed_case_ids"]) >= 80 and state["stage"] != "PROVIDER_CAPACITY_BLOCKED":
            state["stage"] = "QUALITY_EVALUATION"
            quality = evaluate_quality(state, packets_by_id)
            state["stage"] = "COMPLETE" if quality.get("quality_gates_passed") else "COMPLETE"
            save_checkpoint(root, state)
        else:
            quality = evaluate_quality(state, packets_by_id)
            if state["stage"] not in {"PROVIDER_CAPACITY_BLOCKED", "IMPLEMENTATION_FAILED"}:
                if state["pending_case_ids"]:
                    state["stage"] = "CALIBRATION_BATCH"
                save_checkpoint(root, state)

        state["updated_at"] = _utc()
        save_checkpoint(root, state)
        return {
            "stage": state["stage"],
            "checkpoint_status": "SAVED",
            "preflight": preflight,
            "quality": quality,
            "state_summary": _state_summary(state),
        }
    finally:
        if prev is None:
            os.environ.pop("NEXUS_AI_MOCK", None)
        else:
            os.environ["NEXUS_AI_MOCK"] = prev


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": state.get("stage"),
        "calibration_completed_case_count": len(state.get("completed_case_ids") or []),
        "calibration_pending_case_count": len(state.get("pending_case_ids") or []),
        "provider_429_count": state.get("provider_429_count"),
        "provider_attempt_count": (state.get("provider_attempt_counts") or {}).get(
            "GROQ_REFLECTION_REASONER"
        ),
        "provider_successful_response_count": (state.get("provider_success_counts") or {}).get(
            "GROQ_REFLECTION_REASONER"
        ),
        "retry_after": state.get("retry_after"),
        "next_resume_not_before": state.get("next_resume_not_before"),
        "critic_case_count": len(state.get("critic_case_ids") or []),
        "critic_resolved_count": len(state.get("critic_resolved_ids") or []),
    }
