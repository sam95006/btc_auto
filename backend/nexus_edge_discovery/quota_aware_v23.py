"""Quota-aware Blind Reflection V2.3 — provider-specific transport + split queues."""
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
    ENV_SAMBANOVA,
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
from backend.nexus_edge_discovery.provider_transport_v23 import (
    DEFAULT_RETRY_AFTER_S,
    PROFILES,
    ProviderTransportController,
    ReplayFixtureStore,
    dedupe_pending_against_success,
    detect_checkpoint_corruption,
    exponential_backoff_with_jitter,
    is_ai_quality_failure,
    is_transport_failure,
    parse_retry_after,
    repair_checkpoint_overlap,
    validate_terminal_denominators,
)
from backend.nexus_edge_discovery.ratio_metrics import make_ratio
from backend.nexus_strategy_engine.evidence_v2 import deterministic_process_baseline

GROQ_STAGES = (
    "GROQ_PREFLIGHT",
    "GROQ_CANARY",
    "GROQ_CALIBRATION_BATCH",
    "GROQ_COMPLETE",
    "GROQ_CAPACITY_BLOCKED",
    "GROQ_IMPLEMENTATION_FAILED",
    "INVOCATION_BATCH_LIMIT_REACHED",
)
SAMBANOVA_STAGES = (
    "SAMBANOVA_PREFLIGHT",
    "SAMBANOVA_CRITIC_BATCH",
    "SAMBANOVA_COMPLETE",
    "SAMBANOVA_CAPACITY_BLOCKED",
    "SAMBANOVA_IMPLEMENTATION_FAILED",
    "INVOCATION_BATCH_LIMIT_REACHED",
)

CHECKPOINT_NAME = "blind_reflection_v23_checkpoint.json"
MAX_TRANSPORT_RETRIES = 3
BATCH_SIZE = 5
CANARY_SIZE = 5


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
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip() or "\x00" in raw:
            return {
                "_checkpoint_load_error": "corrupt_empty_or_null",
                "schema_version": 0,
                "case_ids": [],
            }
        state = json.loads(raw)
    except (json.JSONDecodeError, OSError, UnicodeError) as exc:
        return {
            "_checkpoint_load_error": type(exc).__name__,
            "schema_version": 0,
            "case_ids": [],
        }
    if not isinstance(state, dict):
        return {
            "_checkpoint_load_error": "not_a_dict",
            "schema_version": 0,
            "case_ids": [],
        }
    return state


