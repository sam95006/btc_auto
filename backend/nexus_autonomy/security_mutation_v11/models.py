"""Typed results for mutation campaign and adversarial proofs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class KillCaseResult:
    case_id: str
    subject_id: str
    passed_on_real: bool
    killed_mutant: bool
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "subject_id": self.subject_id,
            "passed_on_real": self.passed_on_real,
            "killed_mutant": self.killed_mutant,
            "detail": self.detail,
            "evidence": dict(self.evidence),
        }


@dataclass
class MutationOutcome:
    mutation_id: str
    subject_id: str
    operator: str
    killed: bool
    equivalent: bool = False
    survivor: bool = False
    unresolved_blocker: bool = False
    blocker_reason: str = ""
    kill_cases: list[str] = field(default_factory=list)
    detail: str = ""
    severity: str = "info"  # info | high | critical
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "subject_id": self.subject_id,
            "operator": self.operator,
            "killed": self.killed,
            "equivalent": self.equivalent,
            "survivor": self.survivor,
            "unresolved_blocker": self.unresolved_blocker,
            "blocker_reason": self.blocker_reason,
            "kill_cases": list(self.kill_cases),
            "detail": self.detail,
            "severity": self.severity,
            "evidence": dict(self.evidence),
        }


@dataclass
class AdversarialScenarioResult:
    scenario_id: str
    passed: bool
    fail_closed: bool
    detail: str = ""
    critical: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "fail_closed": self.fail_closed,
            "detail": self.detail,
            "critical": self.critical,
            "evidence": dict(self.evidence),
        }


@dataclass
class Finding:
    severity: str
    code: str
    detail: str
    fail_closed: bool = True
    mutation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "severity": self.severity,
            "code": self.code,
            "detail": self.detail,
            "fail_closed": self.fail_closed,
        }
        if self.mutation_id:
            out["mutation_id"] = self.mutation_id
        return out
