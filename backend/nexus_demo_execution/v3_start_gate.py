"""Machine gate: 12H V3 requires operational safety AND autonomous execution evidence.

Orchestrator PASS_WITH_FINDINGS alone must not approve 12H when entries_total==0.
Runtime FAILED / INCONCLUSIVE_NO_EXECUTION blocks promotion.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.v3_policy import (
    ALLOWED_SOURCE_6H_RECOMMENDATIONS,
    BLOCKING_6H_FINDINGS,
    INCONCLUSIVE_6H_RECOMMENDATIONS,
)


def _i(report: dict[str, Any], key: str, default: int = -999) -> int:
    if key not in report or report.get(key) is None:
        return default
    return int(report[key])


def _b(report: dict[str, Any], key: str, default: bool = False) -> bool:
    if key not in report:
        return default
    return bool(report.get(key))


def classify_execution_evidence(report_6h: dict[str, Any]) -> dict[str, Any]:
    """Separate operational safety from autonomous execution proof."""
    entries = _i(report_6h, "entries_total", 0)
    if entries < 0:
        entries = _i(report_6h, "entries", 0)
    completed = _i(report_6h, "completed_trades_total", 0)
    if completed < 0:
        completed = _i(report_6h, "completed_trades", 0)
    outcomes = _i(report_6h, "completed_outcomes", 0)
    reflections = _i(report_6h, "reflections_total", 0)
    order_route = _b(report_6h, "order_route_verified", False)
    exchange_accepted = _i(report_6h, "exchange_accepted_total", 0)

    autonomous_execution_observed = bool(
        entries > 0 or completed > 0 or exchange_accepted > 0 or order_route
    )
    completed_outcome_observed = bool(outcomes > 0 or completed > 0)
    learning_chain_observed = bool(completed_outcome_observed and reflections > 0)

    rec = str(report_6h.get("recommendation") or report_6h.get("runtime_recommendation_sot") or "")
    canonical = str(
        report_6h.get("canonical_6h_classification")
        or report_6h.get("canonical_classification")
        or ""
    )

    # Prefer explicit runtime SoT when present.
    runtime_sot = str(report_6h.get("runtime_recommendation_sot") or rec)
    operational_safety_pass = bool(
        report_6h.get("operational_safety_pass")
        if "operational_safety_pass" in report_6h
        else (
            report_6h.get("session_completed") is True
            and report_6h.get("write_window_closed") is True
            and _i(report_6h, "position_count", 0) == 0
            and _i(report_6h, "open_order_count", 0) == 0
            and str(report_6h.get("reconciliation") or "") == "MATCH"
            and _i(report_6h, "duplicate_order_count", 0) == 0
            and _i(report_6h, "unprotected_position_count", 0) == 0
            and _i(report_6h, "protection_incident_count", 0) == 0
        )
    )

    if canonical == "DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION":
        autonomous_execution_observed = False
    if runtime_sot in INCONCLUSIVE_6H_RECOMMENDATIONS or runtime_sot == "DEMO_AUTONOMOUS_6H_V2_FAILED":
        # Zero-entry FAILED is inconclusive for autonomous execution, not a safety crash by itself.
        if entries == 0 and completed == 0:
            autonomous_execution_observed = False

    return {
        "operational_safety_pass": operational_safety_pass,
        "autonomous_execution_observed": autonomous_execution_observed,
        "order_route_verified": order_route,
        "completed_outcome_observed": completed_outcome_observed,
        "learning_chain_observed": learning_chain_observed,
        "runtime_recommendation_sot": runtime_sot,
        "canonical_6h_classification": canonical
        or (
            "DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION"
            if entries == 0 and operational_safety_pass
            else runtime_sot
        ),
        "entries_total": entries,
        "completed_trades_total": completed,
    }


def evaluate_12h_machine_gate(report_6h: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    evidence = classify_execution_evidence(report_6h)

    # Never let a looser orchestrator summary override Runtime SoT / zero-entry reality.
    runtime_sot = evidence["runtime_recommendation_sot"]
    orch = str(report_6h.get("orchestrator_recommendation") or "")
    if orch and orch != runtime_sot and _i(report_6h, "entries_total", 0) == 0:
        problems.append("orchestrator_cannot_override_runtime_zero_execution")

    if runtime_sot in INCONCLUSIVE_6H_RECOMMENDATIONS:
        problems.append("6h_inconclusive_no_execution")
    elif runtime_sot not in ALLOWED_SOURCE_6H_RECOMMENDATIONS:
        problems.append("6h_recommendation_not_allowed")

    if not evidence["operational_safety_pass"]:
        problems.append("operational_safety_not_pass")
    if not evidence["autonomous_execution_observed"]:
        problems.append("autonomous_execution_not_observed")
    if not evidence["order_route_verified"] and not _b(report_6h, "same_router_probe_pass", False):
        problems.append("order_route_not_verified")
    if report_6h.get("session_completed") is not True:
        problems.append("6h_not_completed")
    if report_6h.get("write_window_closed") is not True:
        problems.append("6h_write_window_open")
    if _i(report_6h, "position_count") != 0:
        problems.append("6h_positions")
    if _i(report_6h, "open_order_count") != 0:
        problems.append("6h_orders")
    if str(report_6h.get("reconciliation") or "") != "MATCH":
        problems.append("6h_reconciliation")
    for key in (
        "duplicate_order_count",
        "unprotected_position_count",
        "protection_incident_count",
        "runtime_stall_count",
    ):
        if _i(report_6h, key, 0) != 0:
            problems.append(key)
    if report_6h.get("export_complete") is not True:
        problems.append("6h_export_incomplete")

    findings = set(report_6h.get("findings") or [])
    blocking = sorted(findings & BLOCKING_6H_FINDINGS)
    if blocking:
        problems.append("blocking_findings:" + ",".join(blocking))

    if report_6h.get("session_id") and report_6h.get("proposed_12h_session_id"):
        if report_6h["session_id"] == report_6h["proposed_12h_session_id"]:
            problems.append("shared_session_id_forbidden")

    # Explicit zero-entry ban for promotion.
    if _i(report_6h, "entries_total", 0) == 0 and not _b(report_6h, "same_router_probe_pass", False):
        problems.append("zero_entries_without_same_router_probe")

    gate_pass = len(problems) == 0
    return {
        "machine_gate_pass": gate_pass,
        "12H_ALLOWED": gate_pass,
        "problems": problems,
        "founder_gate": "CONDITIONALLY_APPROVED",
        "source_6h_session_id": report_6h.get("session_id"),
        "source_6h_recommendation": runtime_sot,
        "auto_start_24h": False,
        **evidence,
    }
