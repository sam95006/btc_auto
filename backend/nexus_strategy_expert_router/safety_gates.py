"""AI cannot set leverage or override Risk Gate."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_strategy_expert_router.constants import FIXED_LEVERAGE
from backend.nexus_strategy_expert_router.hard_bans import HardBanViolation


class SafetyGateRejected(RuntimeError):
    """Raised when AI attempts forbidden safety mutations."""


def refuse_ai_leverage_mutation(requested: int | float | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "applied": False,
        "action": "AI_SET_LEVERAGE",
        "requested_leverage": requested,
        "fixed_leverage": FIXED_LEVERAGE,
        "reason": "AI_CANNOT_SET_LEVERAGE",
    }


def refuse_ai_risk_gate_override(
    *,
    risk_gate_reason: str | None = None,
    attempted_fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "allowed": False,
        "applied": False,
        "action": "AI_OVERRIDE_RISK_GATE",
        "risk_gate_reason": risk_gate_reason,
        "attempted_fields": list(attempted_fields or []),
        "reason": "AI_CANNOT_OVERRIDE_RISK_GATE",
    }


def resolve_leverage(
    *,
    requested_leverage: int | float | None,
    ai_attempt_set_leverage: bool = False,
) -> dict[str, Any]:
    """Always return FIXED_LEVERAGE; record AI mutation attempts as blocked."""
    out = {
        "leverage": FIXED_LEVERAGE,
        "ai_set_leverage_attempted": bool(ai_attempt_set_leverage)
        or (
            requested_leverage is not None
            and int(requested_leverage) != FIXED_LEVERAGE
        ),
        "ai_set_leverage_applied": False,
        "leverage_ai_mutation_blocked": True,
        "refusal": None,
    }
    if out["ai_set_leverage_attempted"]:
        out["refusal"] = refuse_ai_leverage_mutation(requested_leverage)
    return out


def honor_risk_gate(
    *,
    risk_gate_allow: bool,
    risk_gate_reason: str,
    ai_override_attempt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Risk Gate decision is authoritative; AI override never applies."""
    out: dict[str, Any] = {
        "risk_gate_allow": bool(risk_gate_allow),
        "risk_gate_reason": risk_gate_reason,
        "risk_gate_honored": True,
        "ai_override_risk_gate_attempted": False,
        "ai_override_risk_gate_applied": False,
        "refusal": None,
        "effective_allow": bool(risk_gate_allow),
    }
    if not ai_override_attempt:
        return out

    attempted = [
        k
        for k in ai_override_attempt.keys()
        if k
        in {
            "risk_gate_allow",
            "risk_gate_reason",
            "override_risk_gate",
            "force_allow",
            "bypass_risk_gate",
        }
    ]
    if not attempted and ai_override_attempt.get("override_risk_gate"):
        attempted = ["override_risk_gate"]
    if ai_override_attempt.get("override_risk_gate") or ai_override_attempt.get(
        "force_allow"
    ) or ai_override_attempt.get("bypass_risk_gate"):
        attempted = list(dict.fromkeys(attempted + ["override_risk_gate"]))

    if attempted:
        out["ai_override_risk_gate_attempted"] = True
        out["ai_override_risk_gate_applied"] = False
        out["refusal"] = refuse_ai_risk_gate_override(
            risk_gate_reason=risk_gate_reason,
            attempted_fields=attempted,
        )
        # Never flip a blocked gate to allow.
        out["effective_allow"] = bool(risk_gate_allow)
    return out


def apply_ai_safety_suggestion(
    decision: dict[str, Any],
    suggestion: dict[str, Any] | None,
) -> dict[str, Any]:
    """Annotate AI suggestions without mutating leverage or risk-gate fields."""
    out = deepcopy(decision)
    out["ai_set_leverage_applied"] = False
    out["ai_override_risk_gate_applied"] = False
    if not suggestion:
        out["ai_safety_override_attempted"] = False
        return out

    protected = {
        "leverage",
        "risk_gate_allow",
        "risk_gate_reason",
        "risk_gate_honored",
        "effective_allow",
        "side",
        "expert_id",
        "no_trade",
    }
    attempted = [k for k in suggestion if k in protected]
    out["ai_safety_override_attempted"] = bool(attempted)
    if "leverage" in suggestion:
        out["ai_set_leverage_attempted"] = True
        out["leverage_refusal"] = refuse_ai_leverage_mutation(suggestion.get("leverage"))
    if any(
        k in suggestion
        for k in ("risk_gate_allow", "risk_gate_reason", "override_risk_gate", "force_allow")
    ):
        out["ai_override_risk_gate_attempted"] = True
        out["risk_gate_refusal"] = refuse_ai_risk_gate_override(
            risk_gate_reason=str(out.get("risk_gate_reason") or ""),
            attempted_fields=attempted,
        )
    # Explicitly do not merge protected fields.
    out["ai_annotation"] = {k: v for k, v in suggestion.items() if k not in protected}
    out["leverage"] = FIXED_LEVERAGE
    return out


def assert_safety_invariants(decision: dict[str, Any]) -> None:
    if decision.get("ai_set_leverage_applied") is True:
        raise SafetyGateRejected("ai_set_leverage_applied_forbidden")
    if decision.get("ai_override_risk_gate_applied") is True:
        raise SafetyGateRejected("ai_override_risk_gate_applied_forbidden")
    if int(decision.get("leverage", FIXED_LEVERAGE)) != FIXED_LEVERAGE:
        raise HardBanViolation("no_ai_set_leverage:leverage_drift")
    if decision.get("risk_gate_honored") is False:
        raise HardBanViolation("no_ai_override_risk_gate:not_honored")
