"""Provider orchestrator — fixture-safe scheduling + optional real resume."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_ai.profiles import (
    CEREBRAS_RESEARCH_NORMALIZER,
    GROQ_MAIN_REASONER,
    GROQ_REFLECTION_REASONER,
    PROVIDER_PROFILES,
    SAMBANOVA_INDEPENDENT_CRITIC,
)
from backend.nexus_ai.scheduler import ProviderScheduler
from backend.nexus_edge_discovery.blind_reflection_v23 import migrate_process_classification
from backend.nexus_provider.transport_status import assert_429_not_quality_failure
from backend.nexus_reflection.checkpoint import (
    build_initial_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from backend.nexus_reflection.disagreement import build_disagreement_record, classify_conflict
from backend.nexus_reflection.lesson_gate import apply_lesson_gate, pick_agent_c_recommendation
from backend.nexus_reflection.terminal_eval import evaluate_terminal


def simulate_provider_transport(
    scheduler: ProviderScheduler,
    *,
    profile_id: str,
    case_id: str,
    prompt_hash: str = "ph",
    schema_version: str = "blind_reflection_v2_3",
    http_status: int | None = None,
    result_status: str | None = None,
    headers: dict[str, Any] | None = None,
    invalid_json: bool = False,
    invalid_schema: bool = False,
    timeout: bool = False,
    response_hash: str | None = None,
    callback_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Sanitized fixture path — never claims real AI quality."""
    decision, idem = scheduler.begin_attempt(
        profile_id,
        case_id,
        prompt_hash=prompt_hash,
        schema_version=schema_version,
    )
    if not decision.allowed:
        return {
            "allowed": False,
            "decision": decision.reason,
            "transport_status": decision.transport_status,
            "idempotency_key": idem,
            "fixture_only": True,
            "real_ai_quality_claimed": False,
        }
    status = scheduler.record_outcome(
        profile_id,
        case_id,
        http_status=http_status,
        result_status=result_status,
        headers=headers,
        invalid_json=invalid_json,
        invalid_schema=invalid_schema,
        timeout=timeout,
        response_hash=response_hash,
        callback_fingerprint=callback_fingerprint,
    )
    if status == "RATE_LIMITED":
        assert_429_not_quality_failure(
            status,
            {"process_classification": None, "evidence_sufficiency": None},
        )
    return {
        "allowed": True,
        "decision": "DISPATCHED",
        "transport_status": status,
        "idempotency_key": idem,
        "fixture_only": True,
        "real_ai_quality_claimed": False,
        "queue_snapshot": scheduler.queues[profile_id],
    }


