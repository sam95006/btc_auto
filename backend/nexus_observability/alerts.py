"""Alert builders for Founder-private observability SLO V11.1."""
from __future__ import annotations

from typing import Any

from backend.nexus_observability.constants import (
    ALERT_CLASSES,
    PROVIDER_CAPACITY_BLOCKING_STATUSES,
    PROVIDER_CAPACITY_PENDING_RATIO,
    PROVIDER_MIN_SUCCESS_FOR_CAPACITY,
    SCHEMA_ALERT,
    STALENESS_THRESHOLD_SECONDS,
)


def _alert(
    *,
    alert_class: str,
    code: str,
    severity: str,
    message: str,
    domain: str,
    active: bool,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if alert_class not in ALERT_CLASSES:
        raise ValueError(f"unknown_alert_class:{alert_class}")
    return {
        "schema": SCHEMA_ALERT,
        "alert_class": alert_class,
        "code": code,
        "severity": severity,
        "message": message,
        "domain": domain,
        "active": bool(active),
        "evidence": evidence or {},
        "read_only": True,
        "founder_private": True,
        "mutation_attempted": False,
    }


def build_failure_state_alerts(domain_health: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    decision = domain_health.get("decision_lifecycle") or {}
    if decision.get("blocked_ambiguous_count", 0) or decision.get("failure_trap", False):
        out.append(
            _alert(
                alert_class="failure_state",
                code="DECISION_FAILURE_OR_BLOCKED",
                severity="critical",
                message="Decision lifecycle reports failure trap or blocked-ambiguous entries.",
                domain="decision_lifecycle",
                active=True,
                evidence={
                    "blocked_ambiguous_count": decision.get("blocked_ambiguous_count"),
                    "failure_trap": decision.get("failure_trap"),
                },
            )
        )
    session = domain_health.get("session_lifecycle") or {}
    states = set(session.get("terminal_failure_states") or [])
    if states & {"FAILED_SAFE", "BLOCKED"} or session.get("failed_safe"):
        out.append(
            _alert(
                alert_class="failure_state",
                code="SESSION_FAILED_SAFE_OR_BLOCKED",
                severity="critical",
                message="Session lifecycle in FAILED_SAFE or BLOCKED.",
                domain="session_lifecycle",
                active=True,
                evidence={"states": sorted(states)},
            )
        )
    risk = domain_health.get("risk_gates") or {}
    if risk.get("gates_intact") is False:
        out.append(
            _alert(
                alert_class="failure_state",
                code="RISK_GATES_COMPROMISED",
                severity="critical",
                message="Risk gate hard bans no longer intact.",
                domain="risk_gates",
                active=True,
                evidence={"detail": risk.get("detail")},
            )
        )
    ks = domain_health.get("kill_switch_readiness") or {}
    if ks.get("reachable") is False:
        out.append(
            _alert(
                alert_class="failure_state",
                code="KILL_SWITCH_UNREACHABLE",
                severity="critical",
                message="Kill-switch readiness surface unreachable.",
                domain="kill_switch_readiness",
                active=True,
            )
        )
    qual = domain_health.get("qualification_block_state") or {}
    if qual.get("all_stages_blocked") is False:
        out.append(
            _alert(
                alert_class="failure_state",
                code="QUALIFICATION_STAGE_UNBLOCKED",
                severity="critical",
                message="Qualification stage matrix is not fully BLOCKED.",
                domain="qualification_block_state",
                active=True,
                evidence={"stages": qual.get("stages")},
            )
        )
    return out


def build_staleness_alerts(domain_health: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    decision = domain_health.get("decision_lifecycle") or {}
    age = float(decision.get("max_evidence_age_seconds") or 0.0)
    if decision.get("stale") or age > STALENESS_THRESHOLD_SECONDS:
        out.append(
            _alert(
                alert_class="staleness",
                code="DECISION_EVIDENCE_STALE",
                severity="high",
                message=f"Decision evidence older than {STALENESS_THRESHOLD_SECONDS:.0f}s.",
                domain="decision_lifecycle",
                active=True,
                evidence={"max_evidence_age_seconds": age},
            )
        )
    reflection = domain_health.get("reflection_queue") or {}
    if reflection.get("stale_queue"):
        out.append(
            _alert(
                alert_class="staleness",
                code="REFLECTION_QUEUE_STALE",
                severity="high",
                message="Reflection queue reports stalled/stale progress.",
                domain="reflection_queue",
                active=True,
                evidence={
                    "pending_count": reflection.get("pending_count"),
                    "success_count": reflection.get("success_count"),
                },
            )
        )
    return out


def build_data_quality_alerts(domain_health: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    decision = domain_health.get("decision_lifecycle") or {}
    if decision.get("data_quality_ok") is False:
        out.append(
            _alert(
                alert_class="data_quality",
                code="DECISION_EVIDENCE_DQ_FAIL",
                severity="high",
                message="Decision evidence completeness/quality failed.",
                domain="decision_lifecycle",
                active=True,
                evidence={"dq_detail": decision.get("dq_detail")},
            )
        )
    lesson = domain_health.get("lesson_gate") or {}
    if int(lesson.get("unauthorized_lesson_count") or 0) > 0:
        out.append(
            _alert(
                alert_class="data_quality",
                code="LESSON_GATE_UNAUTHORIZED",
                severity="critical",
                message="Unauthorized policy-effect lessons detected.",
                domain="lesson_gate",
                active=True,
                evidence={"unauthorized_lesson_count": lesson.get("unauthorized_lesson_count")},
            )
        )
    micro = domain_health.get("microstructure_health") or {}
    if micro.get("integrity_ok") is False:
        out.append(
            _alert(
                alert_class="data_quality",
                code="MICROSTRUCTURE_INTEGRITY_FAIL",
                severity="high",
                message="Microstructure integrity health degraded.",
                domain="microstructure_health",
                active=True,
                evidence={"detail": micro.get("detail")},
            )
        )
    ledger = domain_health.get("ledger_snapshot_checkpoint") or {}
    if ledger.get("data_quality_ok") is False:
        out.append(
            _alert(
                alert_class="data_quality",
                code="LEDGER_CHECKPOINT_DQ_FAIL",
                severity="high",
                message="Ledger/snapshot/checkpoint data quality failed.",
                domain="ledger_snapshot_checkpoint",
                active=True,
            )
        )
    return out


def build_ambiguous_state_alerts(domain_health: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    decision = domain_health.get("decision_lifecycle") or {}
    if int(decision.get("blocked_ambiguous_count") or 0) > 0:
        out.append(
            _alert(
                alert_class="ambiguous_state",
                code="DECISION_BLOCKED_AMBIGUOUS",
                severity="critical",
                message="Decision objects in BLOCKED_AMBIGUOUS — no silent continue.",
                domain="decision_lifecycle",
                active=True,
                evidence={"count": decision.get("blocked_ambiguous_count")},
            )
        )
    ledger = domain_health.get("ledger_snapshot_checkpoint") or {}
    if ledger.get("ambiguous_state") or int(ledger.get("ambiguous_count") or 0) > 0:
        out.append(
            _alert(
                alert_class="ambiguous_state",
                code="DURABILITY_BLOCKED_AMBIGUOUS_STATE",
                severity="critical",
                message="Durability reports BLOCKED_AMBIGUOUS_STATE.",
                domain="ledger_snapshot_checkpoint",
                active=True,
                evidence={"ambiguous_count": ledger.get("ambiguous_count")},
            )
        )
    return out


def build_storage_floor_alerts(domain_health: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    storage = domain_health.get("storage_budget") or {}
    if storage.get("floor_ok") is False or storage.get("mode") == "STORAGE_BUDGET_BLOCKED":
        out.append(
            _alert(
                alert_class="storage_floor",
                code="STORAGE_FLOOR_OR_HARD_CAP",
                severity="critical",
                message="Storage floor failed or budget hard-cap blocked.",
                domain="storage_budget",
                active=True,
                evidence={
                    "mode": storage.get("mode"),
                    "free_bytes": storage.get("free_bytes"),
                    "minimum_free_disk_bytes": storage.get("minimum_free_disk_bytes"),
                    "stop_reason": storage.get("stop_reason"),
                },
            )
        )
    return out


def build_provider_capacity_alerts(domain_health: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    provider = domain_health.get("provider_health") or {}
    reflection = domain_health.get("reflection_queue") or {}

    status = str(provider.get("transport_status") or "").upper()
    terminal = str(provider.get("terminal_status") or reflection.get("terminal_status") or "").upper()
    success = int(provider.get("success_count") or reflection.get("success_count") or 0)
    pending = int(provider.get("pending_count") or reflection.get("pending_count") or 0)
    denom = max(success + pending, 1)
    pending_ratio = pending / denom

    capacity_blocked = bool(provider.get("capacity_blocked"))
    if status in PROVIDER_CAPACITY_BLOCKING_STATUSES:
        capacity_blocked = True
    if terminal in PROVIDER_CAPACITY_BLOCKING_STATUSES or terminal == "INCOMPLETE_PROVIDER_CAPACITY":
        capacity_blocked = True
    if success < PROVIDER_MIN_SUCCESS_FOR_CAPACITY and pending_ratio >= PROVIDER_CAPACITY_PENDING_RATIO:
        capacity_blocked = True
    if pending_ratio >= 0.5 and pending > 0:
        capacity_blocked = True

    if capacity_blocked:
        out.append(
            _alert(
                alert_class="provider_capacity",
                code="PROVIDER_CAPACITY_BLOCKED",
                severity="high",
                message="Provider capacity blocked (rate-limit/circuit/bucket/incomplete).",
                domain="provider_health",
                active=True,
                evidence={
                    "transport_status": status or None,
                    "terminal_status": terminal or None,
                    "success_count": success,
                    "pending_count": pending,
                    "pending_ratio": round(pending_ratio, 4),
                },
            )
        )
    return out


def collect_alerts(domain_health: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    alerts.extend(build_failure_state_alerts(domain_health))
    alerts.extend(build_staleness_alerts(domain_health))
    alerts.extend(build_data_quality_alerts(domain_health))
    alerts.extend(build_ambiguous_state_alerts(domain_health))
    alerts.extend(build_storage_floor_alerts(domain_health))
    alerts.extend(build_provider_capacity_alerts(domain_health))
    return alerts


def alert_matrix_document(*, alerts: list[dict[str, Any]], created_at: str) -> dict[str, Any]:
    by_class: dict[str, list[dict[str, Any]]] = {c: [] for c in ALERT_CLASSES}
    for a in alerts:
        by_class.setdefault(str(a.get("alert_class")), []).append(a)
    return {
        "schema": "v11_1_private_observability_alert_matrix",
        "created_at": created_at,
        "alert_classes": list(ALERT_CLASSES),
        "active_count": sum(1 for a in alerts if a.get("active")),
        "alerts": alerts,
        "by_class": by_class,
        "founder_private": True,
        "read_only": True,
        "public_routes": False,
        "execution_mutation_endpoint": False,
    }
