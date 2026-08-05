"""Expert cooldown and degradation state."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_strategy_expert_router.constants import (
    EXPERT_COOLDOWN_MS,
    EXPERT_DEGRADATION_THRESHOLD,
    EXPERT_IDS,
)


@dataclass
class ExpertRuntimeState:
    expert_id: str
    cooldown_until_ms: int = 0
    consecutive_soft_failures: int = 0
    degraded: bool = False
    last_selected_ts_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_id": self.expert_id,
            "cooldown_until_ms": self.cooldown_until_ms,
            "consecutive_soft_failures": self.consecutive_soft_failures,
            "degraded": self.degraded,
            "last_selected_ts_ms": self.last_selected_ts_ms,
        }


@dataclass
class CooldownBook:
    states: dict[str, ExpertRuntimeState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for eid in EXPERT_IDS:
            self.states.setdefault(eid, ExpertRuntimeState(expert_id=eid))

    def is_cooling(self, expert_id: str, ts_ms: int) -> bool:
        st = self.states[expert_id]
        return ts_ms < st.cooldown_until_ms

    def is_degraded(self, expert_id: str) -> bool:
        return bool(self.states[expert_id].degraded)

    def record_selection(self, expert_id: str, ts_ms: int) -> None:
        st = self.states[expert_id]
        st.last_selected_ts_ms = ts_ms
        # Defensive expert is never cooled out of availability.
        if expert_id == "DEFENSIVE_NO_TRADE":
            return
        st.cooldown_until_ms = ts_ms + EXPERT_COOLDOWN_MS

    def record_soft_failure(self, expert_id: str) -> None:
        if expert_id == "DEFENSIVE_NO_TRADE":
            return
        st = self.states[expert_id]
        st.consecutive_soft_failures += 1
        if st.consecutive_soft_failures >= EXPERT_DEGRADATION_THRESHOLD:
            st.degraded = True

    def record_success(self, expert_id: str) -> None:
        st = self.states[expert_id]
        st.consecutive_soft_failures = 0
        # Degradation clears only on explicit recovery path (not auto).
        # Leave degraded flag until recover().

    def recover(self, expert_id: str) -> None:
        st = self.states[expert_id]
        st.degraded = False
        st.consecutive_soft_failures = 0
        st.cooldown_until_ms = 0

    def apply_score_penalty(self, expert_id: str, score: float, ts_ms: int) -> float:
        """Cooldown / degradation soft-penalties; defensive never zeroed."""
        if expert_id == "DEFENSIVE_NO_TRADE":
            return score
        out = score
        if self.is_cooling(expert_id, ts_ms):
            out -= 1.5
        if self.is_degraded(expert_id):
            out -= 2.0
        return out

    def to_dict(self) -> dict[str, Any]:
        return {k: v.to_dict() for k, v in self.states.items()}
