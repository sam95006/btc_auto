"""Six-role review completeness for 6H V2. Risk Critic is mandatory with veto."""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.v2_policy import SIX_ROLES


def evaluate_six_role_review(reviews: dict[str, Any] | None) -> dict[str, Any]:
    reviews = reviews or {}
    missing = [r for r in SIX_ROLES if r not in reviews or not isinstance(reviews.get(r), dict)]
    if missing:
        return {
            "ok": False,
            "allowed": False,
            "reason": "ROLE_REVIEW_INCOMPLETE",
            "missing_roles": missing,
            "risk_critic_veto": False,
            "labels": ["ROLE_REVIEW_INCOMPLETE", "NEW_ENTRY_BLOCKED"],
        }
    risk = reviews.get("risk_critic") or {}
    verdict = str(risk.get("verdict") or "").upper()
    if verdict in {"VETO", "BLOCK", "REJECT"}:
        return {
            "ok": True,
            "allowed": False,
            "reason": "RISK_CRITIC_VETO",
            "missing_roles": [],
            "risk_critic_veto": True,
            "labels": ["RISK_CRITIC_VETO", "NEW_ENTRY_BLOCKED", "veto_override=false"],
        }
    return {
        "ok": True,
        "allowed": True,
        "reason": "ROLE_REVIEW_COMPLETE",
        "missing_roles": [],
        "risk_critic_veto": False,
        "labels": ["ROLE_REVIEW_COMPLETE", "risk_critic_mandatory=true"],
    }


def stub_complete_roles(*, risk_verdict: str = "ALLOW") -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for role in SIX_ROLES:
        out[role] = {
            "role": role,
            "verdict": risk_verdict if role == "risk_critic" else "ALLOW",
            "mandatory": role == "risk_critic",
            "veto_override": False,
        }
    return out
