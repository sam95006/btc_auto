"""AI cannot override deterministic risk/capacity review results."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


class AIOverrideRejected(RuntimeError):
    """Raised when an AI or external agent attempts to mutate review outcomes."""


def refuse_ai_override(
    *,
    candidate_id: str | None = None,
    attempted_fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "allowed": False,
        "applied": False,
        "action": "AI_OVERRIDE",
        "candidate_id": candidate_id,
        "attempted_fields": list(attempted_fields or []),
        "reason": "AI_CANNOT_OVERRIDE_DETERMINISTIC_RISK_CAPACITY_REVIEW",
        "ai_override_attempted": True,
        "ai_override_applied": False,
    }


def refuse_strategy_promotion(candidate_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "promoted": False,
        "action": "STRATEGY_PROMOTION",
        "candidate_id": candidate_id,
        "reason": "STRATEGY_PROMOTION_BANNED_V15_H",
    }


def refuse_strategy_selection(candidate_id: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "selected": False,
        "action": "STRATEGY_SELECTION",
        "candidate_id": candidate_id,
        "reason": "STRATEGY_SELECTION_BANNED_V15_H",
    }


_PROTECTED_FIELDS = frozenset(
    {
        "label",
        "gross_expectancy",
        "net_expectancy",
        "cost_components",
        "break_even_cost",
        "maximum_viable_spread",
        "maximum_viable_slippage",
        "capacity_estimate",
        "fragility_score",
        "concentration_review",
        "drawdown_review",
        "liquidation_distance_review",
        "data_quality_review",
        "deterministic_fingerprint",
        "qualified",
        "qualification_ready",
        "strategy_promoted",
        "strategy_selected",
        "status",
    }
)


def apply_ai_suggestion(
    record: dict[str, Any],
    suggestion: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attempt to apply an AI suggestion — always rejected for protected fields.

    Returns a copy of ``record`` unchanged. Sets ``ai_override_attempted`` when
    a suggestion touched protected fields. Never mutates review outcomes.
    """
    out = deepcopy(record)
    out["ai_override_applied"] = False
    if not suggestion:
        out["ai_override_attempted"] = False
        out["ai_override_refusal"] = None
        return out

    attempted = [k for k in suggestion.keys() if k in _PROTECTED_FIELDS]
    if attempted:
        refusal = refuse_ai_override(
            candidate_id=str(out.get("candidate_id") or ""),
            attempted_fields=attempted,
        )
        out["ai_override_attempted"] = True
        out["ai_override_refusal"] = refusal
        # Explicitly do NOT merge suggestion into protected fields.
        return out

    # Non-protected metadata may be annotated but cannot change review truth.
    out["ai_override_attempted"] = False
    out["ai_override_refusal"] = None
    out["ai_annotation"] = {
        k: v for k, v in suggestion.items() if k not in _PROTECTED_FIELDS
    }
    return out


def assert_no_ai_override(record: dict[str, Any]) -> None:
    if record.get("ai_override_applied") is True:
        raise AIOverrideRejected(
            f"ai_override_applied_forbidden candidate={record.get('candidate_id')}"
        )
    if record.get("strategy_promoted") is True:
        raise AIOverrideRejected(
            f"strategy_promoted_forbidden candidate={record.get('candidate_id')}"
        )
