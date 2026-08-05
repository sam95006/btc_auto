"""Aggregate Founder-private read-only Observability SLO snapshot V11.1."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_observability.alerts import alert_matrix_document, collect_alerts
from backend.nexus_observability.collectors import collect_all_domains
from backend.nexus_observability.constants import (
    ALERT_CLASSES,
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    DEFAULT_MINIMUM_FREE_DISK_BYTES,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OBSERVABILITY_DOMAINS,
    OWNED_PATHS,
    PACKAGE,
    PROHIBITED_PATHS_UNTOUCHED,
    SCHEMA_HARD_BANS,
    SCHEMA_SNAPSHOT,
    SCHEMA_STATUS,
    STALENESS_THRESHOLD_SECONDS,
)
from backend.nexus_observability.sanitize import assert_no_forbidden_keys
from backend.nexus_observability.slo import definitions_document, evaluate_slos


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hard_bans_document(*, created_at: str | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA_HARD_BANS,
        "created_at": created_at or _utc(),
        "hard_bans": list(HARD_BANS),
        "public_routes": False,
        "account_secrets": False,
        "execution_mutation_endpoint": False,
        "read_only": True,
        "founder_private": True,
    }


def build_private_observability_slo(
    root: Path | str,
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
    disk_root: str | None = None,
    pass_number: int | None = None,
) -> dict[str, Any]:
    """Build a complete Founder-private observability SLO snapshot (READ-ONLY).

    Never opens public routes, never exposes account secrets, never mutates execution.
    """
    root_path = Path(root)
    created_at = _utc()
    domains = collect_all_domains(root_path, overrides=overrides, disk_root=disk_root)
    alerts = collect_alerts(domains)
    for a in alerts:
        if not a.get("active"):
            continue
        dom_key = str(a.get("domain"))
        dom = domains.get(dom_key) or {}
        classes = set(dom.get("active_alert_classes") or [])
        classes.add(str(a.get("alert_class")))
        dom["active_alert_classes"] = sorted(classes)
        domains[dom_key] = dom

    slo_eval = evaluate_slos(domain_health=domains, alerts=alerts)
    defs = definitions_document(created_at=created_at)
    matrix = alert_matrix_document(alerts=alerts, created_at=created_at)
    bans = hard_bans_document(created_at=created_at)

    snapshot = {
        "schema": SCHEMA_SNAPSHOT,
        "created_at": created_at,
        "founder_private": True,
        "read_only": True,
        "public_routes": False,
        "public_product_exposure": False,
        "execution_mutation_endpoint": False,
        "secrets_present": False,
        "account_information_present": False,
        "strategy_parameters_present": False,
        "domains": domains,
        "domain_order": list(OBSERVABILITY_DOMAINS),
        "alert_classes_supported": list(ALERT_CLASSES),
        "pass_number": pass_number,
    }

    all_slos_ok = slo_eval["passed"] == slo_eval["total"]
    status = {
        "schema": SCHEMA_STATUS,
        "created_at": created_at,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "artifact_rel": ARTIFACT_REL,
        "base_commit": BASE_COMMIT,
        "status": "PASS" if all_slos_ok else "FAIL",
        "slo_score": slo_eval["slo_score"],
        "slo_status": slo_eval["status"],
        "slos_passed": slo_eval["passed"],
        "slos_total": slo_eval["total"],
        "active_alert_count": matrix["active_count"],
        "founder_private": True,
        "read_only": True,
        "public_routes": False,
        "public_api_exposed": False,
        "execution_mutation_endpoint": False,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "mainnet": False,
        "real_money": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "secrets_present": False,
        "account_information_present": False,
        "strategy_parameters_present": False,
        "owned_paths": list(OWNED_PATHS),
        "prohibited_paths_untouched": list(PROHIBITED_PATHS_UNTOUCHED),
        "hard_ban_count": len(HARD_BANS),
        "pass_number": pass_number,
    }

    bundle = {
        "status": status,
        "slo_definitions": defs,
        "slo_evaluation": slo_eval,
        "alert_matrix": matrix,
        "domain_health_snapshot": snapshot,
        "hard_bans": bans,
    }
    assert_no_forbidden_keys(bundle)
    return bundle


def apply_pass2_adversarial_overrides() -> dict[str, dict[str, Any]]:
    """Synthetic adversarial domain breaches for Pass 2 negative proof.

    These overrides exercise alert classes. They do not mutate execution
    and do not open public routes.
    """
    return {
        "decision_lifecycle": {
            "max_evidence_age_seconds": STALENESS_THRESHOLD_SECONDS + 120.0,
            "stale": True,
            "data_quality_ok": False,
            "dq_detail": "incomplete_evidence",
            "blocked_ambiguous_count": 2,
            "failure_trap": True,
        },
        "session_lifecycle": {
            "terminal_failure_states": ["FAILED_SAFE"],
            "failed_safe": True,
        },
        "risk_gates": {
            "gates_intact": False,
            "detail": "adversarial_forbidden_action_bypass_attempt",
        },
        "execution_simulator": {
            "mutation_endpoint_count": 0,
        },
        "provider_health": {
            "transport_status": "RATE_LIMITED",
            "terminal_status": "INCOMPLETE_PROVIDER_CAPACITY",
            "success_count": 10,
            "pending_count": 70,
            "capacity_blocked": True,
        },
        "reflection_queue": {
            "pending_count": 70,
            "success_count": 10,
            "stale_queue": True,
            "terminal_status": "INCOMPLETE_PROVIDER_CAPACITY",
        },
        "lesson_gate": {
            "terminal_status": "INCOMPLETE_PROVIDER_CAPACITY",
            "quality_gates_passed": False,
            "proposed_policy_effect_lesson_count": 5,
            "unauthorized_lesson_count": 1,
        },
        "ledger_snapshot_checkpoint": {
            "ambiguous_state": True,
            "ambiguous_count": 1,
            "data_quality_ok": False,
            "checkpoint_ok": False,
        },
        "microstructure_health": {
            "integrity_ok": False,
            "event_study_started": False,
            "event_study_readiness": "NOT_READY",
            "detail": "adversarial_integrity_degraded",
        },
        "storage_budget": {
            "floor_ok": False,
            "mode": "STORAGE_BUDGET_BLOCKED",
            "free_bytes": 1,
            "minimum_free_disk_bytes": DEFAULT_MINIMUM_FREE_DISK_BYTES,
            "stop_reason": "minimum_free_disk_fail",
        },
        "kill_switch_readiness": {
            "reachable": True,
            "kill_switch_engaged": True,
            "kill_switch_reason": "adversarial_probe",
            "state": "KILLED",
        },
        "qualification_block_state": {
            "all_stages_blocked": True,
        },
    }
