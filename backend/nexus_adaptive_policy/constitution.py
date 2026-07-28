"""Immutable leverage and safety constitution for Wave 3 adaptive policy."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_adaptive_policy import FIXED_LEVERAGE


class ConstitutionViolation(str, Enum):
    IMMUTABLE_LEVERAGE_VIOLATION = "IMMUTABLE_LEVERAGE_VIOLATION"
    IMMUTABLE_SAFETY_POLICY = "IMMUTABLE_SAFETY_POLICY"


FORBIDDEN_LEVERAGES = frozenset({3, 10, 50, 100})


@dataclass(frozen=True)
class ImmutableSafetyPolicy:
    """Safety invariants that AI learning may never mutate."""

    isolated_only: bool = True
    cross_margin: bool = False
    martingale: bool = False
    averaging_down: bool = False
    auto_add_margin: bool = False
    fixed_leverage: int = FIXED_LEVERAGE

    IMMUTABLE_FIELDS = frozenset(
        {
            "isolated_only",
            "cross_margin",
            "martingale",
            "averaging_down",
            "auto_add_margin",
            "fixed_leverage",
        }
    )


@dataclass
class ConstitutionVerdict:
    ok: bool
    violation: ConstitutionViolation | None = None
    detail: str = ""


class LeverageConstitution:
    """Enforces fixed 25x leverage and immutable safety policy."""

    def __init__(self, policy: ImmutableSafetyPolicy | None = None) -> None:
        self.policy = policy or ImmutableSafetyPolicy()

    def validate_leverage(self, leverage: int | float) -> ConstitutionVerdict:
        lev = int(leverage)
        if lev != FIXED_LEVERAGE:
            return ConstitutionVerdict(
                ok=False,
                violation=ConstitutionViolation.IMMUTABLE_LEVERAGE_VIOLATION,
                detail=f"leverage {lev} != fixed {FIXED_LEVERAGE}",
            )
        if lev in FORBIDDEN_LEVERAGES:
            return ConstitutionVerdict(
                ok=False,
                violation=ConstitutionViolation.IMMUTABLE_LEVERAGE_VIOLATION,
                detail=f"forbidden leverage tier {lev}",
            )
        return ConstitutionVerdict(ok=True)

    def validate_patch(self, patch: dict[str, Any]) -> ConstitutionVerdict:
        if "leverage" in patch and int(patch["leverage"]) != FIXED_LEVERAGE:
            return ConstitutionVerdict(
                ok=False,
                violation=ConstitutionViolation.IMMUTABLE_LEVERAGE_VIOLATION,
                detail="patch attempted leverage change",
            )
        for key in ImmutableSafetyPolicy.IMMUTABLE_FIELDS:
            if key in patch and patch[key] != getattr(self.policy, key):
                return ConstitutionVerdict(
                    ok=False,
                    violation=ConstitutionViolation.IMMUTABLE_SAFETY_POLICY,
                    detail=f"patch attempted immutable field change: {key}",
                )
        return ConstitutionVerdict(ok=True)

    def validate_safety_posture(self) -> ConstitutionVerdict:
        p = self.policy
        if not p.isolated_only:
            return ConstitutionVerdict(
                ok=False,
                violation=ConstitutionViolation.IMMUTABLE_SAFETY_POLICY,
                detail="isolated_only must remain true",
            )
        if p.cross_margin or p.martingale or p.averaging_down or p.auto_add_margin:
            return ConstitutionVerdict(
                ok=False,
                violation=ConstitutionViolation.IMMUTABLE_SAFETY_POLICY,
                detail="forbidden safety posture",
            )
        if p.fixed_leverage != FIXED_LEVERAGE:
            return ConstitutionVerdict(
                ok=False,
                violation=ConstitutionViolation.IMMUTABLE_LEVERAGE_VIOLATION,
                detail="fixed_leverage drift",
            )
        return ConstitutionVerdict(ok=True)

    def to_dict(self) -> dict[str, Any]:
        p = self.policy
        return {
            "fixed_leverage": FIXED_LEVERAGE,
            "ai_can_change_leverage": False,
            "isolated_only": p.isolated_only,
            "cross_margin": p.cross_margin,
            "martingale": p.martingale,
            "averaging_down": p.averaging_down,
            "auto_add_margin": p.auto_add_margin,
            "forbidden_leverages": sorted(FORBIDDEN_LEVERAGES),
        }
