"""SLO definitions + evaluation for Founder-private observability V11.1."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.nexus_observability.constants import (
    OBSERVABILITY_DOMAINS,
    SCHEMA_SLO_DEFINITIONS,
    SLO_DEGRADED_MIN,
    SLO_HEALTHY_MIN,
    STALENESS_THRESHOLD_SECONDS,
)


@dataclass(frozen=True)
class SLODefinition:
    slo_id: str
    domain: str
    name: str
    description: str
    metric: str
    threshold: str
    alert_classes: tuple[str, ...]
    severity_on_breach: str = "critical"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["alert_classes"] = list(self.alert_classes)
        return d


def slo_catalog() -> list[SLODefinition]:
    """Canonical Founder-private SLO definitions (read-only contract)."""
    return [
        SLODefinition(
            slo_id="slo.decision_lifecycle.no_failure_trap",
            domain="decision_lifecycle",
            name="Decision lifecycle fail-closed clarity",
            description="Decision objects must not linger in unrecoverable failure traps without alert.",
            metric="failure_or_blocked_count",
            threshold="alert_if_>0_without_CLOSED_path",
            alert_classes=("failure_state", "ambiguous_state"),
        ),
        SLODefinition(
            slo_id="slo.decision_lifecycle.evidence_fresh",
            domain="decision_lifecycle",
            name="Decision evidence freshness",
            description=f"Evidence age must stay within {STALENESS_THRESHOLD_SECONDS:.0f}s or raise staleness.",
            metric="max_evidence_age_seconds",
            threshold=f"<={STALENESS_THRESHOLD_SECONDS}",
            alert_classes=("staleness", "data_quality"),
        ),
        SLODefinition(
            slo_id="slo.session_lifecycle.no_failed_safe_unacked",
            domain="session_lifecycle",
            name="Session FAILED_SAFE / BLOCKED acknowledgment",
            description="Session terminal failure states must surface as failure-state alerts.",
            metric="session_failure_states",
            threshold="alert_if_FAILED_SAFE_or_BLOCKED",
            alert_classes=("failure_state",),
        ),
        SLODefinition(
            slo_id="slo.risk_gates.forbidden_actions_blocked",
            domain="risk_gates",
            name="Risk gate hard bans intact",
            description="Forbidden risk actions must remain rejected; gates healthy.",
            metric="forbidden_action_pass_rate",
            threshold="==1.0",
            alert_classes=("failure_state",),
            severity_on_breach="critical",
        ),
        SLODefinition(
            slo_id="slo.execution_simulator.read_only",
            domain="execution_simulator",
            name="Execution simulator non-mutating observability",
            description="Simulator health may be observed; no mutation endpoint exposed.",
            metric="mutation_endpoint_count",
            threshold="==0",
            alert_classes=("failure_state",),
        ),
        SLODefinition(
            slo_id="slo.provider.capacity_available",
            domain="provider_health",
            name="Provider capacity readiness",
            description="Provider transport must not be capacity-blocked (429/circuit/bucket/incomplete).",
            metric="provider_capacity_blocked",
            threshold="==false",
            alert_classes=("provider_capacity",),
        ),
        SLODefinition(
            slo_id="slo.reflection.queue_progress",
            domain="reflection_queue",
            name="Reflection queue progress",
            description="Reflection pending backlog must not indicate stalled provider capacity.",
            metric="pending_ratio",
            threshold="non_blocking_or_alert",
            alert_classes=("provider_capacity", "staleness"),
        ),
        SLODefinition(
            slo_id="slo.lesson_gate.fail_closed",
            domain="lesson_gate",
            name="Lesson gate fail-closed",
            description="Policy-effect lessons blocked unless VERIFIED + quality gates.",
            metric="unauthorized_lesson_count",
            threshold="==0",
            alert_classes=("failure_state", "data_quality"),
        ),
        SLODefinition(
            slo_id="slo.durability.checkpoint_healthy",
            domain="ledger_snapshot_checkpoint",
            name="Ledger/snapshot/checkpoint health",
            description="Checkpoint/ledger surfaces healthy; ambiguous durability blocks alerted.",
            metric="ambiguous_or_corrupt",
            threshold="==0_or_alerted",
            alert_classes=("ambiguous_state", "data_quality", "failure_state"),
        ),
        SLODefinition(
            slo_id="slo.microstructure.health_visible",
            domain="microstructure_health",
            name="Microstructure health visibility",
            description="Microstructure integrity/event-study readiness observed without starting Event Study.",
            metric="event_study_started",
            threshold="==false",
            alert_classes=("data_quality",),
        ),
        SLODefinition(
            slo_id="slo.storage.floor_ok",
            domain="storage_budget",
            name="Storage floor / budget",
            description="Free disk must meet minimum floor; hard-cap blocked mode must alert.",
            metric="storage_floor_status",
            threshold="PASS",
            alert_classes=("storage_floor",),
        ),
        SLODefinition(
            slo_id="slo.kill_switch.readiness",
            domain="kill_switch_readiness",
            name="Kill-switch readiness",
            description="Kill-switch must be reachable and report engaged state when triggered.",
            metric="kill_switch_reachable",
            threshold="==true",
            alert_classes=("failure_state",),
        ),
        SLODefinition(
            slo_id="slo.qualification.all_blocked",
            domain="qualification_block_state",
            name="Qualification stages remain BLOCKED",
            description="All qualification control stages must remain BLOCKED with hard bans intact.",
            metric="all_stages_blocked",
            threshold="==true",
            alert_classes=("failure_state",),
        ),
    ]


def definitions_document(*, created_at: str) -> dict[str, Any]:
    defs = slo_catalog()
    return {
        "schema": SCHEMA_SLO_DEFINITIONS,
        "created_at": created_at,
        "founder_private": True,
        "read_only": True,
        "domain_count": len(OBSERVABILITY_DOMAINS),
        "domains": list(OBSERVABILITY_DOMAINS),
        "slo_count": len(defs),
        "slos": [d.to_dict() for d in defs],
    }


def score_band(score: float) -> str:
    if score >= SLO_HEALTHY_MIN:
        return "healthy"
    if score >= SLO_DEGRADED_MIN:
        return "degraded"
    return "critical"


def _metric_ok(slo_id: str, domain: dict[str, Any]) -> bool:
    """Per-SLO metric evaluation (not shared domain.slo_ok)."""
    if slo_id == "slo.decision_lifecycle.no_failure_trap":
        return int(domain.get("blocked_ambiguous_count") or 0) == 0 and not bool(
            domain.get("failure_trap")
        )
    if slo_id == "slo.decision_lifecycle.evidence_fresh":
        age = float(domain.get("max_evidence_age_seconds") or 0.0)
        return (not bool(domain.get("stale"))) and age <= STALENESS_THRESHOLD_SECONDS and bool(
            domain.get("data_quality_ok", True)
        )
    if slo_id == "slo.session_lifecycle.no_failed_safe_unacked":
        states = set(domain.get("terminal_failure_states") or [])
        return not bool(domain.get("failed_safe")) and not (states & {"FAILED_SAFE", "BLOCKED"})
    if slo_id == "slo.risk_gates.forbidden_actions_blocked":
        return bool(domain.get("gates_intact", False))
    if slo_id == "slo.execution_simulator.read_only":
        return int(domain.get("mutation_endpoint_count") or 0) == 0
    if slo_id == "slo.provider.capacity_available":
        return not bool(domain.get("capacity_blocked"))
    if slo_id == "slo.reflection.queue_progress":
        return (not bool(domain.get("stale_queue"))) and (
            "provider_capacity" not in (domain.get("active_alert_classes") or [])
        )
    if slo_id == "slo.lesson_gate.fail_closed":
        return int(domain.get("unauthorized_lesson_count") or 0) == 0
    if slo_id == "slo.durability.checkpoint_healthy":
        return (
            int(domain.get("ambiguous_count") or 0) == 0
            and bool(domain.get("data_quality_ok", True))
            and bool(domain.get("checkpoint_ok", True))
        )
    if slo_id == "slo.microstructure.health_visible":
        return (
            bool(domain.get("integrity_ok", True))
            and not bool(domain.get("event_study_started"))
            and str(domain.get("event_study_readiness") or "NOT_READY") == "NOT_READY"
        )
    if slo_id == "slo.storage.floor_ok":
        return bool(domain.get("floor_ok")) and str(domain.get("mode") or "") != "STORAGE_BUDGET_BLOCKED"
    if slo_id == "slo.kill_switch.readiness":
        return bool(domain.get("reachable", False))
    if slo_id == "slo.qualification.all_blocked":
        return bool(domain.get("all_stages_blocked")) and bool(domain.get("hard_bans_intact", True))
    return bool(domain.get("slo_ok", False))


def evaluate_slos(
    *,
    domain_health: dict[str, Any],
    alerts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate each SLO against its metric + alert coverage.

    A SLO passes when its metric is healthy OR an appropriate alert class
    is already raised for the breach (observability must not silently ignore).
    """
    alert_by_class = {a.get("alert_class") for a in alerts if a.get("active")}
    results: list[dict[str, Any]] = []
    for slo in slo_catalog():
        domain = domain_health.get(slo.domain) or {}
        ok = _metric_ok(slo.slo_id, domain)
        domain_alerts = set(domain.get("active_alert_classes") or [])
        covered = ok or any(c in alert_by_class for c in slo.alert_classes)
        if not ok:
            covered = covered or any(c in domain_alerts for c in slo.alert_classes)
        passed_flag = bool(ok or covered)
        results.append(
            {
                "slo_id": slo.slo_id,
                "domain": slo.domain,
                "passed": passed_flag,
                "metric_ok": ok,
                "breach_alerted": (not ok) and passed_flag,
                "severity_on_breach": slo.severity_on_breach,
            }
        )
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    score = round(passed / max(total, 1) * 100, 1)
    return {
        "slo_score": score,
        "status": score_band(score),
        "passed": passed,
        "total": total,
        "results": results,
    }