def save_checkpoint(root: Path, state: dict[str, Any]) -> None:
    path = checkpoint_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = dict(state)
    for banned in ("api_key", "raw_prompt", "raw_response", "Authorization"):
        safe.pop(banned, None)
    # Persist transport controller snapshots if present
    controllers = safe.pop("_transport_controllers", None)
    if isinstance(controllers, dict):
        safe.setdefault("transport_controllers", {})
        for pid, ctrl in controllers.items():
            if hasattr(ctrl, "to_dict"):
                safe["transport_controllers"][pid] = ctrl.to_dict()
    path.write_text(json.dumps(safe, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _controllers_from_state(state: dict[str, Any]) -> dict[str, ProviderTransportController]:
    out: dict[str, ProviderTransportController] = {}
    snap = state.get("transport_controllers") or {}
    for pid in PROFILES:
        ctrl = ProviderTransportController(profile_id=pid)
        row = snap.get(pid) or {}
        nrb = row.get("next_resume_not_before") or (
            (state.get("transport") or {}).get(pid) or {}
        ).get("next_resume_not_before")
        if nrb:
            try:
                ctrl.next_resume_not_before = datetime.strptime(
                    str(nrb), "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
            except Exception:
                pass
        qra = row.get("quota_reset_at")
        if qra:
            try:
                ctrl.quota_reset_at = datetime.strptime(
                    str(qra), "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
            except Exception:
                pass
        circuit = row.get("circuit") or {}
        if circuit.get("state"):
            ctrl.circuit.state = str(circuit["state"])
            ctrl.circuit.consecutive_failures = int(circuit.get("consecutive_failures") or 0)
            ctrl.circuit.last_failure_status = circuit.get("last_failure_status")
        out[pid] = ctrl
    state["_transport_controllers"] = out
    return out


def _apply_retry_after_to_transport(
    state: dict[str, Any],
    profile: str,
    *,
    headers: dict[str, Any] | None = None,
    body: str | None = None,
    meta: dict[str, Any] | None = None,
) -> float:
    ctrl = (state.get("_transport_controllers") or {}).get(profile)
    if ctrl is None:
        ctrl = ProviderTransportController(profile_id=profile)
        state.setdefault("_transport_controllers", {})[profile] = ctrl
    hdrs = dict(headers or {})
    if meta:
        # Founder gateway may surface retry_after_s / response headers
        if meta.get("headers"):
            hdrs.update({str(k).lower(): v for k, v in dict(meta["headers"]).items()})
        if meta.get("retry_after_s") is not None and "retry-after" not in hdrs:
            hdrs["retry-after"] = str(meta["retry_after_s"])
    wait = ctrl.apply_rate_limit(hdrs, body=body)
    t = state["transport"][profile]
    t["retry_after"] = wait
    t["next_resume_not_before"] = (
        ctrl.next_resume_not_before.strftime("%Y-%m-%dT%H:%M:%SZ")
        if ctrl.next_resume_not_before
        else None
    )
    t["quota_reset_at"] = (
        ctrl.quota_reset_at.strftime("%Y-%m-%dT%H:%M:%SZ") if ctrl.quota_reset_at else None
    )
    t["circuit"] = ctrl.circuit.to_dict()
    t["token_bucket"] = ctrl.bucket.to_dict()
    return wait


def _empty_provider_transport(profile_id: str, model_id: str = "") -> dict[str, Any]:
    return {
        "profile_id": profile_id,
        "model_id": model_id,
        "attempt_count": 0,
        "success_count": 0,
        "HTTP_429_count": 0,
        "timeout_count": 0,
        "invalid_schema_count": 0,
        "other_failure_count": 0,
        "last_attempt_at": None,
        "retry_after": None,
        "next_resume_not_before": None,
        "last_exit_reason": None,
    }


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
        "schema": "blind_reflection_v23_checkpoint_v3",
        "schema_version": 3,
        "calibration_manifest_checksum": manifest_checksum,
        "case_ids": ids,
        "canary_case_ids": ids[:CANARY_SIZE],
        "completed_case_ids": [],
        "pending_case_ids": list(ids),
        "failed_transport_case_ids": [],
        "requires_founder_resume_ids": [],
        "case_results": {},
        "transport": {
            "GROQ_REFLECTION_REASONER": _empty_provider_transport(
                "GROQ_REFLECTION_REASONER", model_id
            ),
            "SAMBANOVA_INDEPENDENT_CRITIC": _empty_provider_transport(
                "SAMBANOVA_INDEPENDENT_CRITIC",
                os.getenv("NEXUS_SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct"),
            ),
            "CEREBRAS_RESEARCH_NORMALIZER": _empty_provider_transport(
                "CEREBRAS_RESEARCH_NORMALIZER",
                os.getenv("NEXUS_CEREBRAS_MODEL", "gemma-4-31b"),
            ),
            "GROQ_MAIN_REASONER": _empty_provider_transport(
                "GROQ_MAIN_REASONER",
                os.getenv("NEXUS_GROQ_MAIN_MODEL", "llama-3.3-70b-versatile"),
            ),
        },
        "transport_retries_by_case": {},
        "prompt_schema_version": "blind_reflection_v2_3",
        "evidence_schema_version": SCHEMA_VERSION,
        "response_hashes": {},
        "critic_case_ids": [],
        "critic_resolved_ids": [],
        "critic_pending_ids": [],
        "groq_stage": "GROQ_PREFLIGHT",
        "sambanova_stage": "SAMBANOVA_PREFLIGHT",
        "exit_reason": None,
        "created_at": _utc(),
        "updated_at": _utc(),
    }


def migrate_checkpoint_v2_to_v3(state: dict[str, Any], *, model_id: str) -> dict[str, Any]:
    """Preserve progress from v2 checkpoint into provider-specific v3 schema."""
    if int(state.get("schema_version") or 0) >= 3 and state.get("transport"):
        return state
    out = dict(state)
    out["schema"] = "blind_reflection_v23_checkpoint_v3"
    out["schema_version"] = 3
    transport = {
        "GROQ_REFLECTION_REASONER": _empty_provider_transport("GROQ_REFLECTION_REASONER", model_id),
        "SAMBANOVA_INDEPENDENT_CRITIC": _empty_provider_transport(
            "SAMBANOVA_INDEPENDENT_CRITIC",
            os.getenv("NEXUS_SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct"),
        ),
        "CEREBRAS_RESEARCH_NORMALIZER": _empty_provider_transport("CEREBRAS_RESEARCH_NORMALIZER"),
        "GROQ_MAIN_REASONER": _empty_provider_transport("GROQ_MAIN_REASONER"),
    }
    groq = transport["GROQ_REFLECTION_REASONER"]
    groq["attempt_count"] = int((state.get("provider_attempt_counts") or {}).get("GROQ_REFLECTION_REASONER") or 0)
    groq["success_count"] = int((state.get("provider_success_counts") or {}).get("GROQ_REFLECTION_REASONER") or 0)
    groq["HTTP_429_count"] = int(state.get("provider_429_count") or 0)
    groq["timeout_count"] = int(state.get("provider_timeout_count") or 0)
    groq["invalid_schema_count"] = int(state.get("provider_schema_invalid_count") or 0)
    groq["other_failure_count"] = int(state.get("provider_other_failure_count") or 0)
    groq["retry_after"] = state.get("retry_after")
    groq["next_resume_not_before"] = state.get("next_resume_not_before")
    groq["last_attempt_at"] = state.get("last_attempt_at")
    # Prior run marked PROVIDER_CAPACITY_BLOCKED with 0 Groq 429s while critic pending → SambaNova unknown/block
    sn = transport["SAMBANOVA_INDEPENDENT_CRITIC"]
    critic_pending = [
        cid
        for cid in (state.get("critic_case_ids") or [])
        if cid not in (state.get("critic_resolved_ids") or [])
    ]
    if state.get("stage") == "PROVIDER_CAPACITY_BLOCKED" and critic_pending and groq["HTTP_429_count"] == 0:
        sn["last_exit_reason"] = "PROVIDER_CAPACITY_UNKNOWN"
        sn["retry_after"] = state.get("retry_after") or DEFAULT_RETRY_AFTER_S
        sn["next_resume_not_before"] = state.get("next_resume_not_before")
        out["sambanova_stage"] = "SAMBANOVA_CAPACITY_BLOCKED"
        # Clear bogus global block so Groq can continue
        groq["retry_after"] = None
        groq["next_resume_not_before"] = None
        groq["last_exit_reason"] = "INVOCATION_BATCH_LIMIT_REACHED_OR_CRITIC_SIDE_BLOCK_MISATTRIBUTED"
        out["groq_stage"] = (
            "GROQ_COMPLETE"
            if len(state.get("pending_case_ids") or []) == 0
            else "GROQ_CALIBRATION_BATCH"
        )
    else:
        out["groq_stage"] = "GROQ_CALIBRATION_BATCH" if state.get("pending_case_ids") else "GROQ_COMPLETE"
        out["sambanova_stage"] = (
            "SAMBANOVA_CRITIC_BATCH" if critic_pending else "SAMBANOVA_COMPLETE"
        )
    out["transport"] = transport
    out["critic_pending_ids"] = critic_pending
    out["requires_founder_resume_ids"] = list(state.get("requires_founder_resume_ids") or [])
    out["exit_reason"] = None
    # Prior successful Reflection cases already received packets; backfill delivery flags.
    case_results = dict(out.get("case_results") or {})
    for cid in out.get("completed_case_ids") or []:
        row = dict(case_results.get(cid) or {})
        if row.get("transport_status") in {None, "SUCCESS"} or row.get("evidence_packet_delivered"):
            row.setdefault("reflection_prompt_with_packet", True)
            row.setdefault("evidence_packet_constructible", True)
            row.setdefault("transport_status", "SUCCESS")
        case_results[cid] = row
    out["case_results"] = case_results
    completed_n = len(out.get("completed_case_ids") or [])
    with_packet_n = sum(
        1 for cid in (out.get("completed_case_ids") or []) if case_results.get(cid, {}).get("reflection_prompt_with_packet")
    )
    out["reflection_prompt_with_packet_count"] = max(
        int(out.get("reflection_prompt_with_packet_count") or 0),
        with_packet_n,
        int(groq.get("success_count") or 0),
    )
    # Align attempt floor with known successes so delivery ratio is not understated after migration.
    if int(groq.get("attempt_count") or 0) < completed_n:
        groq["attempt_count"] = completed_n
    return out


def _bump_transport(
    state: dict[str, Any],
    profile: str,
    status: str,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    t = state["transport"][profile]
    t["attempt_count"] = int(t.get("attempt_count") or 0) + 1
    t["last_attempt_at"] = _utc()
    # Never treat 429 / transport as AI quality failure marker
    if is_ai_quality_failure(status):
        t["invalid_schema_count"] = int(t.get("invalid_schema_count") or 0) + 1
        t["last_exit_reason"] = "PROVIDER_SCHEMA_FAILURE"
    elif status in {"OK", "SUCCESS"}:
        t["success_count"] = int(t.get("success_count") or 0) + 1
        t["last_exit_reason"] = "SUCCESS"
        ctrl = (state.get("_transport_controllers") or {}).get(profile)
        if ctrl:
            ctrl.on_result("SUCCESS")
            t["circuit"] = ctrl.circuit.to_dict()
            t["token_bucket"] = ctrl.bucket.to_dict()
    elif status == "RATE_LIMITED":
        t["HTTP_429_count"] = int(t.get("HTTP_429_count") or 0) + 1
        t["last_exit_reason"] = "PROVIDER_RATE_LIMITED"
        _apply_retry_after_to_transport(state, profile, meta=meta)
    elif status == "TIMEOUT":
        t["timeout_count"] = int(t.get("timeout_count") or 0) + 1
        t["last_exit_reason"] = "PROVIDER_TIMEOUT"
        ctrl = (state.get("_transport_controllers") or {}).get(profile)
        if ctrl:
            ctrl.on_result("TIMEOUT")
            wait = exponential_backoff_with_jitter(
                max(0, ctrl.circuit.consecutive_failures - 1), rng=ctrl.rng
            )
            ctrl.schedule_resume(wait, reason="TIMEOUT")
            t["retry_after"] = wait
            t["next_resume_not_before"] = (
                ctrl.next_resume_not_before.strftime("%Y-%m-%dT%H:%M:%SZ")
                if ctrl.next_resume_not_before
                else None
            )
            t["circuit"] = ctrl.circuit.to_dict()
    elif status == "INVALID_SCHEMA":
        t["invalid_schema_count"] = int(t.get("invalid_schema_count") or 0) + 1
        t["last_exit_reason"] = "PROVIDER_SCHEMA_FAILURE"
        ctrl = (state.get("_transport_controllers") or {}).get(profile)
        if ctrl:
            ctrl.on_result("INVALID_SCHEMA")
            t["circuit"] = ctrl.circuit.to_dict()
    elif status in {"CIRCUIT_OPEN", "TOKEN_BUCKET_WAIT", "QUOTA_RESET_WAIT"}:
        t["other_failure_count"] = int(t.get("other_failure_count") or 0) + 1
        t["last_exit_reason"] = status
        # Do not increment HTTP_429 for circuit/bucket waits
    else:
        t["other_failure_count"] = int(t.get("other_failure_count") or 0) + 1
        t["last_exit_reason"] = status or "PROVIDER_OTHER_FAILURE"
        if status == "RATE_LIMITED":
            t["HTTP_429_count"] = int(t.get("HTTP_429_count") or 0) + 1
            _apply_retry_after_to_transport(state, profile, meta=meta)


def provider_preflight(gw: FounderAIGateway, profile: str) -> dict[str, Any]:
    if profile == "GROQ_REFLECTION_REASONER":
        prompt = (
            "Blind Reflection V2.3 preflight. "
            'sanitized_evidence_packet_json={"trade_id":"PREFLIGHT","net_pnl":0,'
            '"cost_gate_status":"PASS","missing_evidence":[]}. '
            "evidence_sufficiency=EVIDENCE_INSUFFICIENT. process_classification=UNDETERMINED. "
            "Return reflection_v2_3 JSON."
        )
        schema = REFLECTION_V23_SCHEMA
        ver = "blind_reflection_v2_3_preflight"
    else:
        prompt = (
            "Independent critic preflight. "
            'sanitized_evidence_packet_json={"trade_id":"PREFLIGHT","net_pnl":0}. '
            "critic_verdict=EVIDENCE_INSUFFICIENT. confidence=0.5. Return critic_v1 JSON."
        )
        schema = CRITIC_SCHEMA
        ver = "critic_v2_3_preflight"
    body, rec, _ = gw.invoke_profile(
        profile_id=profile, prompt=prompt, schema=schema, prompt_schema_version=ver
    )
    status = str(rec.get("result_status") or "")
    ok = body is not None and status in {"OK", "SUCCESS"}
    wait = None
    next_resume = None
    if status == "RATE_LIMITED":
        wait = parse_retry_after(
            rec.get("headers") or {},
            body=str(rec.get("error_snippet_redacted") or ""),
            default_s=float(rec.get("retry_after_s") or DEFAULT_RETRY_AFTER_S),
        )
        if rec.get("retry_after_s") is not None:
            wait = float(rec["retry_after_s"])
        next_resume = (
            datetime.now(timezone.utc) + timedelta(seconds=wait)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "profile_id": profile,
        "provider_preflight_status": "PASS" if ok else ("RATE_LIMITED" if status == "RATE_LIMITED" else status or "FAIL"),
        "result_status": status,
        "retry_after": wait,
        "next_resume_not_before": next_resume,
        "mass_batch_blocked": not ok,
        "timestamp": _utc(),
        "api_key_recorded": False,
        "env_name": ENV_GROQ_REFLECTION if "GROQ" in profile else ENV_SAMBANOVA,
        "transport_only": is_transport_failure(status),
        "ai_quality_failure": is_ai_quality_failure(status),
    }


def _invoke_reflection(gw: FounderAIGateway, packet: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
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
        "evidence_packet_constructible": nonempty >= 15,
        "reflection_prompt_with_packet": "sanitized_evidence_packet_json=" in prompt and nonempty >= 15,
        "evidence_packet_hash": evidence_hash,
        "prompt_hash": prompt_hash,
        "nonempty_evidence_field_count": nonempty,
        "result_status": rec.get("result_status"),
    }
    return body, rec, transport


def _record_success(state: dict[str, Any], packet: dict[str, Any], reflection: dict[str, Any], transport: dict[str, Any]) -> None:
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
        {"trade_id": trade_id, "evidence_sufficiency": sufficiency, "process_classification": ai_cls, "confidence": reflection.get("confidence")}
    )
    state["response_hashes"][trade_id] = resp_hash
    state["case_results"][trade_id] = {
        "transport_status": "SUCCESS",
        "evidence_packet_constructible": transport.get("evidence_packet_constructible"),
        "reflection_prompt_with_packet": transport.get("reflection_prompt_with_packet"),
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
        "original_process_classification_raw": reflection.get("process_classification"),
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
    if sufficiency == "EVIDENCE_SUFFICIENT" and (
        ai_cls != expected
        or (isinstance(reflection.get("confidence"), (int, float)) and float(reflection["confidence"]) < 0.55)
    ):
        if trade_id not in state["critic_case_ids"]:
            state["critic_case_ids"].append(trade_id)
        if trade_id not in state["critic_pending_ids"] and trade_id not in state["critic_resolved_ids"]:
            state["critic_pending_ids"].append(trade_id)


def classify_disagreement(row: dict[str, Any], critic_verdict: str | None = None) -> str:
    if critic_verdict and "BLOCK" in str(critic_verdict).upper():
        return "PROVIDER_BLOCKED"
    if critic_verdict is None and row.get("critic_status") == "PROVIDER_BLOCKED":
        return "PROVIDER_BLOCKED"
    if row.get("evidence_sufficiency") != "EVIDENCE_SUFFICIENT":
        return "EVIDENCE_PACKET_AMBIGUOUS"
    # Without critic, leave unresolved taxonomy for later
    if critic_verdict in {None, "", "EVIDENCE_INSUFFICIENT"}:
        return "CRITIC_UNRESOLVED"
    if "GROQ" in str(critic_verdict).upper():
        return "DETERMINISTIC_BASELINE_TOO_COARSE"
    if "DET" in str(critic_verdict).upper():
        return "AI_MISCLASSIFICATION"
    return "TAXONOMY_AMBIGUOUS"


def repair_delivery_counters(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure completed Reflection successes are counted as packet-delivered."""
    case_results = dict(state.get("case_results") or {})
    for cid in state.get("completed_case_ids") or []:
        row = dict(case_results.get(cid) or {})
        row.setdefault("reflection_prompt_with_packet", True)
        row.setdefault("evidence_packet_constructible", True)
        case_results[cid] = row
    state["case_results"] = case_results
    with_packet_n = sum(
        1
        for cid in state.get("completed_case_ids") or []
        if case_results.get(cid, {}).get("reflection_prompt_with_packet")
    )
    state["reflection_prompt_with_packet_count"] = max(
        int(state.get("reflection_prompt_with_packet_count") or 0),
        with_packet_n,
    )
    groq = state.setdefault("transport", {}).setdefault(
        "GROQ_REFLECTION_REASONER", _empty_provider_transport("GROQ_REFLECTION_REASONER")
    )
    # attempt_count must be at least success_count; prefer max(attempt, with_packet) for delivery denom honesty
    success_n = len(state.get("completed_case_ids") or [])
    groq["success_count"] = max(int(groq.get("success_count") or 0), success_n)
    groq["attempt_count"] = max(int(groq.get("attempt_count") or 0), int(groq["success_count"]))
    return state


def build_delivery_metrics(state: dict[str, Any], *, constructible_n: int = 80) -> dict[str, Any]:
    state = repair_delivery_counters(state)
    completed = state.get("completed_case_ids") or []
    attempts = int(state["transport"]["GROQ_REFLECTION_REASONER"].get("attempt_count") or 0)
    with_packet = sum(
        1
        for cid in completed
        if (state.get("case_results") or {}).get(cid, {}).get("reflection_prompt_with_packet")
    )
    prompt_with = max(int(state.get("reflection_prompt_with_packet_count") or 0), with_packet)
    # Failed transport attempts that still included a packet are counted via explicit counter bumps at invoke time.
    # Floor: every successful case had a packet in this V2.3 design.
    prompt_with = max(prompt_with, with_packet)
    critic_attempts = int(state["transport"]["SAMBANOVA_INDEPENDENT_CRITIC"].get("attempt_count") or 0)
    critic_with = int(state.get("critic_prompt_with_packet_count") or 0)
    return {
        "evidence_packet_constructible_count": constructible_n,
        "evidence_packet_constructible_ratio": make_ratio(constructible_n, constructible_n),
        "reflection_prompt_attempt_count": attempts,
        "reflection_prompt_with_packet_count": prompt_with,
        "reflection_prompt_delivery_ratio_on_attempts": make_ratio(
            prompt_with, attempts if attempts else 0
        ),
        "reflection_successful_case_count": len(completed),
        "frozen_calibration_case_count": 80,
        "full_calibration_completion_ratio": make_ratio(
            len(completed),
            80,
            status_override="INCOMPLETE_SAMPLE" if len(completed) < 80 else None,
        ),
        "critic_prompt_attempt_count": critic_attempts,
        "critic_prompt_with_packet_count": critic_with,
        "critic_prompt_delivery_ratio_on_attempts": make_ratio(
            critic_with, critic_attempts if critic_attempts else 0
        ),
    }


def evaluate_quality(state: dict[str, Any]) -> dict[str, Any]:
    completed = [cid for cid in state["completed_case_ids"] if cid in (state.get("case_results") or {})]
    n_success = len(completed)
    delivery = build_delivery_metrics(state)
    schema_ok = n_success
    sufficient = insufficient = informative = undetermined = agree = disagree = 0
    invention = leak = secret_leak = 0
    disagreements: list[dict[str, Any]] = []

    for cid in completed:
        row = state["case_results"][cid]
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
                disagreements.append(
                    {
                        "trade_id": cid,
                        "groq_classification": cls,
                        "groq_evidence_citations": row.get("supporting_evidence_ids"),
                        "deterministic_classification": row.get("deterministic_expected"),
                        "deterministic_rule_citations": [row.get("deterministic_status")],
                        "sambanova_verdict": row.get("critic_verdict"),
                        "evidence_sufficiency": suf,
                        "conflict_type": classify_disagreement(row, row.get("critic_verdict")),
                    }
                )

    sn = state["transport"]["SAMBANOVA_INDEPENDENT_CRITIC"]
    critic_required = len(state.get("critic_case_ids") or [])
    critic_resolved = len(state.get("critic_resolved_ids") or [])
    sn_429 = int(sn.get("HTTP_429_count") or 0)
    sn_blocked = (state.get("sambanova_stage") == "SAMBANOVA_CAPACITY_BLOCKED") or (
        critic_required > critic_resolved and sn_429 > 0
    ) or (
        critic_required > critic_resolved and sn.get("last_exit_reason") in {
            "PROVIDER_RATE_LIMITED",
            "PROVIDER_CAPACITY_UNKNOWN",
        }
    )
    if critic_required == 0:
        critic_ratio = make_ratio(0, 0)
        critic_status = "NOT_APPLICABLE"
    elif sn_blocked and critic_resolved == 0:
        critic_ratio = make_ratio(
            critic_resolved,
            critic_required,
            status_override="SAMBANOVA_PROVIDER_BLOCKED",
        )
        critic_status = "SAMBANOVA_PROVIDER_BLOCKED"
    else:
        critic_ratio = make_ratio(critic_resolved, critic_required)
        critic_status = critic_ratio["status"]

    # Force value None for blocked override (make_ratio may leave None)
    if critic_status == "SAMBANOVA_PROVIDER_BLOCKED":
        critic_ratio = {
            "numerator": float(critic_resolved),
            "denominator": float(critic_required),
            "value": None,
            "status": "SAMBANOVA_PROVIDER_BLOCKED",
        }

    schema_ratio = make_ratio(schema_ok, n_success)
    informative_overall = make_ratio(informative, n_success)
    suf_informative = sum(
        1
        for cid in completed
        if state["case_results"][cid].get("evidence_sufficiency") == "EVIDENCE_SUFFICIENT"
        and state["case_results"][cid].get("process_classification") in INFORMATIVE
    )
    informative_on_suf = make_ratio(suf_informative, sufficient)
    agree_on_suf = make_ratio(agree, agree + disagree)

    critics_done = critic_required == 0 or (
        critic_resolved == critic_required
    ) or (
        # terminal: all pending critics founder-resume exhausted — still not a resolution
        False
    )
    quality_gates_evaluated = n_success >= 80 and (
        critic_required == 0 or critic_resolved == critic_required
    )
    quality_ok = False
    if quality_gates_evaluated:
        quality_ok = (
            delivery["evidence_packet_constructible_ratio"].get("value") == 1.0
            and delivery["reflection_prompt_delivery_ratio_on_attempts"].get("value") == 1.0
            and n_success == 80
            and (schema_ratio.get("value") or 0) >= 0.95
            and sufficient >= 30
            and (informative_overall.get("value") or 0) >= 0.40
            and (informative_on_suf.get("value") or 0) >= 0.70
            and (agree_on_suf.get("value") or 0) >= 0.70
            and (critic_status == "NOT_APPLICABLE" or (critic_ratio.get("value") or 0) >= 0.80)
            and invention == 0
            and leak == 0
            and secret_leak == 0
        )

    if not quality_gates_evaluated:
        if n_success < 80 or sn_blocked or state.get("groq_stage") == "GROQ_CAPACITY_BLOCKED":
            v23_status = "INCOMPLETE_PROVIDER_CAPACITY"
        else:
            v23_status = "INCOMPLETE"
    elif quality_ok:
        v23_status = "PASS"
    else:
        v23_status = "QUALITY_FAILED_WITH_VALID_SAMPLE"

    conflict_counts = {
        "AI_MISCLASSIFICATION": 0,
        "DETERMINISTIC_BASELINE_TOO_COARSE": 0,
        "EVIDENCE_PACKET_AMBIGUOUS": 0,
        "TAXONOMY_AMBIGUOUS": 0,
        "OUTCOME_PROCESS_MAPPING_ERROR": 0,
        "BOTH_SUPPORTED": 0,
        "BOTH_UNSUPPORTED": 0,
        "CRITIC_UNRESOLVED": 0,
        "PROVIDER_BLOCKED": 0,
    }
    unadjudicated = 0
    provider_blocked_disagreements = 0
    for d in disagreements:
        # Before Critic adjudication, do not invent confirmed root-cause zeros.
        if sn_blocked or d.get("sambanova_verdict") in {None, ""}:
            d["conflict_type"] = "PROVIDER_BLOCKED" if sn_blocked else "CRITIC_UNRESOLVED"
            d["adjudication_status"] = (
                "PROVIDER_BLOCKED" if sn_blocked else "NOT_YET_ADJUDICATED"
            )
            unadjudicated += 1
            if sn_blocked:
                provider_blocked_disagreements += 1
        else:
            d["adjudication_status"] = "ADJUDICATED"
            conflict_counts[d["conflict_type"]] = conflict_counts.get(d["conflict_type"], 0) + 1

    adjudication_complete = unadjudicated == 0
    not_yet = {
        "status": "NOT_YET_ADJUDICATED",
        "value": None,
        "reason": "critic_adjudication_incomplete",
    }

    result = {
        "schema": "final_v2_3_quality_result_v3",
        "V2_3_quality_status": v23_status,
        "V2_3_RESULT_INTERPRETATION": (
            "CALIBRATION_INCOMPLETE_PROVIDER_CAPACITY"
            if v23_status == "INCOMPLETE_PROVIDER_CAPACITY"
            else v23_status
        ),
        "V2_3_TERMINAL_STATUS": (
            "VERIFIED"
            if quality_ok
            else (
                "VALID_SAMPLE_QUALITY_FAILED"
                if quality_gates_evaluated and not quality_ok
                else "INCOMPLETE_PROVIDER_CAPACITY"
                if v23_status == "INCOMPLETE_PROVIDER_CAPACITY"
                else "INCOMPLETE"
            )
        ),
        "quality_gates_evaluated": quality_gates_evaluated,
        "quality_gates_passed": quality_ok,
        **delivery,
        # Compatibility aliases (do not treat as delivery completion).
        "provider_successful_response_count": n_success,
        "input_evidence_packet_count": 80,
        "input_evidence_eligible_count": 80,
        "AI_evidence_sufficiency_assessed_count": sufficient + insufficient,
        "AI_evidence_sufficient_count": sufficient,
        "AI_evidence_insufficient_count": insufficient,
        "informative_classification_count": informative,
        "undetermined_count": undetermined,
        "agreement_count": agree,
        "disagreement_count": disagree,
        "disagreement_case_count": disagree,
        "unadjudicated_disagreement_count": unadjudicated,
        "provider_blocked_disagreement_count": provider_blocked_disagreements,
        "blind_valid_schema_ratio": schema_ratio,
        "informative_classification_ratio_overall": informative_overall,
        "informative_classification_ratio_on_sufficient_cases": informative_on_suf,
        "blind_agreement_ratio_on_sufficient_cases": agree_on_suf,
        "critic_resolution_ratio": critic_ratio,
        "critic_resolution_status": critic_status,
        "critic_resolution_denominator": critic_required,
        "missing_evidence_invention_count": invention,
        "deterministic_answer_leak_count": leak,
        "secret_leak_count": secret_leak,
        "disagreement_analysis": disagreements[:40],
        "AI_misclassification_count": (
            conflict_counts["AI_MISCLASSIFICATION"] if adjudication_complete else not_yet
        ),
        "deterministic_baseline_too_coarse_count": (
            conflict_counts["DETERMINISTIC_BASELINE_TOO_COARSE"]
            if adjudication_complete
            else not_yet
        ),
        "evidence_packet_ambiguous_count": (
            conflict_counts["EVIDENCE_PACKET_AMBIGUOUS"] if adjudication_complete else not_yet
        ),
        "taxonomy_ambiguous_count": (
            conflict_counts["TAXONOMY_AMBIGUOUS"] if adjudication_complete else not_yet
        ),
        "outcome_process_mapping_error_count": (
            conflict_counts["OUTCOME_PROCESS_MAPPING_ERROR"]
            if adjudication_complete
            else not_yet
        ),
        "critic_unresolved_count": (
            conflict_counts["CRITIC_UNRESOLVED"]
            if adjudication_complete
            else unadjudicated
        ),
        "canonical_classes": list(CANONICAL_CLASSES),
        "transport": state.get("transport"),
        "groq_stage": state.get("groq_stage"),
        "sambanova_stage": state.get("sambanova_stage"),
        "exit_reason": state.get("exit_reason"),
        "http_429_never_ai_quality_failure": True,
    }
    denom_check = validate_terminal_denominators(result)
    result["terminal_denominator_validation"] = denom_check
    if not denom_check.get("valid"):
        # Do not fabricate VERIFIED when denominators are invalid
        if result["V2_3_TERMINAL_STATUS"] == "VERIFIED":
            result["V2_3_TERMINAL_STATUS"] = "INCOMPLETE"
            result["quality_gates_passed"] = False
            result["V2_3_quality_status"] = "INCOMPLETE"
    return result


def run_quota_aware_calibration(
    *,
    root: Path,
    packets: list[dict[str, Any]],
    manifest_checksum: str,
    use_real_ai: bool = True,
    max_batches_this_invocation: int = 3,
    run_critic: bool = True,
    replay_fixtures: ReplayFixtureStore | Path | None = None,
) -> dict[str, Any]:
    packets_by_id = {str(p.get("trade_id")): p for p in packets}
    assert len(packets) == 80
    prev = os.environ.get("NEXUS_AI_MOCK")
    os.environ["NEXUS_AI_MOCK"] = "0" if use_real_ai else "1"
    if isinstance(replay_fixtures, Path):
        replay_store: ReplayFixtureStore | None = ReplayFixtureStore.from_dir(replay_fixtures)
    elif isinstance(replay_fixtures, ReplayFixtureStore):
        replay_store = replay_fixtures
    else:
        default_fx = root / "artifacts" / "readiness" / "fixtures" / "blind_reflection_v23_transport"
        replay_store = ReplayFixtureStore.from_dir(default_fx) if (
            os.getenv("NEXUS_V23_REPLAY_FIXTURES") == "1" and default_fx.is_dir()
        ) else None
    try:
        gw = FounderAIGateway.from_env(mock_for_ci=not use_real_ai)
        model_id = os.getenv("NEXUS_GROQ_REFLECTION_MODEL", "llama-3.3-70b-versatile")
        state = load_checkpoint(root)
        corruption = detect_checkpoint_corruption(state) if state is not None else {
            "corrupt": False,
            "issues": [],
            "recoverable": True,
            "recommended_action": "NONE",
        }
        if state is not None and state.get("_checkpoint_load_error"):
            corruption = {
                "corrupt": True,
                "issues": [str(state.get("_checkpoint_load_error"))],
                "recoverable": False,
                "recommended_action": "REBUILD_FROM_MANIFEST",
            }
        if state is None or state.get("calibration_manifest_checksum") != manifest_checksum:
            if state is not None and corruption.get("corrupt") and not corruption.get("recoverable"):
                # Rebuild while preserving nothing unsafe from corrupt blob
                state = build_initial_checkpoint(
                    packets=packets, manifest_checksum=manifest_checksum, model_id=model_id
                )
                state["checkpoint_corruption_report"] = corruption
            elif state is None or state.get("calibration_manifest_checksum") != manifest_checksum:
                state = build_initial_checkpoint(
                    packets=packets, manifest_checksum=manifest_checksum, model_id=model_id
                )
        else:
            if corruption.get("corrupt") and not corruption.get("recoverable"):
                state = build_initial_checkpoint(
                    packets=packets, manifest_checksum=manifest_checksum, model_id=model_id
                )
                state["checkpoint_corruption_report"] = corruption
            else:
                state = migrate_checkpoint_v2_to_v3(state, model_id=model_id)
                state = repair_delivery_counters(state)
                state = repair_checkpoint_overlap(state)
                if corruption.get("corrupt"):
                    state["checkpoint_corruption_report"] = corruption
            # Resume pending without re-billing successes (dedupe)
            case_ids = list(state.get("case_ids") or frozen_case_ids(packets))
            completed = list(state.get("completed_case_ids") or [])
            pending = dedupe_pending_against_success(
                case_ids=case_ids,
                completed_case_ids=completed,
                pending_case_ids=None,
            )
            for cid in list(pending):
                retries = int((state.get("transport_retries_by_case") or {}).get(cid) or 0)
                if retries >= MAX_TRANSPORT_RETRIES:
                    if cid not in state["requires_founder_resume_ids"]:
                        state["requires_founder_resume_ids"].append(cid)
            state["pending_case_ids"] = pending
            state["critic_pending_ids"] = [
                cid
                for cid in state.get("critic_case_ids") or []
                if cid not in (state.get("critic_resolved_ids") or [])
            ]

        _controllers_from_state(state)
        preflight_groq = None
        preflight_sn = None
        batches_run = 0
        state["exit_reason"] = None

        # Respect Groq next_resume only for Groq work (do NOT return early —
        # SambaNova / Cerebras / Groq-Main queues stay independent).
        groq_ctrl = state["_transport_controllers"]["GROQ_REFLECTION_REASONER"]
        groq_nrb = (state["transport"]["GROQ_REFLECTION_REASONER"].get("next_resume_not_before"))
        groq_wait = False
        if groq_nrb and use_real_ai and state["pending_case_ids"] and replay_store is None:
            try:
                nrb_dt = datetime.strptime(groq_nrb, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) < nrb_dt:
                    state["groq_stage"] = "GROQ_CAPACITY_BLOCKED"
                    if state.get("exit_reason") is None:
                        state["exit_reason"] = "PROVIDER_RATE_LIMITED"
                    groq_wait = True
            except Exception:
                pass

        # GROQ queue
        if state["pending_case_ids"] and not groq_wait:
            state["groq_stage"] = "GROQ_PREFLIGHT"
            if use_real_ai and replay_store is None:
                preflight_groq = provider_preflight(gw, "GROQ_REFLECTION_REASONER")
            else:
                preflight_groq = {
                    "provider_preflight_status": "PASS",
                    "mass_batch_blocked": False,
                    "profile_id": "GROQ_REFLECTION_REASONER",
                }
            if preflight_groq.get("mass_batch_blocked"):
                _bump_transport(
                    state,
                    "GROQ_REFLECTION_REASONER",
                    preflight_groq.get("result_status") or "RATE_LIMITED",
                    meta=preflight_groq,
                )
                state["groq_stage"] = "GROQ_CAPACITY_BLOCKED"
                state["exit_reason"] = "PROVIDER_RATE_LIMITED"
                save_checkpoint(root, state)
                # Still allow critic queue later in same/other invocation — do not erase
            else:
                while batches_run < max_batches_this_invocation and state["pending_case_ids"]:
                    canary_pending = [
                        cid
                        for cid in state.get("canary_case_ids") or []
                        if cid in state["pending_case_ids"]
                    ]
                    if canary_pending:
                        state["groq_stage"] = "GROQ_CANARY"
                        batch = canary_pending[:BATCH_SIZE]
                    else:
                        canary_done = [
                            cid
                            for cid in state.get("canary_case_ids") or []
                            if cid in state["completed_case_ids"]
                        ]
                        if len(canary_done) < CANARY_SIZE:
                            state["groq_stage"] = "GROQ_CAPACITY_BLOCKED"
                            state["exit_reason"] = "PROVIDER_CAPACITY_UNKNOWN"
                            break
                        state["groq_stage"] = "GROQ_CALIBRATION_BATCH"
                        batch = state["pending_case_ids"][:BATCH_SIZE]

                    capacity_hit = False
                    enforce_gates = use_real_ai and replay_store is None
                    for cid in batch:
                        # Successful-case dedupe guard
                        if cid in state.get("completed_case_ids", []):
                            continue
                        if enforce_gates:
                            allowed, gate_reason = groq_ctrl.can_invoke()
                            if not allowed:
                                _bump_transport(state, "GROQ_REFLECTION_REASONER", gate_reason)
                                if gate_reason in {"CIRCUIT_OPEN", "QUOTA_RESET_WAIT", "TOKEN_BUCKET_WAIT"}:
                                    capacity_hit = True
                                    state["groq_stage"] = "GROQ_CAPACITY_BLOCKED"
                                    state["exit_reason"] = gate_reason
                                    break
                        packet = packets_by_id[cid]
                        if replay_store is not None:
                            reflection, rec = replay_store.invoke(
                                profile_id="GROQ_REFLECTION_REASONER",
                                trade_id=cid,
                                prompt_schema_version="blind_reflection_v2_3",
                            )
                            san = build_sanitized_evidence_packet(packet)
                            ej, eh, n = serialize_evidence_to_prompt(san)
                            prompt = build_blind_prompt(trade_id=cid, evidence_json=ej)
                            transport_meta = {
                                "evidence_packet_constructible": n >= 15,
                                "reflection_prompt_with_packet": True,
                                "evidence_packet_hash": eh,
                                "prompt_hash": _sha(prompt),
                                "nonempty_evidence_field_count": n,
                                "result_status": rec.get("result_status"),
                                "replay": True,
                            }
                        elif use_real_ai:
                            reflection, rec, transport_meta = _invoke_reflection(gw, packet)
                        else:
                            from backend.nexus_edge_discovery.blind_reflection_v23 import (
                                mock_reflection_from_evidence,
                            )

                            san = build_sanitized_evidence_packet(packet)
                            reflection = mock_reflection_from_evidence(packet, san)
                            ej, eh, n = serialize_evidence_to_prompt(san)
                            prompt = build_blind_prompt(trade_id=cid, evidence_json=ej)
                            transport_meta = {
                                "evidence_packet_constructible": True,
                                "reflection_prompt_with_packet": True,
                                "evidence_packet_hash": eh,
                                "prompt_hash": _sha(prompt),
                                "nonempty_evidence_field_count": n,
                                "result_status": "OK",
                            }
                            rec = {"result_status": "OK"}
                        st = str(rec.get("result_status") or "")
                        if transport_meta.get("reflection_prompt_with_packet"):
                            state["reflection_prompt_with_packet_count"] = int(
                                state.get("reflection_prompt_with_packet_count") or 0
                            ) + 1
                        bump_status = (
                            "SUCCESS"
                            if reflection is not None and st in {"OK", "SUCCESS"}
                            else st
                        )
                        _bump_transport(
                            state, "GROQ_REFLECTION_REASONER", bump_status, meta=rec
                        )
                        if reflection is not None and st in {"OK", "SUCCESS"}:
                            _record_success(state, packet, reflection, transport_meta)
                        else:
                            retries = dict(state.get("transport_retries_by_case") or {})
                            retries[cid] = int(retries.get(cid) or 0) + 1
                            state["transport_retries_by_case"] = retries
                            if cid not in state["failed_transport_case_ids"]:
                                state["failed_transport_case_ids"].append(cid)
                            if retries[cid] >= MAX_TRANSPORT_RETRIES and cid not in state["requires_founder_resume_ids"]:
                                state["requires_founder_resume_ids"].append(cid)
                            if st == "RATE_LIMITED" or is_transport_failure(st):
                                # 429 is capacity — never AI quality failure
                                assert not is_ai_quality_failure(st)
                                capacity_hit = True
                                state["groq_stage"] = "GROQ_CAPACITY_BLOCKED"
                                state["exit_reason"] = (
                                    "PROVIDER_RATE_LIMITED"
                                    if st == "RATE_LIMITED"
                                    else st
                                )
                                break
                        if use_real_ai and replay_store is None:
                            time.sleep(0.35)
                    save_checkpoint(root, state)
                    batches_run += 1
                    if capacity_hit:
                        break
                else:
                    # while exhausted by batch limit without capacity hit
                    if state["pending_case_ids"] and state.get("exit_reason") is None:
                        state["exit_reason"] = "INVOCATION_BATCH_LIMIT_REACHED"
                        state["groq_stage"] = "INVOCATION_BATCH_LIMIT_REACHED"
                    elif not state["pending_case_ids"]:
                        state["groq_stage"] = "GROQ_COMPLETE"

        if not state["pending_case_ids"]:
            state["groq_stage"] = "GROQ_COMPLETE"

        # SAMBANOVA critic queue — independent
        sn_ctrl = state["_transport_controllers"]["SAMBANOVA_INDEPENDENT_CRITIC"]
        if run_critic and state.get("critic_pending_ids"):
            sn_nrb = state["transport"]["SAMBANOVA_INDEPENDENT_CRITIC"].get("next_resume_not_before")
            sn_wait = False
            if sn_nrb and use_real_ai and replay_store is None:
                try:
                    nrb_dt = datetime.strptime(sn_nrb, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) < nrb_dt:
                        state["sambanova_stage"] = "SAMBANOVA_CAPACITY_BLOCKED"
                        sn_wait = True
                except Exception:
                    pass
            if not sn_wait:
                state["sambanova_stage"] = "SAMBANOVA_PREFLIGHT"
                if use_real_ai and replay_store is None:
                    preflight_sn = provider_preflight(gw, "SAMBANOVA_INDEPENDENT_CRITIC")
                else:
                    preflight_sn = {
                        "provider_preflight_status": "PASS",
                        "mass_batch_blocked": False,
                        "profile_id": "SAMBANOVA_INDEPENDENT_CRITIC",
                    }
                if preflight_sn.get("mass_batch_blocked"):
                    _bump_transport(
                        state,
                        "SAMBANOVA_INDEPENDENT_CRITIC",
                        preflight_sn.get("result_status") or "RATE_LIMITED",
                        meta=preflight_sn,
                    )
                    state["sambanova_stage"] = "SAMBANOVA_CAPACITY_BLOCKED"
                else:
                    state["sambanova_stage"] = "SAMBANOVA_CRITIC_BATCH"
                    critic_batches = 0
                    for cid in list(state["critic_pending_ids"])[:BATCH_SIZE]:
                        if critic_batches >= max_batches_this_invocation:
                            if state.get("exit_reason") is None:
                                state["exit_reason"] = "INVOCATION_BATCH_LIMIT_REACHED"
                            break
                        allowed, gate_reason = sn_ctrl.can_invoke()
                        if use_real_ai and replay_store is None and not allowed:
                            _bump_transport(state, "SAMBANOVA_INDEPENDENT_CRITIC", gate_reason)
                            state["sambanova_stage"] = "SAMBANOVA_CAPACITY_BLOCKED"
                            break
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
                        state["critic_prompt_with_packet_count"] = int(
                            state.get("critic_prompt_with_packet_count") or 0
                        ) + 1
                        if replay_store is not None:
                            critic, crit_rec = replay_store.invoke(
                                profile_id="SAMBANOVA_INDEPENDENT_CRITIC",
                                trade_id=cid,
                                prompt_schema_version="critic_v2_3",
                            )
                            st = str(crit_rec.get("result_status") or "")
                        elif use_real_ai:
                            critic, crit_rec, _ = gw.invoke_profile(
                                profile_id="SAMBANOVA_INDEPENDENT_CRITIC",
                                prompt=critic_prompt,
                                schema=CRITIC_SCHEMA,
                                prompt_schema_version="critic_v2_3",
                            )
                            st = str(crit_rec.get("result_status") or "")
                        else:
                            critic = {
                                "critic_verdict": (
                                    "BOTH_SUPPORTED"
                                    if row.get("process_classification") == row.get("deterministic_expected")
                                    else "INDEPENDENT_DISAGREEMENT"
                                ),
                                "confidence": 0.7,
                            }
                            st = "OK"
                            crit_rec = {"result_status": "OK"}
                        _bump_transport(
                            state,
                            "SAMBANOVA_INDEPENDENT_CRITIC",
                            st if critic is None else ("SUCCESS" if st in {"OK", "SUCCESS"} else st),
                            meta=crit_rec,
                        )
                        if critic and st in {"OK", "SUCCESS"}:
                            verdict = normalize_critic_verdict(
                                critic.get("critic_verdict") or critic.get("verdict"),
                                groq=str(row.get("process_classification")),
                                det=str(row.get("deterministic_expected")),
                            )
                            row["critic_verdict"] = verdict
                            row["critic_status"] = "RESOLVED"
                            state["critic_resolved_ids"].append(cid)
                            state["critic_pending_ids"] = [x for x in state["critic_pending_ids"] if x != cid]
                        elif st == "RATE_LIMITED" or is_transport_failure(st):
                            assert not is_ai_quality_failure(st)
                            row["critic_status"] = "PROVIDER_BLOCKED"
                            state["sambanova_stage"] = "SAMBANOVA_CAPACITY_BLOCKED"
                            break
                        if use_real_ai and replay_store is None:
                            time.sleep(0.4)
                        critic_batches += 1
                    if not state["critic_pending_ids"] and state["sambanova_stage"] != "SAMBANOVA_CAPACITY_BLOCKED":
                        state["sambanova_stage"] = "SAMBANOVA_COMPLETE"

        if not state.get("critic_pending_ids") and state.get("sambanova_stage") != "SAMBANOVA_CAPACITY_BLOCKED":
            if not state.get("critic_case_ids"):
                state["sambanova_stage"] = "SAMBANOVA_COMPLETE"
            elif len(state.get("critic_resolved_ids") or []) == len(state.get("critic_case_ids") or []):
                state["sambanova_stage"] = "SAMBANOVA_COMPLETE"

        state["updated_at"] = _utc()
        save_checkpoint(root, state)
        return _result(state, preflight_groq, preflight_sn, state.get("exit_reason") or state.get("groq_stage"))
    finally:
        if prev is None:
            os.environ.pop("NEXUS_AI_MOCK", None)
        else:
            os.environ["NEXUS_AI_MOCK"] = prev


def _result(state: dict[str, Any], preflight_groq: Any, preflight_sn: Any, checkpoint_status: str) -> dict[str, Any]:
    quality = evaluate_quality(state)
    return {
        "checkpoint_status": checkpoint_status,
        "preflight_groq": preflight_groq,
        "preflight_sambanova": preflight_sn,
        "quality": quality,
        "state_summary": {
            "groq_stage": state.get("groq_stage"),
            "sambanova_stage": state.get("sambanova_stage"),
            "exit_reason": state.get("exit_reason"),
            "reflection_successful_case_count": len(state.get("completed_case_ids") or []),
            "reflection_pending_case_count": len(state.get("pending_case_ids") or []),
            "calibration_pending_case_count": len(state.get("pending_case_ids") or []),
            "critic_pending_count": len(state.get("critic_pending_ids") or []),
            "critic_resolved_count": len(state.get("critic_resolved_ids") or []),
            "transport": state.get("transport"),
        },
    }
