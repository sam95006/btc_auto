"""Mistake similarity engine and pre-trade guard actions."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.nexus_adaptive_policy.failure_taxonomy import FailureType
from backend.nexus_adaptive_policy.mistake_memory import FailureSignature, MistakeMemoryStore


class GuardAction(str, Enum):
    ALLOW = "ALLOW"
    RAISE_THRESHOLD = "RAISE_THRESHOLD"
    REDUCE_MARGIN = "REDUCE_MARGIN"
    REQUIRE_EXTRA_CONFIRMATION = "REQUIRE_EXTRA_CONFIRMATION"
    CHANGE_STRATEGY = "CHANGE_STRATEGY"
    COOLDOWN = "COOLDOWN"
    SHADOW_ONLY = "SHADOW_ONLY"
    BLOCK = "BLOCK"


ALL_GUARD_ACTIONS = tuple(GuardAction)


@dataclass
class GuardDecision:
    action: GuardAction
    reason: str
    leverage: int
    margin_multiplier: float = 1.0
    similar_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "leverage": self.leverage,
            "margin_multiplier": self.margin_multiplier,
            "similar_count": self.similar_count,
        }


class MistakeSimilarityEngine:
    """Score similarity between a candidate trade context and past mistakes."""

    def __init__(self, store: MistakeMemoryStore) -> None:
        self.store = store

    def score(self, signature: FailureSignature) -> float:
        similar = self.store.index.find_similar(signature)
        if not similar:
            return 0.0
        return min(1.0, sum(r.occurrence_count for r in similar) * 0.15)


class RecurringErrorEscalationPolicy:
    """Escalate guard action as the same mistake repeats; never changes leverage."""

    THRESHOLDS = (
        (1, GuardAction.ALLOW),
        (2, GuardAction.RAISE_THRESHOLD),
        (3, GuardAction.REDUCE_MARGIN),
        (4, GuardAction.REQUIRE_EXTRA_CONFIRMATION),
        (5, GuardAction.COOLDOWN),
        (6, GuardAction.SHADOW_ONLY),
        (7, GuardAction.BLOCK),
    )

    def action_for_count(self, count: int) -> GuardAction:
        chosen = GuardAction.ALLOW
        for threshold, action in self.THRESHOLDS:
            if count >= threshold:
                chosen = action
        return chosen

    def margin_multiplier_for(self, action: GuardAction) -> float:
        if action == GuardAction.REDUCE_MARGIN:
            return 0.5
        if action in {GuardAction.COOLDOWN, GuardAction.SHADOW_ONLY, GuardAction.BLOCK}:
            return 0.0
        return 1.0


class PreTradeMistakeGuard:
    """Apply recurring mistake guard before shadow order intent creation."""

    def __init__(
        self,
        store: MistakeMemoryStore,
        *,
        fixed_leverage: int,
    ) -> None:
        self.store = store
        self.engine = MistakeSimilarityEngine(store)
        self.escalation = RecurringErrorEscalationPolicy()
        self.fixed_leverage = fixed_leverage

    def evaluate(
        self,
        *,
        symbol: str,
        strategy_id: str,
        failure_type: FailureType | None = None,
        regime: str = "UNKNOWN",
    ) -> GuardDecision:
        sig = FailureSignature(
            failure_type=(failure_type or FailureType.UNKNOWN).value,
            symbol=symbol,
            strategy_id=strategy_id,
            regime=regime,
        )
        similar = self.store.index.find_similar(sig)
        count = similar[0].occurrence_count if similar else 0
        action = self.escalation.action_for_count(count)
        if failure_type == FailureType.REPEATED_KNOWN_MISTAKE and count >= 2:
            action = GuardAction.BLOCK
        mult = self.escalation.margin_multiplier_for(action)
        return GuardDecision(
            action=action,
            reason=f"similar_mistakes={count}",
            leverage=self.fixed_leverage,
            margin_multiplier=mult,
            similar_count=count,
        )