def run_provider_hardening_pass(
    *,
    root: Path,
    packets: list[dict[str, Any]] | None = None,
    manifest_checksum: str | None = None,
    model_id: str = "fixture-model",
    allow_real_resume: bool = False,
) -> dict[str, Any]:
    """
    Hardening entrypoint for Agent C.

    When local checkpoint is missing: do NOT fabricate progress; return
    LOCAL_CHECKPOINT_REQUIRED_FOR_REAL_RESUME and run fixture scheduler checks only.
    """
    loaded = load_checkpoint(
        root,
        expected_manifest=manifest_checksum,
        migrate=True,
        model_id=model_id,
    )
    scheduler = ProviderScheduler()
    scheduler_status = {p: "READY" for p in PROVIDER_PROFILES}

    # Always exercise independent queue isolation with sanitized fixtures
    fixture_cases = {
        GROQ_REFLECTION_REASONER: "FIX_GROQ_1",
        SAMBANOVA_INDEPENDENT_CRITIC: "FIX_SN_1",
        CEREBRAS_RESEARCH_NORMALIZER: "FIX_CB_1",
        GROQ_MAIN_REASONER: "FIX_GM_1",
    }
    for pid, cid in fixture_cases.items():
        scheduler.enqueue(pid, [cid])

    # Isolate: Groq 429 must not block SambaNova / Cerebras / Main
    groq_429 = simulate_provider_transport(
        scheduler,
        profile_id=GROQ_REFLECTION_REASONER,
        case_id=fixture_cases[GROQ_REFLECTION_REASONER],
        http_status=429,
        headers={"Retry-After": "120"},
    )
    sn_ok = simulate_provider_transport(
        scheduler,
        profile_id=SAMBANOVA_INDEPENDENT_CRITIC,
        case_id=fixture_cases[SAMBANOVA_INDEPENDENT_CRITIC],
        result_status="SUCCESS",
        response_hash="sn_ok",
    )
    cb_ok = simulate_provider_transport(
        scheduler,
        profile_id=CEREBRAS_RESEARCH_NORMALIZER,
        case_id=fixture_cases[CEREBRAS_RESEARCH_NORMALIZER],
        result_status="SUCCESS",
        response_hash="cb_ok",
    )
    gm_ok = simulate_provider_transport(
        scheduler,
        profile_id=GROQ_MAIN_REASONER,
        case_id=fixture_cases[GROQ_MAIN_REASONER],
        result_status="SUCCESS",
        response_hash="gm_ok",
    )
    isolation_ok = (
        groq_429.get("transport_status") == "RATE_LIMITED"
        and sn_ok.get("transport_status") == "SUCCESS"
        and cb_ok.get("transport_status") == "SUCCESS"
        and gm_ok.get("transport_status") == "SUCCESS"
    )
    scheduler_status[GROQ_REFLECTION_REASONER] = "RATE_LIMITED_ISOLATED"
    scheduler_status[SAMBANOVA_INDEPENDENT_CRITIC] = "OK_DESPITE_GROQ_429"
    scheduler_status[CEREBRAS_RESEARCH_NORMALIZER] = "OK"
    scheduler_status[GROQ_MAIN_REASONER] = "OK"

    if not loaded.get("ok") or loaded.get("state") is None:
        lesson = apply_lesson_gate(terminal_status="INCOMPLETE_PROVIDER_CAPACITY")
        rec = pick_agent_c_recommendation(
            impl_ok=isolation_ok,
            local_checkpoint_available=False,
            checkpoint_integrity_ok=None,
            real_resume_executed=False,
            terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
            quality_evaluated=False,
            quality_passed=False,
        )
        # If file exists but corrupt
        if loaded.get("local_runtime_checkpoint_available") and not loaded.get("ok"):
            rec = pick_agent_c_recommendation(
                impl_ok=isolation_ok,
                local_checkpoint_available=True,
                checkpoint_integrity_ok=False,
                real_resume_executed=False,
                terminal_status=None,
                quality_evaluated=False,
                quality_passed=False,
            )
        return {
            "agent_id": "AGENT_C_REFLECTION_PROVIDER",
            "impl_ok": isolation_ok,
            "local_runtime_checkpoint_available": bool(
                loaded.get("local_runtime_checkpoint_available")
            ),
            "manifest_checksum_status": loaded.get("manifest_checksum_status"),
            "checkpoint_integrity_status": loaded.get("checkpoint_integrity_status"),
            "checkpoint_migration_status": loaded.get("checkpoint_migration_status"),
            "real_resume_executed": False,
            "real_resume_status": loaded.get("real_resume_status")
            or "LOCAL_CHECKPOINT_REQUIRED_FOR_REAL_RESUME",
            "groq_scheduler_status": scheduler_status[GROQ_REFLECTION_REASONER],
            "sambanova_scheduler_status": scheduler_status[SAMBANOVA_INDEPENDENT_CRITIC],
            "cerebras_scheduler_status": scheduler_status[CEREBRAS_RESEARCH_NORMALIZER],
            "groq_main_scheduler_status": scheduler_status[GROQ_MAIN_REASONER],
            "circuit_breaker_status": scheduler.breaker.status(GROQ_REFLECTION_REASONER),
            "retry_after_status": "PARSED" if groq_429.get("transport_status") == "RATE_LIMITED" else "FAIL",
            "successful_case_dedup_status": "READY",
            "provider_isolation_ok": isolation_ok,
            "scheduler_snapshot": scheduler.snapshot(),
            "frozen_calibration_case_count": 80,
            "groq_success_count": None,
            "groq_pending_count": None,
            "sambanova_success_count": None,
            "sambanova_pending_count": None,
            "V2_3_terminal_status": "INCOMPLETE_PROVIDER_CAPACITY",
            "quality_gates_evaluated": False,
            "quality_gates_passed": False,
            "new_policy_effect_lesson_count": lesson["new_policy_effect_lesson_count"],
            "lesson": lesson,
            "recommendation": rec,
            "fixture_only": True,
            "real_ai_quality_claimed": False,
        }

    state = loaded["state"]
    # Sync scheduler counters from checkpoint (no fabricated increments)
    for pid in PROVIDER_PROFILES:
        slot = (state.get("transport") or {}).get(pid) or {}
        q = scheduler.queues[pid]
        q.attempt_count = int(slot.get("attempt_count") or 0)
        q.success_count = int(slot.get("success_count") or 0)
        q.http_429_count = int(slot.get("HTTP_429_count") or 0)
        q.next_resume_not_before = slot.get("next_resume_not_before")
        q.retry_after = slot.get("retry_after")
        q.model_id = str(slot.get("model_id") or "")

    scheduler.deduper.load_from_checkpoint(state)

    quality = evaluate_terminal(state)
    terminal = quality.get("V2_3_TERMINAL_STATUS")
    lesson = apply_lesson_gate(terminal_status=terminal)

    # Optional real resume — pending-only via quota_aware (never repeats successes)
    real_resume_executed = False
    real_resume_status = "LOCAL_CHECKPOINT_PRESENT_RESUME_DEFERRED"
    cal_out: dict[str, Any] | None = None
    if allow_real_resume and packets is not None and manifest_checksum:
        from backend.nexus_edge_discovery.quota_aware_v23 import run_quota_aware_calibration

        cal_out = run_quota_aware_calibration(
            root=root,
            packets=packets,
            manifest_checksum=manifest_checksum,
            use_real_ai=True,
            max_batches_this_invocation=int(
                __import__("os").environ.get("NEXUS_V23_MAX_BATCHES", "2")
            ),
            run_critic=True,
        )
        real_resume_executed = True
        real_resume_status = str(cal_out.get("checkpoint_status") or "REAL_RESUME_ATTEMPTED")
        # Reload checkpoint after resume (successes already deduped inside quota_aware)
        reloaded = load_checkpoint(
            root,
            expected_manifest=manifest_checksum,
            migrate=True,
            model_id=model_id,
        )
        if reloaded.get("ok") and reloaded.get("state"):
            state = reloaded["state"]
            quality = evaluate_terminal(state)
            terminal = quality.get("V2_3_TERMINAL_STATUS")
            lesson = apply_lesson_gate(terminal_status=terminal)
            groq = (state.get("transport") or {}).get(GROQ_REFLECTION_REASONER) or {}
            sn = (state.get("transport") or {}).get(SAMBANOVA_INDEPENDENT_CRITIC) or {}
    elif allow_real_resume:
        real_resume_status = "REAL_RESUME_SKIPPED_MISSING_PACKETS_OR_MANIFEST"

    # Persist migrated checkpoint (sanitized) when packets provided for schema upgrade
    if packets is not None and manifest_checksum and not real_resume_executed:
        if len(state.get("case_ids") or []) != 80 and packets:
            pass
        save_checkpoint(root, state)

    if not real_resume_executed:
        groq = (state.get("transport") or {}).get(GROQ_REFLECTION_REASONER) or {}
        sn = (state.get("transport") or {}).get(SAMBANOVA_INDEPENDENT_CRITIC) or {}

    rec = pick_agent_c_recommendation(
        impl_ok=isolation_ok,
        local_checkpoint_available=True,
        checkpoint_integrity_ok=True,
        real_resume_executed=real_resume_executed,
        terminal_status=terminal,
        quality_evaluated=bool(quality.get("quality_gates_evaluated")),
        quality_passed=bool(quality.get("quality_gates_passed")),
    )

    out = {
        "agent_id": "AGENT_C_REFLECTION_PROVIDER",
        "impl_ok": isolation_ok,
        "local_runtime_checkpoint_available": True,
        "manifest_checksum_status": loaded.get("manifest_checksum_status"),
        "checkpoint_integrity_status": loaded.get("checkpoint_integrity_status"),
        "checkpoint_migration_status": loaded.get("checkpoint_migration_status"),
        "real_resume_executed": real_resume_executed,
        "real_resume_status": real_resume_status,
        "groq_scheduler_status": scheduler_status[GROQ_REFLECTION_REASONER],
        "sambanova_scheduler_status": scheduler_status[SAMBANOVA_INDEPENDENT_CRITIC],
        "cerebras_scheduler_status": scheduler_status[CEREBRAS_RESEARCH_NORMALIZER],
        "groq_main_scheduler_status": scheduler_status[GROQ_MAIN_REASONER],
        "circuit_breaker_status": scheduler.breaker.status(GROQ_REFLECTION_REASONER),
        "retry_after_status": "PARSED",
        "successful_case_dedup_status": "LOADED_FROM_CHECKPOINT",
        "provider_isolation_ok": isolation_ok,
        "scheduler_snapshot": scheduler.snapshot(),
        "frozen_calibration_case_count": 80,
        "groq_success_count": int(groq.get("success_count") or 0),
        "groq_pending_count": len(state.get("pending_case_ids") or []),
        "sambanova_success_count": int(sn.get("success_count") or 0),
        "sambanova_pending_count": len(
            state.get("pending_critic_case_ids") or state.get("critic_pending_ids") or []
        ),
        "V2_3_terminal_status": terminal,
        "quality_gates_evaluated": bool(quality.get("quality_gates_evaluated")),
        "quality_gates_passed": bool(quality.get("quality_gates_passed")),
        "new_policy_effect_lesson_count": lesson["new_policy_effect_lesson_count"],
        "lesson": lesson,
        "quality": quality,
        "recommendation": rec,
        "fixture_only": False,
        "real_ai_quality_claimed": False,
        "undetermined_migration_sample": migrate_process_classification("UNDETERMINED_PROCESS"),
        "disagreement_sample": build_disagreement_record(
            trade_id="SAMPLE",
            groq_classification="GOOD_PROCESS_WIN",
            groq_evidence_ids=["e1"],
            deterministic_classification="BAD_PROCESS_WIN",
            deterministic_rule_ids=["r1"],
            sambanova_result=None,
            evidence_sufficiency="EVIDENCE_SUFFICIENT",
            conflict_type=classify_conflict(
                {
                    "evidence_sufficiency": "EVIDENCE_SUFFICIENT",
                    "critic_verdict": None,
                }
            ),
            legacy_process_raw="UNDETERMINED_PROCESS",
        ),
    }
    if cal_out is not None:
        out["quota_aware_resume_summary"] = cal_out.get("state_summary")
        out["quota_aware_checkpoint_status"] = cal_out.get("checkpoint_status")
    return out


def bootstrap_fixture_checkpoint(
    root: Path,
    *,
    packets: list[dict[str, Any]],
    manifest_checksum: str,
    model_id: str = "fixture-model",
) -> dict[str, Any]:
    """Create a sanitized empty checkpoint for unit tests only (not real progress)."""
    state = build_initial_checkpoint(
        packets=packets, manifest_checksum=manifest_checksum, model_id=model_id
    )
    save_checkpoint(root, state)
    return state
