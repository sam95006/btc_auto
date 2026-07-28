"""Champion/challenger policy experiments — shadow promotion gate only."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_adaptive_policy.metrics import LearningMetricsSnapshot, TargetStatus


class PolicyRoleStatus(str, Enum):
    SHADOW_CHALLENGER = "SHADOW_CHALLENGER"
    SHADOW_CHAMPION_CANDIDATE = "SHADOW_CHAMPION_CANDIDATE"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


FORBIDDEN_PROMOTION_STATUSES = frozenset({"LIVE_APPLIED", "AUTO_PROMOTED"})


@dataclass
class PolicyChampion:
    policy_id: str
    snapshot_id: str
    status: PolicyRoleStatus = PolicyRoleStatus.SHADOW_CHAMPION_CANDIDATE
    metrics: LearningMetricsSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status.value,
            "metrics": self.metrics.to_dict() if self.metrics else None,
        }


@dataclass
class PolicyChallenger:
    policy_id: str
    snapshot_id: str
    status: PolicyRoleStatus = PolicyRoleStatus.SHADOW_CHALLENGER
    experiment_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status.value,
            "experiment_id": self.experiment_id,
        }


@dataclass
class Experiment:
    experiment_id: str
    champion_id: str
    challenger_id: str
    sample_size: int = 0
    status: str = "RUNNING"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "champion_id": self.champion_id,
            "challenger_id": self.challenger_id,
            "sample_size": self.sample_size,
            "status": self.status,
            "metadata": dict(self.metadata),
        }


@dataclass
class PromotionVerdict:
    promoted: bool
    reason: str
    candidate_status: PolicyRoleStatus = PolicyRoleStatus.SHADOW_CHALLENGER

    def to_dict(self) -> dict[str, Any]:
        return {
            "promoted": self.promoted,
            "reason": self.reason,
            "candidate_status": self.candidate_status.value,
        }


class PromotionGate:
    """Evaluate challenger promotion — never LIVE_APPLIED / AUTO_PROMOTED."""

    MIN_SAMPLE = 30

    def evaluate(
        self,
        champion_metrics: LearningMetricsSnapshot,
        challenger_metrics: LearningMetricsSnapshot,
        *,
        immutable_change_attempted: bool = False,
    ) -> PromotionVerdict:
        if immutable_change_attempted:
            return PromotionVerdict(False, "immutable_change_blocked")
        if challenger_metrics.sample_size < self.MIN_SAMPLE:
            return PromotionVerdict(False, "insufficient_sample")
        if challenger_metrics.expectancy <= champion_metrics.expectancy:
            return PromotionVerdict(False, "expectancy_not_improved")
        if challenger_metrics.profit_factor < champion_metrics.profit_factor:
            return PromotionVerdict(False, "profit_factor_worse")
        if challenger_metrics.max_drawdown_pct > champion_metrics.max_drawdown_pct:
            return PromotionVerdict(False, "drawdown_worse")
        if challenger_metrics.mistake_recurrence_rate >= champion_metrics.mistake_recurrence_rate:
            return PromotionVerdict(False, "mistake_recurrence_not_reduced")
        if challenger_metrics.target_status != TargetStatus.TARGET_REACHED_SHADOW_ONLY:
            return PromotionVerdict(False, "target_not_reached_shadow_only")
        return PromotionVerdict(
            True,
            "shadow_champion_candidate",
            candidate_status=PolicyRoleStatus.SHADOW_CHAMPION_CANDIDATE,
        )

    @staticmethod
    def max_status(status: PolicyRoleStatus) -> PolicyRoleStatus:
        """Highest allowed status is SHADOW_CHAMPION_CANDIDATE."""
        if status.value in FORBIDDEN_PROMOTION_STATUSES:
            return PolicyRoleStatus.REJECTED
        if status == PolicyRoleStatus.SHADOW_CHAMPION_CANDIDATE:
            return status
        return status
