"""Policy split: RESEARCH_AI_DEMO vs QUALIFIED_SYSTEM_DEMO."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research_ai_autonomy.constants import (
    DEFAULT_LEVERAGE,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_HOLD_SEC,
    DEFAULT_MAX_NEW_ENTRIES_24H,
    EXECUTION_PURPOSE_QUALIFIED,
    EXECUTION_PURPOSE_RESEARCH,
    POLICY_QUALIFIED_SYSTEM_DEMO,
    POLICY_RESEARCH_AI_DEMO,
)


@dataclass
class PolicyRequirements:
    policy: str
    execution_purpose: str
    requires_pre_wf: bool
    requires_formal_wf: bool
    requires_oos: bool
    requires_risk_review: bool
    may_use_radar_eligible_without_trade_eligible: bool
    max_new_entries_24h: int = DEFAULT_MAX_NEW_ENTRIES_24H
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    leverage: int = DEFAULT_LEVERAGE
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC
    protective_stop_required: bool = True
    contamination_into_formal_forbidden: bool = True


RESEARCH_AI_DEMO_POLICY = PolicyRequirements(
    policy=POLICY_RESEARCH_AI_DEMO,
    execution_purpose=EXECUTION_PURPOSE_RESEARCH,
    requires_pre_wf=False,
    requires_formal_wf=False,
    requires_oos=False,
    requires_risk_review=True,  # Research Risk, not Formal Risk Review
    may_use_radar_eligible_without_trade_eligible=True,
)

QUALIFIED_SYSTEM_DEMO_POLICY = PolicyRequirements(
    policy=POLICY_QUALIFIED_SYSTEM_DEMO,
    execution_purpose=EXECUTION_PURPOSE_QUALIFIED,
    requires_pre_wf=True,
    requires_formal_wf=True,
    requires_oos=True,
    requires_risk_review=True,
    may_use_radar_eligible_without_trade_eligible=False,
    max_new_entries_24h=0,  # not governed by exploration budget
)


def get_policy(name: str) -> PolicyRequirements:
    key = str(name or "").strip().upper()
    if key == POLICY_RESEARCH_AI_DEMO:
        return RESEARCH_AI_DEMO_POLICY
    if key == POLICY_QUALIFIED_SYSTEM_DEMO:
        return QUALIFIED_SYSTEM_DEMO_POLICY
    raise ValueError(f"unknown_policy:{name}")


def formal_gate_blocks_research(formal_status: dict[str, Any] | None) -> bool:
    """Formal WF/OOS alone must NEVER block RESEARCH_AI_DEMO."""
    _ = formal_status
    return False


@dataclass
class ExplorationBudget:
    max_new_entries_24h: int = DEFAULT_MAX_NEW_ENTRIES_24H
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    entries_timestamps_ms: list[int] = field(default_factory=list)
    open_positions: int = 0

    def prune(self, now_ms: int) -> None:
        cutoff = now_ms - 24 * 3600 * 1000
        self.entries_timestamps_ms = [t for t in self.entries_timestamps_ms if t >= cutoff]

    def can_open(self, now_ms: int) -> tuple[bool, str]:
        self.prune(now_ms)
        if self.open_positions >= self.max_concurrent:
            return False, "concurrent_cap"
        if len(self.entries_timestamps_ms) >= self.max_new_entries_24h:
            return False, "rolling_24h_cap"
        return True, "ok"

    def record_entry(self, now_ms: int) -> None:
        self.entries_timestamps_ms.append(now_ms)
        self.open_positions += 1

    def record_close(self) -> None:
        self.open_positions = max(0, self.open_positions - 1)
