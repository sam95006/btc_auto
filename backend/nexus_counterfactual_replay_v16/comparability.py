"""Comparability and coverage marking for counterfactual paths."""
from __future__ import annotations

from typing import Any

from backend.nexus_counterfactual_replay_v16.constants import (
    COMPARABILITY_GRADES,
    COVERAGE_STATES,
    SCHEMA_COMPARABILITY,
)


def mark_comparability(
    *,
    pit_ok: bool,
    cost_included: bool,
    path_series_complete: bool,
    data_trust_ok: bool,
    same_symbol: bool = True,
    same_side_semantics: bool = True,
) -> dict[str, Any]:
    """Every CF result must declare comparability + coverage explicitly."""
    if not pit_ok:
        coverage = "MISSING_PIT"
        grade = "BLOCKED_INSUFFICIENT_COVERAGE"
    elif not cost_included:
        coverage = "MISSING_COST"
        grade = "NOT_COMPARABLE"
    elif not path_series_complete:
        coverage = "MISSING_PATH_SERIES"
        grade = "PARTIALLY_COMPARABLE"
    elif not data_trust_ok:
        coverage = "LOW_DATA_TRUST"
        grade = "BLOCKED_INSUFFICIENT_COVERAGE"
    elif not same_symbol or not same_side_semantics:
        coverage = "PARTIAL"
        grade = "PARTIALLY_COMPARABLE"
    else:
        coverage = "COMPLETE"
        grade = "FULLY_COMPARABLE"

    assert coverage in COVERAGE_STATES
    assert grade in COMPARABILITY_GRADES
    return {
        "schema": SCHEMA_COMPARABILITY,
        "comparability": grade,
        "coverage": coverage,
        "pit_ok": pit_ok,
        "cost_included": cost_included,
        "path_series_complete": path_series_complete,
        "data_trust_ok": data_trust_ok,
        "same_symbol": same_symbol,
        "same_side_semantics": same_side_semantics,
        "usable_for_promotion": False,
        "usable_as_real_performance": False,
    }
