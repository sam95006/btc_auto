"""Training / validation / embargo / purge window construction (plan-only)."""
from __future__ import annotations

from typing import Any

from backend.nexus_formal_wf_plan.constants import (
    DEFAULT_EMBARGO_DAYS,
    DEFAULT_MAX_FOLDS,
    DEFAULT_PURGE_DAYS,
    DEFAULT_STEP_DAYS,
    DEFAULT_TRAINING_DAYS,
    DEFAULT_VALIDATION_DAYS,
    MS_PER_DAY,
)


def _days_to_ms(days: int) -> int:
    return int(days) * MS_PER_DAY


def build_embargo_spec(*, embargo_days: int = DEFAULT_EMBARGO_DAYS) -> dict[str, Any]:
    return {
        "kind": "embargo",
        "embargo_days": int(embargo_days),
        "embargo_ms": _days_to_ms(embargo_days),
        "purpose": "Separate training labels from validation to reduce leakage",
        "executed": False,
    }


def build_purge_spec(*, purge_days: int = DEFAULT_PURGE_DAYS) -> dict[str, Any]:
    return {
        "kind": "purge",
        "purge_days": int(purge_days),
        "purge_ms": _days_to_ms(purge_days),
        "purpose": "Purge overlapping label horizons across train/validation boundary",
        "executed": False,
    }


def build_fold_windows(
    *,
    development_start_ms: int,
    development_end_ms: int,
    training_days: int = DEFAULT_TRAINING_DAYS,
    validation_days: int = DEFAULT_VALIDATION_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
    embargo_days: int = DEFAULT_EMBARGO_DAYS,
    purge_days: int = DEFAULT_PURGE_DAYS,
    max_folds: int = DEFAULT_MAX_FOLDS,
) -> dict[str, Any]:
    """Compile rolling train/validation folds inside a development interval.

    Does not evaluate any fold. Embargo and purge are recorded as plan
    constraints between train end and validation start.
    """
    if development_end_ms < development_start_ms:
        raise ValueError("development_interval_inverted")

    train_ms = _days_to_ms(training_days)
    val_ms = _days_to_ms(validation_days)
    step_ms = _days_to_ms(step_days)
    embargo_ms = _days_to_ms(embargo_days)
    purge_ms = _days_to_ms(purge_days)
    gap_ms = embargo_ms + purge_ms

    folds: list[dict[str, Any]] = []
    cursor = development_start_ms
    fold_idx = 0
    while fold_idx < max_folds:
        train_start = cursor
        train_end = train_start + train_ms - 1
        val_start = train_end + 1 + gap_ms
        val_end = val_start + val_ms - 1
        if val_end > development_end_ms:
            break
        folds.append(
            {
                "fold_id": f"WF_PLAN_FOLD_{fold_idx:02d}",
                "fold_index": fold_idx,
                "role": "planned_not_executed",
                "training_window": {
                    "start_ms": train_start,
                    "end_ms": train_end,
                    "duration_ms": train_ms,
                    "executed": False,
                },
                "validation_window": {
                    "start_ms": val_start,
                    "end_ms": val_end,
                    "duration_ms": val_ms,
                    "executed": False,
                },
                "embargo": {
                    "start_ms": train_end + 1,
                    "end_ms": train_end + embargo_ms,
                    "embargo_days": embargo_days,
                    "executed": False,
                },
                "purge_interval": {
                    "start_ms": train_end + 1 + embargo_ms,
                    "end_ms": train_end + gap_ms,
                    "purge_days": purge_days,
                    "executed": False,
                },
                "formal_walk_forward_executed": False,
            }
        )
        cursor += step_ms
        fold_idx += 1

    return {
        "development_interval": {
            "start_ms": development_start_ms,
            "end_ms": development_end_ms,
        },
        "training_days": training_days,
        "validation_days": validation_days,
        "step_days": step_days,
        "embargo": build_embargo_spec(embargo_days=embargo_days),
        "purge_intervals": build_purge_spec(purge_days=purge_days),
        "folds": folds,
        "fold_count": len(folds),
        "training_windows": [f["training_window"] for f in folds],
        "validation_windows": [f["validation_window"] for f in folds],
        "all_folds_unexecuted": all(
            f["formal_walk_forward_executed"] is False for f in folds
        ),
    }
