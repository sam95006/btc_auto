"""Phase 5 Gate C — Patch Governance State Machine.

RESEARCH ONLY. Manages the lifecycle of simulation-derived patch proposals.
Never applies patches to production code, config files, or trading logic.

State machine:
  PROPOSED
    → UNDER_REVIEW    (operator marks for review)
    → REJECTED        (review rejected)
    → NEEDS_REPLAY    (review requests replay evidence)
    → REPLAY_DONE     (replay completed with evidence)
    → APPROVED_SIM    (approved for simulation-only apply)
    → APPLIED_TO_SIMULATION  (applied in simulation context only)
    → ROLLED_BACK     (rolled back after apply)

Governance requirements for APPROVED_SIM:
  - problem field present
  - evidence field present
  - sampleSize >= required minSampleSize
  - scope = "simulation_only"
  - requiresReplay satisfied if true
  - requiresWalkForward satisfied if true
  - rollbackDescription present
  - autoApplyProduction must be False
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from backend.nexus_research.domain_events import PATCH_APPLIED, publish_event
from backend.nexus_research.storage import get_research_store

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── States ────────────────────────────────────────────────────────────────────
STATE_PROPOSED = "PROPOSED"
STATE_UNDER_REVIEW = "UNDER_REVIEW"
STATE_REJECTED = "REJECTED"
STATE_NEEDS_REPLAY = "NEEDS_REPLAY"
STATE_REPLAY_DONE = "REPLAY_DONE"
STATE_APPROVED_SIM = "APPROVED_SIM"
STATE_APPLIED_TO_SIMULATION = "APPLIED_TO_SIMULATION"
STATE_ROLLED_BACK = "ROLLED_BACK"

_VALID_TRANSITIONS: dict[str, set[str]] = {
    STATE_PROPOSED: {STATE_UNDER_REVIEW, STATE_REJECTED, STATE_NEEDS_REPLAY},
    STATE_UNDER_REVIEW: {STATE_REJECTED, STATE_NEEDS_REPLAY, STATE_APPROVED_SIM},
    STATE_NEEDS_REPLAY: {STATE_REPLAY_DONE, STATE_REJECTED},
    STATE_REPLAY_DONE: {STATE_APPROVED_SIM, STATE_REJECTED, STATE_UNDER_REVIEW},
    STATE_APPROVED_SIM: {STATE_APPLIED_TO_SIMULATION, STATE_REJECTED},
    STATE_APPLIED_TO_SIMULATION: {STATE_ROLLED_BACK},
    STATE_REJECTED: set(),
    STATE_ROLLED_BACK: set(),
}

_TERMINAL_STATES = {STATE_REJECTED, STATE_ROLLED_BACK}

_REQUIRED_APPROVAL_FIELDS = [
    "problem", "evidence", "scope", "rollbackDescription",
]


class PatchGovernanceError(Exception):
    pass


class PatchProposal:
    """A governed patch proposal record."""

    def __init__(
        self,
        proposal_id: str,
        symbol: str,
        scope: str,
        problem: str,
        evidence: dict[str, Any],
        suggested_change: dict[str, Any],
        sample_size: int,
        requires_min_sample: int,
        requires_replay: bool,
        requires_walk_forward: bool,
        requires_rollback_plan: bool,
        rollback_description: str,
        source_reflection_id: str | None = None,
    ) -> None:
        self.proposal_id = proposal_id
        self.symbol = symbol
        self.scope = scope
        self.problem = problem
        self.evidence = evidence
        self.suggested_change = suggested_change
        self.sample_size = sample_size
        self.requires_min_sample = requires_min_sample
        self.requires_replay = requires_replay
        self.requires_walk_forward = requires_walk_forward
        self.requires_rollback_plan = requires_rollback_plan
        self.rollback_description = rollback_description
        self.source_reflection_id = source_reflection_id

        self.state = STATE_PROPOSED
        self.auto_apply_production = False  # ALWAYS False; enforced here
        self.state_history: list[dict[str, Any]] = [
            {"state": STATE_PROPOSED, "ts": int(time.time() * 1000), "actor": "system"}
        ]
        self.review_notes: list[str] = []
        self.replay_evidence: dict[str, Any] | None = None
        self.walk_forward_evidence: dict[str, Any] | None = None
        self.created_at_ms = int(time.time() * 1000)
        self.updated_at_ms = self.created_at_ms

    def transition(
        self,
        new_state: str,
        actor: str = "system",
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if new_state not in _VALID_TRANSITIONS.get(self.state, set()):
            raise PatchGovernanceError(
                f"invalid transition {self.state!r} → {new_state!r} for proposal {self.proposal_id}"
            )

        # Validate pre-conditions for APPROVED_SIM
        if new_state == STATE_APPROVED_SIM:
            self._validate_approval_preconditions()

        # Validate pre-conditions for APPLIED_TO_SIMULATION
        if new_state == STATE_APPLIED_TO_SIMULATION:
            if self.auto_apply_production:
                raise PatchGovernanceError(
                    "autoApplyProduction is True — blocked by governance"
                )
            if self.scope != "simulation_only":
                raise PatchGovernanceError(
                    f"scope must be 'simulation_only', got {self.scope!r}"
                )

        entry: dict[str, Any] = {
            "state": new_state,
            "ts": int(time.time() * 1000),
            "actor": actor,
            "note": note,
        }
        if metadata:
            entry["metadata"] = metadata
        self.state_history.append(entry)
        self.state = new_state
        self.updated_at_ms = int(time.time() * 1000)
        if note:
            self.review_notes.append(f"[{actor}] {note}")
        logger.info(
            "[patch_gov] %s → %s (actor=%s)", self.proposal_id, new_state, actor
        )

    def _validate_approval_preconditions(self) -> None:
        errors: list[str] = []
        if not self.problem:
            errors.append("missing problem description")
        if not self.evidence:
            errors.append("missing evidence")
        if self.scope != "simulation_only":
            errors.append(f"scope must be simulation_only, got {self.scope!r}")
        if not self.rollback_description:
            errors.append("missing rollbackDescription")
        if self.sample_size < self.requires_min_sample:
            errors.append(
                f"sample_size {self.sample_size} < required {self.requires_min_sample}"
            )
        if self.requires_replay and self.replay_evidence is None:
            errors.append("requires_replay=True but no replay_evidence attached")
        if self.requires_walk_forward and self.walk_forward_evidence is None:
            errors.append("requires_walk_forward=True but no walk_forward_evidence attached")
        if self.auto_apply_production:
            errors.append("autoApplyProduction must be False")
        if errors:
            raise PatchGovernanceError(
                f"approval preconditions not met: {'; '.join(errors)}"
            )

    def attach_replay_evidence(self, evidence: dict[str, Any]) -> None:
        self.replay_evidence = evidence
        self.updated_at_ms = int(time.time() * 1000)

    def attach_walk_forward_evidence(self, evidence: dict[str, Any]) -> None:
        self.walk_forward_evidence = evidence
        self.updated_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposalId": self.proposal_id,
            "symbol": self.symbol,
            "scope": self.scope,
            "state": self.state,
            "problem": self.problem,
            "evidence": self.evidence,
            "suggestedChange": self.suggested_change,
            "sampleSize": self.sample_size,
            "requiresMinSample": self.requires_min_sample,
            "requiresReplay": self.requires_replay,
            "requiresWalkForward": self.requires_walk_forward,
            "requiresRollbackPlan": self.requires_rollback_plan,
            "rollbackDescription": self.rollback_description,
            "autoApplyProduction": self.auto_apply_production,
            "stateHistory": self.state_history,
            "reviewNotes": self.review_notes,
            "replayEvidence": self.replay_evidence,
            "walkForwardEvidence": self.walk_forward_evidence,
            "sourceReflectionId": self.source_reflection_id,
            "createdAtMs": self.created_at_ms,
            "updatedAtMs": self.updated_at_ms,
            "researchOnly": True,
        }


class PatchGovernanceManager:
    """Manages all patch proposals with governance enforcement."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proposals: dict[str, PatchProposal] = {}
        self._total_created = 0
        self._total_approved = 0
        self._total_rejected = 0

    def ingest_from_reflection(self, proposal_dict: dict[str, Any]) -> PatchProposal:
        """Create a PatchProposal from a reflection-generated proposal dict."""
        proposal_id = proposal_dict.get("proposalId") or str(uuid.uuid4())

        # Check for existing
        with self._lock:
            if proposal_id in self._proposals:
                return self._proposals[proposal_id]

        change = proposal_dict.get("suggestedChange") or {}
        prop = PatchProposal(
            proposal_id=proposal_id,
            symbol=proposal_dict.get("evidence", {}).get("symbol", "UNKNOWN"),
            scope=proposal_dict.get("scope", "simulation_only"),
            problem=proposal_dict.get("problem", ""),
            evidence=proposal_dict.get("evidence") or {},
            suggested_change=change,
            sample_size=int(proposal_dict.get("sampleSize", 0)),
            requires_min_sample=int(proposal_dict.get("requiresMinSample", 5)),
            requires_replay=bool(proposal_dict.get("requiresReplay", False)),
            requires_walk_forward=bool(proposal_dict.get("requiresWalkForward", False)),
            requires_rollback_plan=bool(proposal_dict.get("requiresRollbackPlan", False)),
            rollback_description=proposal_dict.get("rollbackDescription", ""),
            source_reflection_id=proposal_dict.get("sourceReflectionId"),
        )

        with self._lock:
            self._proposals[proposal_id] = prop
            self._total_created += 1

        # Persist
        store = get_research_store()
        store.append("patch_proposals", prop.to_dict())
        return prop

    def transition(
        self,
        proposal_id: str,
        new_state: str,
        actor: str = "system",
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PatchProposal:
        with self._lock:
            prop = self._proposals.get(proposal_id)
            if prop is None:
                raise PatchGovernanceError(f"proposal not found: {proposal_id}")
            prop.transition(new_state, actor=actor, note=note, metadata=metadata)
            if new_state == STATE_APPROVED_SIM:
                self._total_approved += 1
            elif new_state == STATE_REJECTED:
                self._total_rejected += 1

        store = get_research_store()
        store.append("patch_proposals", prop.to_dict())

        if new_state == STATE_APPLIED_TO_SIMULATION:
            publish_event(
                PATCH_APPLIED,
                {"proposalId": proposal_id, "scope": "simulation_only",
                 "autoApplyProduction": False, "researchOnly": True},
                idempotency_key=f"patch_applied_{proposal_id}",
            )
        return prop

    def get(self, proposal_id: str) -> PatchProposal | None:
        with self._lock:
            return self._proposals.get(proposal_id)

    def list_proposals(
        self,
        state: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._lock:
            proposals = list(self._proposals.values())
        if state:
            proposals = [p for p in proposals if p.state == state]
        if symbol:
            proposals = [p for p in proposals if p.symbol == symbol]
        proposals.sort(key=lambda p: p.created_at_ms, reverse=True)
        return [p.to_dict() for p in proposals[:limit]]

    def status(self) -> dict[str, Any]:
        with self._lock:
            state_counts: dict[str, int] = {}
            for p in self._proposals.values():
                state_counts[p.state] = state_counts.get(p.state, 0) + 1
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "autoApplyProduction": False,
            "totalCreated": self._total_created,
            "totalApproved": self._total_approved,
            "totalRejected": self._total_rejected,
            "activePropals": len(self._proposals),
            "stateCounts": state_counts,
            "generatedAt": int(time.time() * 1000),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_MGR: PatchGovernanceManager | None = None
_MGR_LOCK = threading.Lock()


def get_patch_governance() -> PatchGovernanceManager:
    global _MGR
    with _MGR_LOCK:
        if _MGR is None:
            _MGR = PatchGovernanceManager()
            logger.info("[patch_gov] PatchGovernanceManager initialised (researchOnly=true)")
        return _MGR
