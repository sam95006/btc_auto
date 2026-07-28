"""Multi-cause failure taxonomy for Wave 3 adaptive learning."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureType(str, Enum):
    ENTRY_TOO_EARLY = "ENTRY_TOO_EARLY"
    ENTRY_TOO_LATE = "ENTRY_TOO_LATE"
    CHASE_ENTRY = "CHASE_ENTRY"
    POOR_RISK_REWARD = "POOR_RISK_REWARD"
    STOP_TOO_TIGHT = "STOP_TOO_TIGHT"
    STOP_TOO_WIDE = "STOP_TOO_WIDE"
    EARLY_EXIT = "EARLY_EXIT"
    LATE_EXIT = "LATE_EXIT"
    REGIME_MISMATCH = "REGIME_MISMATCH"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
    DATA_QUALITY = "DATA_QUALITY"
    EXECUTION_SLIPPAGE = "EXECUTION_SLIPPAGE"
    OVERCONFIDENCE = "OVERCONFIDENCE"
    UNDERCONFIDENCE = "UNDERCONFIDENCE"
    REPEATED_KNOWN_MISTAKE = "REPEATED_KNOWN_MISTAKE"
    PORTFOLIO_CONCENTRATION = "PORTFOLIO_CONCENTRATION"
    STRATEGY_DRIFT = "STRATEGY_DRIFT"
    UNKNOWN = "UNKNOWN"


class FailureSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Preventability(str, Enum):
    PREVENTABLE = "PREVENTABLE"
    PARTIALLY_PREVENTABLE = "PARTIALLY_PREVENTABLE"
    NOT_PREVENTABLE = "NOT_PREVENTABLE"


ALL_FAILURE_TYPES = tuple(FailureType)


@dataclass
class FailureClassification:
    failure_type: FailureType
    severity: FailureSeverity
    confidence: float
    supporting_evidence: list[str] = field(default_factory=list)
    root_cause: str = ""
    contributing_causes: list[str] = field(default_factory=list)
    preventability: Preventability = Preventability.PARTIALLY_PREVENTABLE
    preventive_rule_candidate: str = ""
    similar_case_ids: list[str] = field(default_factory=list)
    case_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "failure_type": self.failure_type.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "supporting_evidence": list(self.supporting_evidence),
            "root_cause": self.root_cause,
            "contributing_causes": list(self.contributing_causes),
            "preventability": self.preventability.value,
            "preventive_rule_candidate": self.preventive_rule_candidate,
            "similar_case_ids": list(self.similar_case_ids),
        }


def classify_failure(
    *,
    case_id: str,
    failure_type: FailureType,
    evidence: list[str] | None = None,
    root_cause: str = "",
    confidence: float = 0.7,
) -> FailureClassification:
    severity = FailureSeverity.MEDIUM
    if failure_type in {FailureType.REPEATED_KNOWN_MISTAKE, FailureType.PORTFOLIO_CONCENTRATION}:
        severity = FailureSeverity.HIGH
    if failure_type == FailureType.DATA_QUALITY:
        severity = FailureSeverity.LOW
    preventability = Preventability.PARTIALLY_PREVENTABLE
    if failure_type == FailureType.REPEATED_KNOWN_MISTAKE:
        preventability = Preventability.PREVENTABLE
    rule = _default_preventive_rule(failure_type)
    return FailureClassification(
        case_id=case_id,
        failure_type=failure_type,
        severity=severity,
        confidence=confidence,
        supporting_evidence=list(evidence or []),
        root_cause=root_cause or failure_type.value.lower(),
        contributing_causes=[],
        preventability=preventability,
        preventive_rule_candidate=rule,
    )


def _default_preventive_rule(failure_type: FailureType) -> str:
    mapping = {
        FailureType.ENTRY_TOO_EARLY: "require_confirmation_candle_close",
        FailureType.CHASE_ENTRY: "block_chase_if_move_exceeds_threshold",
        FailureType.REPEATED_KNOWN_MISTAKE: "escalate_recurring_mistake_guard",
        FailureType.REGIME_MISMATCH: "route_strategy_by_regime",
        FailureType.STOP_TOO_TIGHT: "widen_stop_within_invariant_bounds",
        FailureType.EARLY_EXIT: "apply_time_stop_instead_of_discretionary_exit",
    }
    return mapping.get(failure_type, f"review_{failure_type.value.lower()}")
