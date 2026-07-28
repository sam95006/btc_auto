"""Bounded learning patches with immutable guard."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_adaptive_policy.constitution import LeverageConstitution


class PatchStatus(str, Enum):
    PROPOSED = "PROPOSED"
    SHADOW_APPLIED = "SHADOW_APPLIED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


FORBIDDEN_PATCH_FIELDS = frozenset(
    {"leverage", "cross_margin", "martingale", "averaging_down", "auto_add_margin", "isolated_only"}
)


@dataclass
class LearningPatch:
    patch_id: str
    proposal_id: str
    action: str
    parameter: str
    value: Any
    status: PatchStatus = PatchStatus.PROPOSED
    bounds: dict[str, Any] = field(default_factory=dict)
    rejection_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "proposal_id": self.proposal_id,
            "action": self.action,
            "parameter": self.parameter,
            "value": self.value,
            "status": self.status.value,
            "bounds": dict(self.bounds),
            "rejection_reason": self.rejection_reason,
        }


class ImmutablePatchGuard:
    """Reject patches that attempt immutable mutations."""

    def __init__(self) -> None:
        self.constitution = LeverageConstitution()

    def validate(self, patch: LearningPatch) -> tuple[bool, str]:
        payload = {patch.parameter: patch.value, "action": patch.action}
        if patch.parameter in FORBIDDEN_PATCH_FIELDS or patch.action.startswith("set_leverage"):
            return False, "IMMUTABLE_SAFETY_POLICY"
        verdict = self.constitution.validate_patch(payload)
        if not verdict.ok:
            return False, verdict.violation.value if verdict.violation else "REJECTED"
        if patch.bounds:
            lo = patch.bounds.get("min")
            hi = patch.bounds.get("max")
            if lo is not None and patch.value < lo:
                return False, "OUT_OF_BOUNDS"
            if hi is not None and patch.value > hi:
                return False, "OUT_OF_BOUNDS"
        return True, ""


class LearningPatchApplier:
    """Apply bounded patches in shadow only."""

    _seq = 0

    def __init__(self) -> None:
        self.guard = ImmutablePatchGuard()
        self.applied: list[LearningPatch] = []

    def submit(self, patch: LearningPatch) -> LearningPatch:
        ok, reason = self.guard.validate(patch)
        if not ok:
            patch.status = PatchStatus.REJECTED
            patch.rejection_reason = reason
            return patch
        patch.status = PatchStatus.SHADOW_APPLIED
        self.applied.append(patch)
        return patch

    def create_from_proposal(
        self,
        proposal_id: str,
        action: str,
        parameter: str,
        value: Any,
        *,
        bounds: dict[str, Any] | None = None,
    ) -> LearningPatch:
        LearningPatchApplier._seq += 1
        return LearningPatch(
            patch_id=f"patch_{LearningPatchApplier._seq:06d}",
            proposal_id=proposal_id,
            action=action,
            parameter=parameter,
            value=value,
            bounds=dict(bounds or {}),
        )
