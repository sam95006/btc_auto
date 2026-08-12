"""Founder-approved 12H extended observation after inconclusive 6H + same-router probe.

Distinct from ordinary 6H→12H promotion. Never implies 6h_pass / production / 24h / mainnet / real money.
"""
from __future__ import annotations

import os
from typing import Any

GATE_TYPE = "FOUNDER_APPROVED_EXTENDED_OBSERVATION_AFTER_INCONCLUSIVE_6H"
EXACT_PHRASE = "APPROVE_NEXUS_DEMO_12H_V3_EXTENDED_OBSERVATION"
FOUNDER_FLAG = "FOUNDER_APPROVE_12H_AFTER_INCONCLUSIVE_6H_AND_PROBE"
SOURCE_CLASSIFICATION = "DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION"
PROBE_VERDICT = "SAME_ROUTER_DEMO_PROBE_PASS"

_TRUE = {"1", "true", "yes", "on"}


def _i(report: dict[str, Any], *keys: str, default: int = 0) -> int:
    for key in keys:
        if key in report and report.get(key) is not None:
            try:
                return int(report[key])
            except (TypeError, ValueError):
                continue
    return default


def _b(report: dict[str, Any], *keys: str, default: bool = False) -> bool:
    for key in keys:
        if key in report:
            return bool(report.get(key))
    return default


def _s(report: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        if key in report and report.get(key) is not None:
            return str(report.get(key))
    return default


def evaluate_extended_observation_gate(
    report: dict[str, Any],
    *,
    approval_phrase: str | None = None,
) -> dict[str, Any]:
    problems: list[str] = []

    source_class = _s(
        report,
        "canonical_6h_classification",
        "canonical_classification",
        "source_6h_classification",
    )
    if source_class != SOURCE_CLASSIFICATION:
        problems.append("source_6h_classification_not_inconclusive")

    safety = _b(report, "source_6h_operational_safety_pass", "operational_safety_pass", default=False)
    if not safety:
        # Infer from flat MATCH book if explicitly provided.
        inferred = (
            _i(report, "source_6h_final_position_count", "final_position_count", "position_count") == 0
            and _i(report, "source_6h_final_open_order_count", "final_open_order_count", "open_order_count") == 0
            and _s(report, "source_6h_reconciliation", "reconciliation", "reconciliation_final") == "MATCH"
        )
        if not inferred:
            problems.append("source_6h_operational_safety_not_pass")

    if _i(report, "source_6h_final_position_count", "final_position_count", "position_count") != 0:
        problems.append("source_6h_final_position_count_not_zero")
    if _i(report, "source_6h_final_open_order_count", "final_open_order_count", "open_order_count") != 0:
        problems.append("source_6h_final_open_order_count_not_zero")
    recon = _s(report, "source_6h_reconciliation", "reconciliation", "reconciliation_final", "final_reconciliation")
    if recon != "MATCH":
        problems.append("source_6h_reconciliation_not_match")

    probe_verdict = _s(report, "same_router_probe_verdict", "probe_verdict", "verdict")
    probe_pass = probe_verdict == PROBE_VERDICT or _b(report, "same_router_probe_pass", default=False)
    if not probe_pass:
        problems.append("same_router_probe_not_pass")

    if not _b(report, "same_router_order_route_verified", "order_route_verified", default=False):
        problems.append("same_router_order_route_verified_required")
    if not _b(report, "same_router_fill_confirmed", "fill_confirmed", default=False):
        problems.append("same_router_fill_confirmed_required")
    if not _b(report, "same_router_protection_verified", "protection_verified", default=False):
        problems.append("same_router_protection_verified_required")
    if not _b(report, "same_router_controlled_close_completed", "controlled_close_completed", default=False):
        problems.append("same_router_controlled_close_completed_required")

    flat = _b(report, "same_router_final_account_flat", default=False) or (
        _i(report, "final_position_count", "position_count_final") == 0
        and _i(report, "final_open_order_count", "open_order_count_final") == 0
        and _s(report, "final_reconciliation", "reconciliation_final") == "MATCH"
    )
    if not flat:
        problems.append("same_router_final_account_not_flat")

    for key in (
        "duplicate_order_count",
        "unprotected_position_count",
        "protection_incident_count",
        "reconciliation_incident_count",
    ):
        if _i(report, key) != 0:
            problems.append(key)

    flag = (os.environ.get(FOUNDER_FLAG) or "").strip().lower() in _TRUE or _b(
        report, FOUNDER_FLAG, "founder_approve_12h_after_inconclusive_6h_and_probe", default=False
    )
    if not flag:
        problems.append("founder_extended_observation_flag_missing")

    phrase = (approval_phrase or _s(report, "approval_phrase", "exact_phrase")).strip()
    if phrase != EXACT_PHRASE:
        problems.append("exact_phrase_mismatch")

    if (os.environ.get("MAINNET") or "").strip().lower() in _TRUE or _b(report, "mainnet", default=False):
        problems.append("mainnet_forbidden")
    if (os.environ.get("REAL_MONEY") or "").strip().lower() in _TRUE or _b(report, "real_money", default=False):
        problems.append("real_money_forbidden")

    allowed = len(problems) == 0
    return {
        "gate_type": GATE_TYPE,
        "gate_pass": allowed,
        "12H_ALLOWED": allowed,
        "problems": problems,
        "source_6h_classification": source_class,
        "same_router_probe_verdict": probe_verdict or (PROBE_VERDICT if probe_pass else ""),
        "exact_phrase_required": EXACT_PHRASE,
        "exact_phrase_received": phrase,
        "implies_6h_pass": False,
        "implies_production_ready": False,
        "implies_24h_approved": False,
        "implies_mainnet": False,
        "implies_real_money": False,
        "6h_pass": False,
        "production_ready": False,
        "24h_approved": False,
        "mainnet": False,
        "real_money": False,
        "purpose": "EXTENDED_DEMO_OBSERVATION_AFTER_INCONCLUSIVE_6H",
    }
