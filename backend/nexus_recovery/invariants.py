"""Recovery invariants — enforced after every crash / injected failure.

Every one of the counts below MUST be zero after recovery. Anything else
routes the session to BLOCKED / FAILED_SAFE.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REQUIRED_ZERO_INVARIANTS: tuple[str, ...] = (
    "open_ambiguous_position_count",
    "orphan_lifecycle_count",
    "duplicate_position_count",
    "unclosed_intent_count",
    "untracked_fill_count",
    "risk_limit_bypass_count",
    "exchange_write_attempt_count",
)


@dataclass
class RecoveryInvariantResult:
    passed: bool
    counts: dict[str, int]
    violations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_invariants_status": "PASS" if self.passed else "FAIL",
            "counts": dict(self.counts),
            "violations": list(self.violations),
        }


def check_recovery_invariants(counts: dict[str, Any]) -> RecoveryInvariantResult:
    resolved: dict[str, int] = {}
    violations: list[str] = []
    for key in REQUIRED_ZERO_INVARIANTS:
        raw = counts.get(key)
        try:
            value = int(raw or 0)
        except (TypeError, ValueError):
            value = 0
            violations.append(f"{key}:non_integer")
        resolved[key] = value
        if value != 0:
            violations.append(f"{key}={value}")
    return RecoveryInvariantResult(
        passed=len(violations) == 0,
        counts=resolved,
        violations=violations,
    )
