"""Structured learning loop — temporary controls only; no autonomous weight training."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

LESSON_SCHEMA_VERSION = "lesson_record_v1"
REFLECTION_SCHEMA_VERSION = "reflection_v1"

PROCESS_CLASSIFICATIONS = frozenset(
    {
        "GOOD_PROCESS_WIN",
        "GOOD_PROCESS_LOSS",
        "BAD_PROCESS_WIN",
        "BAD_PROCESS_LOSS",
        "UNDETERMINED_PROCESS",
    }
)

LESSON_STATUSES = frozenset(
    {
        "PROPOSED",
        "VALIDATED_AS_TEMPORARY_CONTROL",
        "REPLAY_VALIDATED",
        "WALK_FORWARD_VALIDATED",
        "OOS_VALIDATED",
        "RISK_REVIEWED",
        "REJECTED",
        "REVOKED",
        "INTEGRATION_PROOF_ONLY",
        "PROPOSED_INSUFFICIENT_SOURCE_EVIDENCE",
    }
)

IMMEDIATE_SAFE_ACTIONS = frozenset(
    {
        "confidence_penalty",
        "symbol_cooldown",
        "strategy_context_cooldown",
        "regime_context_cooldown",
        "require_additional_confirmation",
        "reduce_candidate_priority",
        "temporary_block",
        "escalate_to_manual_review",
    }
)

FORBIDDEN_IMMEDIATE = frozenset(
    {
        "entry_threshold_modification",
        "stop_modification",
        "target_modification",
        "leverage_modification",
        "position_size_increase",
        "new_feature_activation",
        "model_weight_change",
        "risk_limit_relaxation",
        "strategy_promotion",
        "policy_replacement",
    }
)

HARD_RISK_BLOCKS = frozenset(
    {
        "missing_required_data",
        "stale_data",
        "instrument_not_trading",
        "spread_above_limit",
        "slippage_above_limit",
        "cost_gate_failure",
        "invalid_stop",
        "invalid_quantity",
        "risk_above_limit",
        "liquidation_distance_failure",
        "duplicate_intent",
        "position_limit_failure",
        "account_reconciliation_failure",
        "provider_quality_failure",
    }
)


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass
class LessonRecord:
    lesson_id: str
    source_trade_id: str
    created_at: str
    process_classification: str
    root_causes: list[str]
    evidence_ids: list[str]
    symbol: str
    symbol_profile: dict[str, Any]
    strategy_id: str
    regime: str
    direction: str
    entry_context: dict[str, Any]
    cost_context: dict[str, Any]
    risk_context: dict[str, Any]
    applicable_conditions: list[str]
    contradicting_conditions: list[str]
    confidence: float
    reflection_provider: str
    reflection_model: str
    critic_provider: str
    critic_model: str
    immediate_safe_actions: list[str]
    proposed_policy_changes: list[str]
    referenced_prior_lessons: list[str]
    status: str
    schema_version: str = LESSON_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReasonerLessonApplication:
    retrieved_lesson_ids: list[str]
    applied_lesson_ids: list[str]
    ignored_lesson_ids: list[str]
    lesson_application_reason: str


@dataclass
class LessonMemory:
    lessons: list[LessonRecord] = field(default_factory=list)
    temporary_controls: list[dict[str, Any]] = field(default_factory=list)

    def add(self, lesson: LessonRecord) -> None:
        if lesson.process_classification not in PROCESS_CLASSIFICATIONS:
            raise ValueError("invalid_process_classification")
        if lesson.status not in LESSON_STATUSES:
            raise ValueError("invalid_lesson_status")
        for action in lesson.immediate_safe_actions:
            if action in FORBIDDEN_IMMEDIATE:
                raise ValueError(f"forbidden_immediate:{action}")
            if action not in IMMEDIATE_SAFE_ACTIONS:
                raise ValueError(f"unknown_immediate:{action}")
        self.lessons.append(lesson)
        if lesson.status == "VALIDATED_AS_TEMPORARY_CONTROL":
            for action in lesson.immediate_safe_actions:
                self.temporary_controls.append(
                    {
                        "lesson_id": lesson.lesson_id,
                        "action": action,
                        "permanent": False,
                        "symbol": lesson.symbol,
                    }
                )

    def retrieve(self, *, symbol: str | None = None, strategy_id: str | None = None, limit: int = 5) -> list[LessonRecord]:
        scored: list[LessonRecord] = []
        for lesson in reversed(self.lessons):
            if lesson.status == "REJECTED" or lesson.status == "REVOKED":
                continue
            if symbol and lesson.symbol != symbol:
                continue
            if strategy_id and lesson.strategy_id != strategy_id:
                continue
            scored.append(lesson)
            if len(scored) >= limit:
                break
        return scored

    def temporary_control_is_permanent(self, lesson_id: str) -> bool:
        return False  # hard invariant


def deterministic_risk_critic(
    *,
    hard_blocks: list[str],
    ai_opinion: str | None = None,
) -> dict[str, Any]:
    """AI may explain a hard block; AI may not remove or override one."""
    active = [b for b in hard_blocks if b in HARD_RISK_BLOCKS]
    blocked = len(active) > 0
    return {
        "blocked": blocked,
        "hard_blocks": active,
        "ai_opinion": ai_opinion,
        "ai_override_allowed": False,
        "order_permission": "BLOCK" if blocked else "ALLOW",
        "decision_status": "BLOCKED" if blocked else "PASS",
    }


def create_lesson_from_outcome(
    *,
    trade_id: str,
    symbol: str,
    symbol_profile: dict[str, Any],
    strategy_id: str,
    regime: str,
    direction: str,
    pnl: float,
    process_good: bool,
    reflection_provider: str,
    reflection_model: str,
    critic_provider: str,
    critic_model: str,
    root_causes: list[str] | None = None,
) -> LessonRecord:
    win = pnl > 0
    if process_good and win:
        cls = "GOOD_PROCESS_WIN"
    elif process_good and not win:
        cls = "GOOD_PROCESS_LOSS"
    elif not process_good and win:
        cls = "BAD_PROCESS_WIN"
    else:
        cls = "BAD_PROCESS_LOSS"
    immediate: list[str] = []
    proposed: list[str] = []
    if cls == "BAD_PROCESS_WIN":
        immediate = ["require_additional_confirmation", "reduce_candidate_priority"]
        # Negative lesson even on win
        proposed = ["policy_change_requires_eati"]  # proposal only, not immediate
    elif cls == "GOOD_PROCESS_LOSS":
        immediate = []  # loss is not automatic error / policy change
        proposed = []
    elif cls == "BAD_PROCESS_LOSS":
        immediate = ["symbol_cooldown", "confidence_penalty"]
        proposed = ["policy_change_requires_eati"]
    status = "PROPOSED"
    if immediate:
        status = "VALIDATED_AS_TEMPORARY_CONTROL"
    return LessonRecord(
        lesson_id=str(uuid.uuid4()),
        source_trade_id=trade_id,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        process_classification=cls,
        root_causes=root_causes or [],
        evidence_ids=[trade_id],
        symbol=symbol,
        symbol_profile=symbol_profile,
        strategy_id=strategy_id,
        regime=regime,
        direction=direction,
        entry_context={},
        cost_context={},
        risk_context={},
        applicable_conditions=[],
        contradicting_conditions=[],
        confidence=0.6,
        reflection_provider=reflection_provider,
        reflection_model=reflection_model,
        critic_provider=critic_provider,
        critic_model=critic_model,
        immediate_safe_actions=immediate,
        proposed_policy_changes=proposed,
        referenced_prior_lessons=[],
        status=status,
    )


def main_reasoner_with_lessons(
    *,
    memory: LessonMemory,
    symbol: str,
    strategy_id: str,
) -> ReasonerLessonApplication:
    retrieved = memory.retrieve(symbol=symbol, strategy_id=strategy_id)
    applied: list[str] = []
    ignored: list[str] = []
    for lesson in retrieved:
        if lesson.process_classification in ("BAD_PROCESS_WIN", "BAD_PROCESS_LOSS"):
            applied.append(lesson.lesson_id)
        else:
            ignored.append(lesson.lesson_id)
    return ReasonerLessonApplication(
        retrieved_lesson_ids=[l.lesson_id for l in retrieved],
        applied_lesson_ids=applied,
        ignored_lesson_ids=ignored,
        lesson_application_reason="apply_negative_process_lessons_as_context_only",
    )


def qualification_identity(*, provider: str, model: str, policy_id: str) -> str:
    return _sha({"provider": provider, "model": model, "policy_id": policy_id})
