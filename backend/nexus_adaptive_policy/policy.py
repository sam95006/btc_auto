"""Dynamic trading policies and decision traces."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_adaptive_policy import FIXED_LEVERAGE, MAX_MARGIN, MIN_MARGIN


@dataclass
class PolicySnapshot:
    snapshot_id: str
    leverage: int = FIXED_LEVERAGE
    min_margin: int = MIN_MARGIN
    max_margin: int = MAX_MARGIN
    entry_threshold: float = 0.55
    strategy_id: str = "default"
    exit_time_stop_minutes: int = 60
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "leverage": self.leverage,
            "min_margin": self.min_margin,
            "max_margin": self.max_margin,
            "entry_threshold": self.entry_threshold,
            "strategy_id": self.strategy_id,
            "exit_time_stop_minutes": self.exit_time_stop_minutes,
            "metadata": dict(self.metadata),
        }


@dataclass
class PolicyDecisionTrace:
    trace_id: str
    decision: str
    reason: str
    leverage: int = FIXED_LEVERAGE
    margin_usd: float = 0.0
    policy_snapshot_id: str = ""
    labels: list[str] = field(default_factory=lambda: ["SHADOW", "NO_EXCHANGE_WRITE"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "decision": self.decision,
            "reason": self.reason,
            "leverage": self.leverage,
            "margin_usd": self.margin_usd,
            "policy_snapshot_id": self.policy_snapshot_id,
            "labels": list(self.labels),
        }


class DynamicOrderPolicy:
    def __init__(self, snapshot: PolicySnapshot | None = None) -> None:
        self.snapshot = snapshot or PolicySnapshot(snapshot_id="default")

    def allowed_side(self, side: str) -> bool:
        return side.upper() in {"LONG", "SHORT", "BUY", "SELL"}


class DynamicExitPolicy:
    def __init__(self, snapshot: PolicySnapshot | None = None) -> None:
        self.snapshot = snapshot or PolicySnapshot(snapshot_id="default")

    def time_stop_minutes(self) -> int:
        return self.snapshot.exit_time_stop_minutes


class DynamicRiskAllocationPolicy:
    def __init__(self, snapshot: PolicySnapshot | None = None) -> None:
        self.snapshot = snapshot or PolicySnapshot(snapshot_id="default")

    def clamp_margin(self, suggested: float, *, risk_budget: float, portfolio_remaining: float) -> float:
        caps = [suggested, risk_budget, portfolio_remaining, float(self.snapshot.max_margin)]
        margin = min(caps)
        return margin


class DynamicTradingPolicy:
    """Aggregate dynamic policies; leverage remains fixed."""

    def __init__(self, snapshot: PolicySnapshot | None = None) -> None:
        snap = snapshot or PolicySnapshot(snapshot_id="default")
        self.snapshot = snap
        self.order = DynamicOrderPolicy(snap)
        self.exit = DynamicExitPolicy(snap)
        self.risk = DynamicRiskAllocationPolicy(snap)

    def entry_passes(self, score: float) -> bool:
        return score >= self.snapshot.entry_threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "fixed_leverage": FIXED_LEVERAGE,
        }
