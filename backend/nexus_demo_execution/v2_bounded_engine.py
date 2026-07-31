"""Bounded session engine shell for 6H V2 / 12H V3 — dry-run safe, no auto-extend."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_demo_execution.v2_kill_switch import evaluate_kill_switch
from backend.nexus_demo_execution.v2_session_state import (
    COMPLETED,
    CREATED,
    EXPORTING,
    FAILED,
    FLATTENING,
    KILLED,
    PREFLIGHT,
    READY,
    RECONCILING,
    RUNNING,
    STOPPING,
    InvalidTransition,
    can_transition,
    transition,
)


@dataclass
class BoundedSessionEngine:
    policy_version: str
    duration_sec: int
    max_session_net_loss: float
    max_single_trade_net_loss: float
    max_consecutive_losses: int
    max_bad_process_outcomes: int
    session_id: str = ""
    state: str = CREATED
    deadline_ts: float | None = None
    write_window_open: bool = False
    automatic_extension: bool = False
    entries_total: int = 0
    completed_trades: int = 0
    consecutive_losses: int = 0
    bad_process_outcomes: int = 0
    session_net_pnl: float = 0.0
    last_trade_net_pnl: float | None = None
    exchange_write_call_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("session_id_required")
        if self.automatic_extension:
            raise ValueError("automatic_extension_forbidden")

    def _evt(self, kind: str, **kw: Any) -> None:
        self.events.append({"kind": kind, "ts": time.time(), **kw})

    def advance(self, dst: str) -> str:
        self.state = transition(self.state, dst)
        self._evt("transition", state=self.state)
        return self.state

    def run_preflight_ok(self) -> None:
        self.advance(PREFLIGHT)
        self.advance(READY)

    def open_write_window(self, *, now: float | None = None) -> None:
        if self.state != READY:
            raise InvalidTransition(f"write window only from READY, have {self.state}")
        now = now or time.time()
        self.deadline_ts = now + self.duration_sec
        self.write_window_open = True
        self.advance(RUNNING)
        self._evt("write_window_open", deadline_ts=self.deadline_ts)

    def check_deadline(self, *, now: float | None = None) -> bool:
        now = now or time.time()
        if self.deadline_ts is None:
            return False
        if now >= self.deadline_ts:
            self.write_window_open = False
            self._evt("deadline_reached")
            if self.state == RUNNING:
                self.advance(STOPPING)
            return True
        return False

    def extend_deadline(self, *_a: Any, **_k: Any) -> None:
        raise InvalidTransition("automatic_extension_forbidden")

    def evaluate_risk_and_maybe_kill(self, **kw: Any) -> dict[str, Any]:
        decision = evaluate_kill_switch(
            session_net_pnl=self.session_net_pnl,
            max_session_net_loss=self.max_session_net_loss,
            last_trade_net_pnl=self.last_trade_net_pnl,
            max_single_trade_net_loss=self.max_single_trade_net_loss,
            consecutive_losses=self.consecutive_losses,
            max_consecutive_losses=self.max_consecutive_losses,
            bad_process_outcomes=self.bad_process_outcomes,
            max_bad_process_outcomes=self.max_bad_process_outcomes,
            duplicate_orders=int(kw.get("duplicate_orders") or 0),
            unprotected_positions=int(kw.get("unprotected_positions") or 0),
            protection_verify_timeout=bool(kw.get("protection_verify_timeout")),
            reconciliation=str(kw.get("reconciliation") or "MATCH"),
            execution_owner_count=int(kw.get("execution_owner_count") or 1),
            persistence_ok=bool(kw.get("persistence_ok", True)),
            runtime_stall=bool(kw.get("runtime_stall")),
            fee_expired=bool(kw.get("fee_expired")),
            mainnet=bool(kw.get("mainnet")),
            real_money=bool(kw.get("real_money")),
        )
        if decision.triggered:
            self.write_window_open = False
            if self.state not in {KILLED, COMPLETED, FAILED}:
                if can_transition(self.state, KILLED):
                    self.advance(KILLED)
                elif self.state == RUNNING:
                    self.advance(STOPPING)
                    self.advance(FLATTENING)
                    self.advance(RECONCILING)
                    self.advance(EXPORTING)
                    self.advance(KILLED)
                else:
                    self.state = KILLED
            self._evt("kill", reason=decision.reason)
        return decision.to_dict()

    def finalize_success(self) -> None:
        self.write_window_open = False
        if self.state == RUNNING:
            self.advance(STOPPING)
        if self.state == STOPPING:
            self.advance(FLATTENING)
        if self.state == FLATTENING:
            self.advance(RECONCILING)
        if self.state == RECONCILING:
            self.advance(EXPORTING)
        if self.state == EXPORTING:
            self.advance(COMPLETED)

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "policy_version": self.policy_version,
            "state": self.state,
            "deadline_ts": self.deadline_ts,
            "write_window_open": self.write_window_open,
            "automatic_extension": False,
            "entries_total": self.entries_total,
            "completed_trades": self.completed_trades,
            "consecutive_losses": self.consecutive_losses,
            "bad_process_outcomes": self.bad_process_outcomes,
            "session_net_pnl": self.session_net_pnl,
            "exchange_write_call_count": self.exchange_write_call_count,
            "mainnet": False,
            "real_money": False,
        }


def new_6h_session_id(nonce: str) -> str:
    utc = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"NEXUS-DEMO-6H-V2-{utc}-{nonce}"


def new_12h_session_id(nonce: str) -> str:
    utc = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"NEXUS-DEMO-12H-V3-{utc}-{nonce}"


def make_engine_6h(*, nonce: str | None = None) -> BoundedSessionEngine:
    from backend.nexus_demo_execution import v2_policy as p

    return BoundedSessionEngine(
        session_id=new_6h_session_id(nonce or uuid.uuid4().hex[:8]),
        policy_version=p.POLICY_VERSION,
        duration_sec=p.SESSION_DURATION_SEC,
        max_session_net_loss=p.MAX_SESSION_NET_LOSS,
        max_single_trade_net_loss=p.MAX_SINGLE_TRADE_NET_LOSS,
        max_consecutive_losses=p.MAX_CONSECUTIVE_LOSSES,
        max_bad_process_outcomes=p.MAX_BAD_PROCESS_OUTCOMES,
        automatic_extension=False,
    )


def make_engine_12h(*, nonce: str | None = None) -> BoundedSessionEngine:
    from backend.nexus_demo_execution import v3_policy as p

    return BoundedSessionEngine(
        session_id=new_12h_session_id(nonce or uuid.uuid4().hex[:8]),
        policy_version=p.POLICY_VERSION,
        duration_sec=p.SESSION_DURATION_SEC,
        max_session_net_loss=p.MAX_SESSION_NET_LOSS,
        max_single_trade_net_loss=p.MAX_SINGLE_TRADE_NET_LOSS,
        max_consecutive_losses=p.MAX_CONSECUTIVE_LOSSES,
        max_bad_process_outcomes=p.MAX_BAD_PROCESS_OUTCOMES,
        automatic_extension=False,
    )
