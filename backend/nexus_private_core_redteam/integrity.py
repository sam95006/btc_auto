"""V15-L integrity oracles — research/autonomy false-pass detectors.

Reuses V14 research seals for shared attacks and adds Private Core gates:
duplicate lifecycle, risk bypass, lesson-before-reflection, capacity-as-quality,
and development/OOS confusion.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_research_redteam.research_integrity import (  # noqa: F401
    CONTROL_FIXTURE_LABEL,
    REAL_PERFORMANCE_LABEL,
    classify_provider_status,
    detect_candidate_relabeling,
    detect_cost_omission,
    detect_counter_inflation,
    detect_fabricated_universe,
    detect_fixture_as_real,
    detect_provider_failure_as_quality,
    detect_result_cherry_picking,
    seal_research_result,
    verify_research_result_seal,
)

CAPACITY_TERMINAL_STATUSES = frozenset(
    {
        "INCOMPLETE_PROVIDER_CAPACITY",
        "PROVIDER_CAPACITY_BLOCKED",
        "PARTIAL_PROVIDER_CAPACITY",
        "TIMEOUT",
        "RATE_LIMITED",
        "CIRCUIT_OPEN",
        "PROVIDER_UNAVAILABLE",
    }
)

DATA_CLASSES = frozenset(
    {
        "DEVELOPMENT",
        "VALIDATION_PLANNING",
        "OOS_RESERVED",
        "OOS_UNTOUCHED",
    }
)


def detect_development_oos_confusion(
    *,
    claimed_class: str,
    sealed_class: str,
    consumed: bool,
) -> dict[str, Any]:
    """Development must not be relabeled as OOS; OOS must not be consumed."""
    claimed = str(claimed_class or "").upper()
    sealed = str(sealed_class or "").upper()
    unknown = claimed not in DATA_CLASSES or sealed not in DATA_CLASSES
    relabel = claimed != sealed
    oos_consumed = sealed in {"OOS_RESERVED", "OOS_UNTOUCHED"} and bool(consumed)
    development_as_oos = sealed == "DEVELOPMENT" and claimed in {"OOS_RESERVED", "OOS_UNTOUCHED"}
    oos_as_development = sealed in {"OOS_RESERVED", "OOS_UNTOUCHED"} and claimed == "DEVELOPMENT"
    hole = unknown or relabel or oos_consumed or development_as_oos or oos_as_development
    return {
        "ok": not hole,
        "status": "DEVELOPMENT_OOS_CONFUSION" if hole else "PASS",
        "claimed_class": claimed,
        "sealed_class": sealed,
        "consumed": bool(consumed),
        "relabel": relabel,
        "oos_consumed": oos_consumed,
        "development_as_oos": development_as_oos,
        "oos_as_development": oos_as_development,
    }


def detect_duplicate_lifecycle(
    *,
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    """Same idempotency key must not create a second lifecycle object."""
    first_dup = bool(first.get("duplicate"))
    second_dup = bool(second.get("duplicate"))
    first_id = (first.get("decision") or {}).get("decision_id") or first.get("decision_id")
    second_id = (second.get("decision") or {}).get("decision_id") or second.get("decision_id")
    created_twice = (
        first.get("status") not in {None, "DUPLICATE_IGNORED"}
        and second.get("status") not in {None, "DUPLICATE_IGNORED"}
        and first_id
        and second_id
        and first_id != second_id
        and not second_dup
    )
    honest_dup = (not first_dup) and second_dup and first_id == second_id
    ok = honest_dup and not created_twice
    return {
        "ok": ok,
        "status": "PASS" if ok else "DUPLICATE_LIFECYCLE",
        "first_id": first_id,
        "second_id": second_id,
        "second_duplicate": second_dup,
        "created_twice": created_twice,
    }


def detect_risk_bypass(
    *,
    decision_allowed: bool,
    reason: str,
    forbidden_hit: bool,
    leverage: int | None = None,
) -> dict[str, Any]:
    """Forbidden risk actions / ceiling breaches must never be allowed."""
    reason_u = str(reason or "")
    leverage_bypass = leverage is not None and int(leverage) >= 100 and decision_allowed
    forbidden_allowed = bool(forbidden_hit) and bool(decision_allowed)
    missing_reject = bool(forbidden_hit) and "REJECT" not in reason_u.upper() and not (
        "FORBIDDEN" in reason_u.upper() or "CEILING" in reason_u.upper() or "HARD_RISK" in reason_u.upper()
    )
    # missing_reject only matters when the gate claimed to evaluate a forbidden action
    hole = leverage_bypass or forbidden_allowed or (bool(forbidden_hit) and decision_allowed)
    if bool(forbidden_hit) and not decision_allowed and "HARD_RISK" not in reason_u.upper() and "FORBIDDEN" not in reason_u.upper() and "CEILING" not in reason_u.upper() and "LEVERAGE" not in reason_u.upper():
        hole = True
        missing_reject = True
    return {
        "ok": not hole,
        "status": "RISK_BYPASS" if hole else "PASS",
        "decision_allowed": decision_allowed,
        "reason": reason_u,
        "forbidden_hit": bool(forbidden_hit),
        "leverage_bypass": leverage_bypass,
        "forbidden_allowed": forbidden_allowed,
        "missing_reject": missing_reject,
    }


def detect_lesson_before_reflection(
    *,
    reflection_terminal_status: str | None,
    lesson_executed: bool,
    reflection_complete: bool,
) -> dict[str, Any]:
    """Lessons must not execute before Reflection reaches VERIFIED."""
    terminal = str(reflection_terminal_status or "").upper()
    verified = terminal == "VERIFIED"
    premature = bool(lesson_executed) and (not verified or not reflection_complete)
    ok = not premature
    return {
        "ok": ok,
        "status": "PASS" if ok else "LESSON_BEFORE_REFLECTION",
        "terminal": terminal,
        "lesson_executed": bool(lesson_executed),
        "reflection_complete": bool(reflection_complete),
        "verified": verified,
    }


def detect_capacity_as_quality(
    *,
    provider_or_terminal_status: str,
    claimed_as_quality: bool = False,
    claimed_quality_pass: bool = False,
) -> dict[str, Any]:
    """Provider capacity / transport incompleteness must not be sold as quality."""
    status = str(provider_or_terminal_status or "").upper()
    is_capacity = status in CAPACITY_TERMINAL_STATUSES or "CAPACITY" in status
    transport = classify_provider_status(status)
    transport_bucket = transport.get("is_transport_failure") is True
    hole = (is_capacity or transport_bucket) and (
        bool(claimed_as_quality) or bool(claimed_quality_pass)
    )
    # Also: capacity terminal claimed as VERIFIED quality.
    if status in CAPACITY_TERMINAL_STATUSES and claimed_quality_pass:
        hole = True
    return {
        "ok": not hole,
        "status": "CAPACITY_AS_QUALITY" if hole else "PASS",
        "provider_or_terminal_status": status,
        "is_capacity": is_capacity,
        "is_transport_failure": transport_bucket,
        "claimed_as_quality": bool(claimed_as_quality),
        "claimed_quality_pass": bool(claimed_quality_pass),
    }
