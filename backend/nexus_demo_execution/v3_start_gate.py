"""Machine gate: 12H V3 may start only after 6H V2 hard PASS (+ non-blocking findings)."""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.v3_policy import (
    ALLOWED_SOURCE_6H_RECOMMENDATIONS,
    BLOCKING_6H_FINDINGS,
)


def _i(report: dict[str, Any], key: str, default: int = -999) -> int:
    if key not in report or report.get(key) is None:
        return default
    return int(report[key])


def evaluate_12h_machine_gate(report_6h: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    rec = str(report_6h.get("recommendation") or "")
    if rec not in ALLOWED_SOURCE_6H_RECOMMENDATIONS:
        problems.append("6h_recommendation_not_allowed")
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

    # Must be a new session — caller supplies ids.
    if report_6h.get("session_id") and report_6h.get("proposed_12h_session_id"):
        if report_6h["session_id"] == report_6h["proposed_12h_session_id"]:
            problems.append("shared_session_id_forbidden")

    return {
        "machine_gate_pass": len(problems) == 0,
        "problems": problems,
        "founder_gate": "CONDITIONALLY_APPROVED",
        "source_6h_session_id": report_6h.get("session_id"),
        "source_6h_recommendation": rec,
        "auto_start_24h": False,
    }
