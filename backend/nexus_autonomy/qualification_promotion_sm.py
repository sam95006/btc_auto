"""Promotion state machine + Founder authorization gate.

Fail-closed by default. Never promotes a real strategy. Never executes
Walk-forward / OOS / Demo. Synthetic fixtures only.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_autonomy.qualification_checksums import sha_obj

# Ordered qualification stages. All default BLOCKED.
QUALIFICATION_STAGES: tuple[str, ...] = (
    "CANDIDATE_FREEZE",
    "REPLAY",
    "CHRONOLOGICAL_WALK_FORWARD",
    "CONCENTRATION_REVIEW",
    "COST_STRESS",
    "RISK_REVIEW",
    "UNTOUCHED_OOS_RESERVATION",
    "OOS_EXECUTION_AUTHORIZATION",
    "DEMO_ELIGIBILITY",
)

STAGE_STATUS_BLOCKED = "BLOCKED"
STAGE_STATUS_READY = "READY"  # infrastructure wired, still not executed
STAGE_STATUS_PASSED = "PASSED"  # reserved for future; never set by V1 dry-run
STAGE_STATUS_FAILED = "FAILED"

PROMOTION_STATES: tuple[str, ...] = (
    "UNINITIALIZED",
    "INFRASTRUCTURE_READY",
    "CANDIDATE_REGISTERED_SYNTHETIC",
    "AWAITING_FOUNDER_AUTHORIZATION",
    "AUTHORIZED_BUT_STAGES_BLOCKED",
    "PROMOTION_BLOCKED",
    "PROMOTED",  # unreachable without explicit Founder override + all stages PASSED
)

FOUNDER_AUTH_REQUIRED = "FOUNDER_AUTHORIZATION_REQUIRED"
FOUNDER_AUTH_DENIED = "FOUNDER_AUTHORIZATION_DENIED"
FOUNDER_AUTH_GRANTED = "FOUNDER_AUTHORIZATION_GRANTED"
FOUNDER_AUTH_MISSING = "FOUNDER_AUTHORIZATION_MISSING"


@dataclass
class FounderAuthorizationGate:
    """Fail-closed gate. Empty/missing token never authorizes."""

    required_scope: str = "formal_qualification_v1"
    authorized: bool = False
    actor: str | None = None
    token_fingerprint: str | None = None
    reason: str = FOUNDER_AUTH_MISSING
    metadata: dict[str, Any] = field(default_factory=dict)

    def evaluate(self, request: dict[str, Any] | None) -> dict[str, Any]:
        req = dict(request or {})
        token = str(req.get("founder_authorization_token") or "").strip()
        actor = str(req.get("actor") or "").strip() or None
        scope = str(req.get("scope") or "").strip()
        explicit = bool(req.get("explicit_authorize") is True)

        if not token:
            self.authorized = False
            self.actor = actor
            self.token_fingerprint = None
            self.reason = FOUNDER_AUTH_MISSING
            return self.to_dict()

        # Token present but must be explicit + correct scope. Never auto-grant
        # from ambient env. V1 dry-run never grants promotion authority.
        fingerprint = sha_obj({"token_len": len(token), "prefix": token[:4]})
        self.token_fingerprint = fingerprint
        self.actor = actor

        if not explicit:
            self.authorized = False
            self.reason = FOUNDER_AUTH_REQUIRED
            return self.to_dict()
        if scope != self.required_scope:
            self.authorized = False
            self.reason = FOUNDER_AUTH_DENIED
            self.metadata = {"expected_scope": self.required_scope, "got_scope": scope}
            return self.to_dict()

        # Even with a well-formed request, V1 infrastructure never grants
        # promotion. Authorization here only means "gate evaluated".
        # Real promotion requires a future Founder-signed package.
        self.authorized = False
        self.reason = FOUNDER_AUTH_DENIED
        self.metadata = {
            "note": "v1_dry_run_never_grants_promotion",
            "scope_matched": True,
            "explicit": True,
        }
        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_scope": self.required_scope,
            "authorized": self.authorized,
            "actor": self.actor,
            "token_fingerprint": self.token_fingerprint,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass
class PromotionStateMachine:
    """Promotion SM — defaults to PROMOTION_BLOCKED for all real outcomes."""

    state: str = "UNINITIALIZED"
    stages: dict[str, str] = field(default_factory=dict)
    founder_gate: FounderAuthorizationGate = field(default_factory=FounderAuthorizationGate)
    history: list[dict[str, Any]] = field(default_factory=list)
    selected_strategy: None = None  # always None in V1
    formal_walk_forward_executed: bool = False
    oos_executed: bool = False
    demo_eligibility: bool = False

    def __post_init__(self) -> None:
        if not self.stages:
            self.stages = {s: STAGE_STATUS_BLOCKED for s in QUALIFICATION_STAGES}

    def mark_infrastructure_ready(self) -> None:
        self.state = "INFRASTRUCTURE_READY"
        # Stages remain BLOCKED; READY is recorded only on the SM itself.
        self._record("mark_infrastructure_ready", {"state": self.state})

    def register_synthetic_candidate(self, candidate_id: str) -> None:
        if self.state not in {"INFRASTRUCTURE_READY", "CANDIDATE_REGISTERED_SYNTHETIC", "PROMOTION_BLOCKED"}:
            self.state = "PROMOTION_BLOCKED"
            self._record("register_synthetic_candidate_rejected", {"candidate_id": candidate_id})
            return
        self.state = "CANDIDATE_REGISTERED_SYNTHETIC"
        self.selected_strategy = None  # never select a real strategy
        self._record(
            "register_synthetic_candidate",
            {"candidate_id": candidate_id, "selected_strategy": None, "fixture_only": True},
        )

    def request_founder_authorization(self, request: dict[str, Any] | None) -> dict[str, Any]:
        self.state = "AWAITING_FOUNDER_AUTHORIZATION"
        gate = self.founder_gate.evaluate(request)
        if gate["authorized"]:
            # Unreachable in V1 dry-run, but keep path for future.
            self.state = "AUTHORIZED_BUT_STAGES_BLOCKED"
        else:
            self.state = "PROMOTION_BLOCKED"
        self._record("founder_authorization", gate)
        return gate

    def attempt_advance_stage(self, stage: str) -> dict[str, Any]:
        """Refuse all stage advances in V1 — infrastructure only."""
        if stage not in QUALIFICATION_STAGES:
            result = {"allowed": False, "reason": "UNKNOWN_STAGE", "stage": stage}
            self._record("advance_stage_rejected", result)
            return result
        result = {
            "allowed": False,
            "reason": "STAGE_DEFAULT_BLOCKED_V1_INFRASTRUCTURE_ONLY",
            "stage": stage,
            "current_status": self.stages.get(stage, STAGE_STATUS_BLOCKED),
            "formal_walk_forward_executed": False,
            "oos_executed": False,
        }
        self.stages[stage] = STAGE_STATUS_BLOCKED
        self.state = "PROMOTION_BLOCKED"
        self._record("advance_stage_blocked", result)
        return result

    def attempt_promote(self) -> dict[str, Any]:
        """Never promotes in V1."""
        all_passed = all(self.stages.get(s) == STAGE_STATUS_PASSED for s in QUALIFICATION_STAGES)
        result = {
            "allowed": False,
            "reason": "PROMOTION_BLOCKED_V1",
            "all_stages_passed": all_passed,
            "founder_authorized": self.founder_gate.authorized,
            "selected_strategy": None,
            "formal_walk_forward_executed": False,
            "oos_executed": False,
            "demo_eligibility": False,
        }
        self.state = "PROMOTION_BLOCKED"
        self.demo_eligibility = False
        self._record("attempt_promote_blocked", result)
        return result

    def _record(self, event: str, detail: dict[str, Any]) -> None:
        self.history.append({"event": event, "detail": deepcopy(detail)})

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "stages": dict(self.stages),
            "stage_order": list(QUALIFICATION_STAGES),
            "founder_gate": self.founder_gate.to_dict(),
            "selected_strategy": self.selected_strategy,
            "formal_walk_forward_executed": self.formal_walk_forward_executed,
            "oos_executed": self.oos_executed,
            "demo_eligibility": self.demo_eligibility,
            "history_count": len(self.history),
            "history": list(self.history),
        }
