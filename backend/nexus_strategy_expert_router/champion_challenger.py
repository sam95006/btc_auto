"""Champion / Challenger shadow roles for Strategy Expert Router policies."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_strategy_expert_router.constants import (
    CHALLENGER_ROLE,
    CHAMPION_ROLE,
    FORBIDDEN_PROMOTION,
)


@dataclass
class RouterPolicySnapshot:
    policy_id: str
    role: str
    expert_weights: dict[str, float] = field(default_factory=dict)
    sample_size: int = 0
    no_trade_win_rate: float = 0.0
    entry_regret: float = 0.0
    status: str = "SHADOW_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "role": self.role,
            "expert_weights": dict(self.expert_weights),
            "sample_size": self.sample_size,
            "no_trade_win_rate": self.no_trade_win_rate,
            "entry_regret": self.entry_regret,
            "status": self.status,
        }


@dataclass
class PromotionVerdict:
    promoted: bool
    reason: str
    candidate_role: str = CHALLENGER_ROLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "promoted": self.promoted,
            "reason": self.reason,
            "candidate_role": self.candidate_role,
            "live_applied": False,
            "auto_promoted": False,
        }


class RouterPromotionGate:
    """Shadow-only promotion. LIVE / AUTO_PROMOTED are hard-forbidden."""

    MIN_SAMPLE = 20

    def evaluate(
        self,
        champion: RouterPolicySnapshot,
        challenger: RouterPolicySnapshot,
        *,
        requested_status: str | None = None,
    ) -> PromotionVerdict:
        if requested_status and requested_status in FORBIDDEN_PROMOTION:
            return PromotionVerdict(False, "live_promotion_forbidden")
        if challenger.status in FORBIDDEN_PROMOTION:
            return PromotionVerdict(False, "challenger_forbidden_status")
        if challenger.sample_size < self.MIN_SAMPLE:
            return PromotionVerdict(False, "insufficient_sample")
        # Prefer higher no-trade discipline and lower entry regret in shadow.
        if challenger.no_trade_win_rate < champion.no_trade_win_rate:
            return PromotionVerdict(False, "no_trade_discipline_worse")
        if challenger.entry_regret > champion.entry_regret:
            return PromotionVerdict(False, "entry_regret_worse")
        return PromotionVerdict(
            True,
            "shadow_champion_candidate",
            candidate_role=CHAMPION_ROLE,
        )

    @staticmethod
    def max_status(status: str) -> str:
        if status in FORBIDDEN_PROMOTION:
            return CHALLENGER_ROLE
        return status


def default_champion() -> RouterPolicySnapshot:
    return RouterPolicySnapshot(
        policy_id="router_champion_v16d_baseline",
        role=CHAMPION_ROLE,
        sample_size=50,
        no_trade_win_rate=0.55,
        entry_regret=0.40,
        status="SHADOW_ONLY",
    )


def default_challenger() -> RouterPolicySnapshot:
    return RouterPolicySnapshot(
        policy_id="router_challenger_v16d_defensive_bias",
        role=CHALLENGER_ROLE,
        sample_size=10,
        no_trade_win_rate=0.60,
        entry_regret=0.35,
        status="SHADOW_ONLY",
    )
