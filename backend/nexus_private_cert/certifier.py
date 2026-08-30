"""PRIVATE-ENV-2R certifier orchestration → strict redacted schema."""

from __future__ import annotations

import os
from typing import Any

from backend.nexus_private_cert.safety import safety_gate

# Required active certification set (PRIVATE-AI-2): SambaNova is deferred
# (billing not enabled) and replaced by the Gemini independent critic.
GROQ_CEREBRAS_PROFILES = (
    "GROQ_MAIN_REASONER",
    "GROQ_REFLECTION_REASONER",
    "CEREBRAS_RESEARCH_NORMALIZER",
)
GEMINI_PROFILE = "GEMINI_INDEPENDENT_CRITIC"
AI_PROFILES = GROQ_CEREBRAS_PROFILES + (GEMINI_PROFILE,)


def _run_ai_smoke(gateway: Any | None) -> dict[str, Any]:
    """Bounded, sanitized real-API smoke per required profile (read-only).

    Groq main/reflection + Cerebras run via the existing FounderAIGateway;
    the independent critic runs via the dedicated native Gemini adapter.
    SambaNova is NOT part of the required set (DEFERRED_BILLING_NOT_ENABLED).
    """
    statuses: dict[str, Any] = {}
    models: dict[str, Any] = {}
    detail: dict[str, Any] = {}
    try:
        if gateway is None:
            from backend.nexus_ai_gateway.founder_providers import FounderAIGateway

            gateway = FounderAIGateway.from_env()
        from backend.nexus_ai_gateway.founder_providers import (
            DEFAULT_MODELS,
            run_real_provider_smoke_tests,
        )

        smoke = run_real_provider_smoke_tests(gateway)
        by = {r["provider_profile"]: r for r in smoke}
        for p in GROQ_CEREBRAS_PROFILES:
            statuses[p] = (by.get(p) or {}).get("result_status", "PROVIDER_ERROR")
            models[p] = DEFAULT_MODELS.get(p)
        for rec in getattr(gateway, "records", []) or []:
            pid = rec.get("provider_profile")
            if pid in GROQ_CEREBRAS_PROFILES:
                detail[pid] = {
                    "http_status": rec.get("http_status"),
                    "smoke_map": rec.get("smoke_map"),
                    "error": rec.get("error_snippet_redacted"),
                    "verified_model_id": rec.get("verified_model_id"),
                }
    except Exception as exc:  # noqa: BLE001 - never leak internals
        for p in GROQ_CEREBRAS_PROFILES:
            statuses.setdefault(p, "PROVIDER_ERROR")
            models.setdefault(p, None)
        detail["_gateway_error"] = type(exc).__name__

    # Independent critic via the dedicated Gemini adapter (never SambaNova code).
    try:
        from backend.nexus_private_cert.gemini_provider import gemini_smoke

        g = gemini_smoke()
        statuses[GEMINI_PROFILE] = g.get("result_status", "PROVIDER_ERROR")
        models[GEMINI_PROFILE] = g.get("verified_model_id")
        detail[GEMINI_PROFILE] = {
            "http_status": g.get("http_status"),
            "smoke_map": g.get("smoke_map"),
            "error": g.get("error"),
            "verified_model_id": g.get("verified_model_id"),
            "can_approve_order": False,
        }
    except Exception as exc:  # noqa: BLE001
        statuses[GEMINI_PROFILE] = "PROVIDER_ERROR"
        models[GEMINI_PROFILE] = None
        detail[GEMINI_PROFILE] = {"error": type(exc).__name__}

    return {
        "statuses": statuses,
        "models": models,
        "detail": detail,
        "all_pass": all(statuses.get(p) == "REAL_API_PASS" for p in AI_PROFILES),
    }


