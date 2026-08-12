"""Autonomy metrics counters — §49 / §50 / §44 funnel."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AutonomyMetrics:
    market_state_cycles: int = 0
    radar_candidates_seen: int = 0
    deep_quant_evaluations: int = 0
    ai_reasoner_evaluations: int = 0
    ai_critic_evaluations: int = 0
    prepared_decisions_created: int = 0
    prepared_decisions_triggered: int = 0
    prepared_decisions_expired: int = 0
    research_risk_pass_count: int = 0
    research_risk_block_count: int = 0
    research_demo_orders: int = 0
    research_demo_completed_lifecycles: int = 0
    research_demo_wins: int = 0
    research_demo_losses: int = 0
    good_process_win: int = 0
    good_process_loss: int = 0
    bad_process_win: int = 0
    bad_process_loss: int = 0
    wait_decisions: int = 0
    blocked_decisions: int = 0
    counterfactuals_completed: int = 0
    reflections_completed: int = 0
    lesson_candidates_created: int = 0
    active_lessons_created_from_live_demo: int = 0
    # Funnel §44 extras
    reasoner_long: int = 0
    reasoner_short: int = 0
    reasoner_wait: int = 0
    critic_rejected: int = 0
    trigger_not_reached: int = 0
    slow_path_leak_count: int = 0
    latency_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def funnel_counts(self) -> dict[str, Any]:
        return {
            "radar_candidates": self.radar_candidates_seen,
            "deep_evaluated": self.deep_quant_evaluations,
            "ai_evaluated": self.ai_reasoner_evaluations,
            "reasoner_long": self.reasoner_long,
            "reasoner_short": self.reasoner_short,
            "reasoner_wait": self.reasoner_wait,
            "critic_rejected": self.critic_rejected,
            "research_risk_rejected": self.research_risk_block_count,
            "prepared_decisions": self.prepared_decisions_created,
            "expired_prepared_decisions": self.prepared_decisions_expired,
            "trigger_not_reached": self.trigger_not_reached,
            "orders_executed": self.research_demo_orders,
        }

    def note_process_class(self, process_class: str) -> None:
        key = str(process_class or "").lower()
        if key == "good_process_win":
            self.good_process_win += 1
        elif key == "good_process_loss":
            self.good_process_loss += 1
        elif key == "bad_process_win":
            self.bad_process_win += 1
        elif key == "bad_process_loss":
            self.bad_process_loss += 1
