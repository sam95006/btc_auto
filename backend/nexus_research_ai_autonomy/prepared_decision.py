"""PreparedDecision object + state machine — AI prepares BEFORE trigger."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_research_ai_autonomy.constants import (
    DEFAULT_PREPARED_TTL_SEC,
    EXECUTION_PURPOSE_RESEARCH,
    PREPARED_DECISION_STATES,
)
from backend.nexus_research_ai_autonomy.horizon_feasibility import (
    HorizonPlan,
    validate_horizon_configuration,
)

LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "PREPARING": frozenset({"READY", "REJECTED", "INVALIDATED", "EXPIRED"}),
    "READY": frozenset({"TRIGGERED", "INVALIDATED", "EXPIRED", "REJECTED"}),
    "TRIGGERED": frozenset({"EXECUTED", "REJECTED", "INVALIDATED"}),
    "EXECUTED": frozenset(),
    "REJECTED": frozenset(),
    "INVALIDATED": frozenset(),
    "EXPIRED": frozenset(),
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _new_id() -> str:
    return f"pd_{uuid.uuid4().hex[:16]}"


@dataclass
class PreparedDecision:
    decision_id: str = field(default_factory=_new_id)
    created_at: int = field(default_factory=_now_ms)
    expires_at: int = 0
    symbol: str = ""
    regime: str = "UNCERTAIN"
    strategy_family: str = ""
    side: str = ""  # LONG | SHORT | WAIT | BLOCK
    setup_type: str = ""
    entry_trigger: dict[str, Any] = field(default_factory=dict)
    entry_style: str = "STOP_OR_ZONE"
    entry_zone: dict[str, Any] = field(default_factory=dict)
    expected_edge: float | None = None
    estimated_cost: float | None = None
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    invalidation: list[str] = field(default_factory=list)
    stop_logic: dict[str, Any] = field(default_factory=dict)
    take_profit_logic: dict[str, Any] = field(default_factory=dict)
    max_hold: int = 3600
    requested_size: float = 0.0
    research_policy: str = EXECUTION_PURPOSE_RESEARCH
    status: str = "PREPARING"
    # V18.2.25 — horizon-consistent thesis fields (not a transport timer)
    entry_horizon: str = ""
    expected_target_move_pct: float | None = None
    stop_move_pct: float | None = None
    target_price: float | None = None
    stop_price: float | None = None
    expected_time_to_target: float | None = None
    expected_time_to_stop: float | None = None
    recommended_hold_window: list[float] = field(default_factory=list)
    hard_max_hold: int | None = None
    horizon_provenance: str = ""
    horizon_feasibility_pass: bool | None = None
    economic_edge_pass: bool | None = None
    # Provenance extras
    candidate_id: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    reasoner_result: dict[str, Any] = field(default_factory=dict)
    critic_result: dict[str, Any] = field(default_factory=dict)
    risk_result: dict[str, Any] = field(default_factory=dict)
    radar_snapshot: dict[str, Any] = field(default_factory=dict)
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    activity_snapshot: dict[str, Any] = field(default_factory=dict)
    transition_log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.expires_at:
            self.expires_at = self.created_at + DEFAULT_PREPARED_TTL_SEC * 1000
        if self.status not in PREPARED_DECISION_STATES:
            raise ValueError(f"invalid_status:{self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def transition(self, to_status: str, *, reason: str = "") -> None:
        to_u = str(to_status).upper()
        if to_u not in PREPARED_DECISION_STATES:
            raise ValueError(f"invalid_status:{to_status}")
        allowed = LEGAL_TRANSITIONS.get(self.status, frozenset())
        if to_u not in allowed:
            raise ValueError(f"illegal_transition:{self.status}->{to_u}")
        self.transition_log.append(
            {"from": self.status, "to": to_u, "reason": reason, "at_ms": _now_ms()}
        )
        self.status = to_u

    def check_invalidate(self, *, now_ms: int | None = None, context: dict[str, Any] | None = None) -> str | None:
        """Return invalidate/expire reason or None if still valid."""
        now = now_ms if now_ms is not None else _now_ms()
        if self.status in {"EXECUTED", "REJECTED", "INVALIDATED", "EXPIRED"}:
            return None
        if now >= self.expires_at:
            if self.status in {"PREPARING", "READY", "TRIGGERED"}:
                self.transition("EXPIRED", reason="ttl")
            return "ttl"
        ctx = dict(context or {})
        if ctx.get("regime") and str(ctx["regime"]).upper() != str(self.regime).upper():
            if abs(float(ctx.get("regime_confidence") or 0)) >= 0.5:
                if self.status in {"PREPARING", "READY", "TRIGGERED"}:
                    self.transition("INVALIDATED", reason="regime_change")
                return "regime_change"
        if ctx.get("data_stale"):
            if self.status in {"PREPARING", "READY", "TRIGGERED"}:
                self.transition("INVALIDATED", reason="data_stale")
            return "data_stale"
        if ctx.get("liquidity_deteriorated"):
            if self.status in {"PREPARING", "READY", "TRIGGERED"}:
                self.transition("INVALIDATED", reason="liquidity_deteriorated")
            return "liquidity_deteriorated"
        if ctx.get("risk_changed_block"):
            if self.status in {"PREPARING", "READY", "TRIGGERED"}:
                self.transition("INVALIDATED", reason="risk_changed")
            return "risk_changed"
        if ctx.get("setup_invalid"):
            if self.status in {"PREPARING", "READY", "TRIGGERED"}:
                self.transition("INVALIDATED", reason="setup_invalid")
            return "setup_invalid"
        return None


def validate_prepared_decision_horizon(decision: dict[str, Any] | PreparedDecision) -> dict[str, Any]:
    """PreparedDecision horizon validation — INVALID_HORIZON_CONFIGURATION blocker."""
    d = decision.to_dict() if isinstance(decision, PreparedDecision) else dict(decision)
    win = d.get("recommended_hold_window") or [0, 0]
    plan = HorizonPlan(
        strategy_family=str(d.get("strategy_family") or "TREND"),
        entry_horizon=str(d.get("entry_horizon") or ""),
        expected_target_move_pct=float(d.get("expected_target_move_pct") or 0.55),
        stop_move_pct=float(d.get("stop_move_pct") or 0.40),
        target_price=float(d.get("target_price") or 0),
        stop_price=float(d.get("stop_price") or 0),
        expected_time_to_target=float(d.get("expected_time_to_target") or 1200),
        expected_time_to_stop=float(d.get("expected_time_to_stop") or 600),
        recommended_hold_window=(float(win[0]), float(win[1] if len(win) > 1 else win[0])),
        hard_max_hold=int(d.get("hard_max_hold") or d.get("max_hold") or 3600),
        provenance=str(d.get("horizon_provenance") or "prepared_decision_validation"),
    )
    cfg_ok, cfg_reasons, cfg_block = validate_horizon_configuration(plan)
    out = {
        "valid": cfg_ok,
        "block_code": cfg_block,
        "reasons": cfg_reasons,
        "blocks": [cfg_block] if cfg_block else [],
    }
    out["RESEARCH_PNL_TRADE_requires_both"] = {
        "ECONOMIC_EDGE_PASS": d.get("economic_edge_pass"),
        "HORIZON_FEASIBILITY_PASS": d.get("horizon_feasibility_pass"),
    }
    if not cfg_ok:
        out["action"] = "REJECT"
        out["status_blocker"] = "INVALID_HORIZON_CONFIGURATION"
    else:
        out["action"] = "OK"
    return out


class PreparedDecisionStore:
    def __init__(self) -> None:
        self._items: dict[str, PreparedDecision] = {}

    def put(self, decision: PreparedDecision) -> None:
        self._items[decision.decision_id] = decision

    def get(self, decision_id: str) -> PreparedDecision | None:
        return self._items.get(decision_id)

    def list_by_status(self, status: str) -> list[PreparedDecision]:
        return [d for d in self._items.values() if d.status == status]

    def all(self) -> list[PreparedDecision]:
        return list(self._items.values())