def run_certification(
    *,
    pool: Any = None,
    env: dict[str, str] | None = None,
    ai_gateway: Any = None,
    bybit_reader: Any = None,
) -> dict[str, Any]:
    """Return the redacted PRIVATE-ENV-2 certification. Never returns secrets."""
    src = env if env is not None else os.environ
    ok, safety = safety_gate(src)

    base = {
        "schema": "private_env2_certification_v1",
        "private_env2_pass": False,
        "safety": {"ok": safety["ok"], "flags": safety["flags"], "violations": safety["violations"]},
        "orders_submitted": 0,
        "cancels": 0,
        "position_mutations": 0,
    }

    # Fail-closed: no external credentialed call happens unless the demo-only
    # posture holds.
    if not ok:
        base["blocked_reason"] = "SAFETY_BLOCK"
        base["ai"] = {p: "NOT_RUN" for p in AI_PROFILES}
        base["bybit_demo"] = {"auth": "NOT_RUN"}
        base["postgres"] = {"postgres_available": "NOT_RUN"}
        return base

    ai = _run_ai_smoke(ai_gateway)

    # Redacted provider model catalog (model IDs only) so a stale configured
    # model can be corrected against the provider's live catalog.
    try:
        from backend.nexus_private_cert.ai_catalog import ai_model_catalog

        ai_catalog = ai_model_catalog()
    except Exception:  # noqa: BLE001
        ai_catalog = {}

    from backend.nexus_private_cert.bybit_readonly import bybit_readonly_preflight

    expected_uid = (src.get("BYBIT_DEMO_UID_EXPECTED") or src.get("BYBIT_DEMO_UID") or "").strip() or None
    bybit = bybit_readonly_preflight(expected_uid=expected_uid, reader=bybit_reader)

    from backend.nexus_private_cert.postgres_durability import postgres_durability_preflight

    postgres = postgres_durability_preflight(pool)

    ai_ok = ai["all_pass"]
    # UID binding must be an explicit PASS: SKIPPED (no expected UID configured)
    # does NOT qualify as certified account-identity readiness.
    bybit_ok = (
        bybit["auth"] == "PASS"
        and bybit["balance_read"] == "PASS"
        and bybit["positions_read"] == "PASS"
        and bybit["instrument_read"] == "PASS"
        and bybit["clock_skew_ok"] == "PASS"
        and bybit["uid_binding"] == "PASS"
    )
    postgres_ok = all(
        postgres.get(k) is True
        for k in (
            "postgres_available",
            "migration_catalog_valid",
            "migration_0014_present",
            "durable_ledger_readable",
            "durable_lesson_readable",
            "learning_closure_readable",
            "repeat_mistake_guard_healthy",
            "runtime_lease_healthy",
            "cost_gate_healthy",
            "no_unresolved_intent",
        )
    )

    base["ai"] = ai["statuses"]
    base["ai_models"] = ai["models"]
    base["ai_detail"] = ai.get("detail", {})
    base["ai_catalog"] = ai_catalog
    base["ai_routing"] = {
        "main_market_reasoner": "GROQ_MAIN_REASONER",
        "reflection_reasoner": "GROQ_REFLECTION_REASONER",
        "lesson_normalizer": "CEREBRAS_RESEARCH_NORMALIZER",
        "bulk_research_summarizer": "CEREBRAS_RESEARCH_NORMALIZER",
        "independent_reflection_critic": "GEMINI_INDEPENDENT_CRITIC",
        "sambanova": "DEFERRED_BILLING_NOT_ENABLED",
        "main_reasoner_failover_forbidden": True,
        "only_main_reasoner_order_critical": True,
        "ai_can_approve_order": False,
    }
    base["bybit_demo"] = bybit
    base["postgres"] = postgres
    # Counters authoritatively come from the read-only bybit path (always 0).
    base["orders_submitted"] = int(bybit.get("orders_submitted", 0))
    base["cancels"] = int(bybit.get("cancels", 0))
    base["position_mutations"] = int(bybit.get("position_mutations", 0))
    base["private_env2_pass"] = bool(ai_ok and bybit_ok and postgres_ok and safety["ok"])
    if not base["private_env2_pass"]:
        reasons = []
        if not ai_ok:
            reasons.append("AI_NOT_ALL_REAL_API_PASS")
        if not bybit_ok:
            reasons.append("BYBIT_READONLY_INCOMPLETE")
        if not postgres_ok:
            reasons.append("POSTGRES_DURABILITY_INCOMPLETE")
        base["blocked_reason"] = ",".join(reasons) or "UNKNOWN"
    return base
