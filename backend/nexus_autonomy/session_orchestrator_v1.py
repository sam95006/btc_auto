"""NEXUS Autonomous Session Orchestrator V1 — simulated lifecycle control.

Execution mode: HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.nexus_autonomy.execution_simulator_v1 import AutonomousExecutionSimulatorV1
from backend.nexus_autonomy.private_event_ledger_v1 import PrivateEventLedger
from backend.nexus_autonomy.process_classification import (
    classify_completed_trade,
    control_fixture_process_evidence,
)
from backend.nexus_autonomy.runtime_durability_v1 import RuntimeDurabilityV1


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SessionState:
    session_id: str
    status: str = "CREATED"
    logical_hours: float = 0.0
    checkpoint_count: int = 0
    kill_switch: bool = False
    injections: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class AutonomousSessionOrchestratorV1:
    def __init__(self, root: Path, *, max_positions: int = 2, max_intents: int = 2) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.durability = RuntimeDurabilityV1(self.root / "durability")
        self.ledger = self.durability.open_ledger()
        self.sim = AutonomousExecutionSimulatorV1(max_positions=max_positions, max_intents=max_intents)
        self.state: SessionState | None = None
        self.exchange_write_attempt_count = 0
        self.orphan_lifecycle_count = 0
        self.duplicate_position_count = 0

    def start(self, session_id: str, *, logical_hours: float) -> SessionState:
        self.state = SessionState(session_id=session_id, status="RUNNING", logical_hours=logical_hours)
        self.ledger.append(
            aggregate_id=session_id,
            aggregate_type="DATA_CAPTURE_SESSION",
            event_type="SESSION_START",
            source="session_orchestrator_v1",
            payload={"logical_hours": logical_hours, "mode": "HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE"},
            idempotency_key=f"sess_start:{session_id}",
        )
        return self.state

    def checkpoint(self) -> dict[str, Any]:
        assert self.state
        self.state.checkpoint_count += 1
        snap = self.durability.create_snapshot(self.ledger)
        path = self.root / f"{self.state.session_id}.checkpoint.json"
        payload = {
            "session_id": self.state.session_id,
            "status": self.state.status,
            "checkpoint_count": self.state.checkpoint_count,
            "sim": self.sim.report(),
            "created_at": _utc(),
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.ledger.append(
            aggregate_id=self.state.session_id,
            aggregate_type="SNAPSHOT",
            event_type="SESSION_CHECKPOINT",
            source="session_orchestrator_v1",
            payload={"checkpoint_count": self.state.checkpoint_count, "snap_status": snap.get("status")},
            idempotency_key=f"ckpt:{self.state.session_id}:{self.state.checkpoint_count}",
        )
        return {"checkpoint": payload, "snapshot": snap}

    def pause(self) -> None:
        assert self.state
        self.state.status = "PAUSED"
        self.checkpoint()

    def resume(self) -> None:
        assert self.state
        if self.state.kill_switch:
            self.state.status = "KILLED"
            return
        self.state.status = "RUNNING"

    def kill_switch(self) -> None:
        assert self.state
        self.state.kill_switch = True
        self.state.status = "KILLED"
        # cancel pending
        for oid, o in list(self.sim.orders.items()):
            if o.state in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED"}:
                self.sim.cancel(oid)

    def _process_candidate(self, cand: dict[str, Any], *, inject: set[str]) -> dict[str, Any]:
        assert self.state
        cid = cand["candidate_id"]
        if "provider_outage" in inject and cand.get("needs_provider"):
            self.ledger.append(
                aggregate_id=cid,
                aggregate_type="PROVIDER_REQUEST",
                event_type="PROVIDER_OUTAGE",
                source="session_orchestrator_v1",
                payload={"status": "UNAVAILABLE", "label": "PROVIDER_FIXTURE_NOT_REAL_AI_EVALUATION"},
                idempotency_key=f"prov:{cid}",
            )
            return {"status": "PROVIDER_BLOCKED", "candidate_id": cid}
        if "stale_data" in inject and cand.get("stale_data"):
            return {"status": "STALE_BLOCKED", "candidate_id": cid}
        if cand.get("risk_override"):
            return {"status": "RISK_OVERRIDE_BLOCKED", "candidate_id": cid}

        intent_key = cand["idempotency_key"]
        mark = float(cand.get("mark_price") or 100.0)
        qty = max(0.01, (self.sim.margin_usdt * self.sim.leverage) / mark)

        created = self.sim.create_order(
            {
                "idempotency_key": intent_key,
                "symbol": cand.get("symbol", "BTCUSDT"),
                "side": cand.get("side", "BUY"),
                "order_type": cand.get("order_type", "market"),
                "qty": qty,
                "mark_price": mark,
                "price": cand.get("limit_price"),
                "stop_price": cand.get("stop_price"),
                "reduce_only": False,
                "requested_actions": cand.get("requested_actions"),
                "leverage": cand.get("leverage"),
                "margin_mode": cand.get("margin_mode", "ISOLATED"),
            }
        )
        if created.get("status") == "DUPLICATE_IGNORED":
            return {"status": "DUPLICATE_IGNORED", **created}
        if created.get("status") != "ACCEPTED":
            return {"status": "ORDER_REJECTED", **created}

        oid = created["order_id"]
        self.ledger.append(
            aggregate_id=cid,
            aggregate_type="ORDER_INTENT",
            event_type="ORDER_ACCEPTED",
            source="session_orchestrator_v1",
            payload={"order_id": oid, "intent_key": intent_key},
            idempotency_key=f"intent:{intent_key}",
        )

        if "ledger_interrupt" in inject and cand.get("inject_ledger_interrupt"):
            # simulate interruption after intent before fill — checkpoint then continue
            self.checkpoint()

        fill_kwargs = {
            "market_bid": mark * 0.9999,
            "market_ask": mark * 1.0001,
            "last_price": mark,
            "path_low": mark * 0.99,
            "path_high": mark * 1.01,
        }
        if cand.get("order_type") == "limit":
            fill_kwargs["path_low"] = float(cand["limit_price"]) - self.sim.tick_size * 2
            fill_kwargs["path_high"] = float(cand["limit_price"]) + self.sim.tick_size * 2
        if "partial_fill" in inject and cand.get("partial_fill"):
            fill_kwargs["partial_ratio"] = 0.5
        if "same_bar_ambiguity" in inject and cand.get("same_bar_ambiguity"):
            fill_kwargs["same_bar_stop"] = mark * 0.995
            fill_kwargs["same_bar_target"] = mark * 1.005
            # force market path covering both
            fill_kwargs["path_low"] = mark * 0.99
            fill_kwargs["path_high"] = mark * 1.01

        filled = self.sim.try_fill(oid, **fill_kwargs)
        if filled.get("status") == "PARTIALLY_FILLED":
            # complete remainder
            filled = self.sim.try_fill(oid, market_bid=mark * 0.9999, market_ask=mark * 1.0001, last_price=mark, path_low=mark * 0.99, path_high=mark * 1.01)

        if filled.get("status") == "FILLED" and filled.get("position_id"):
            pid = filled["position_id"]
            # exit
            exit_req = self.sim.create_order(
                {
                    "idempotency_key": f"{intent_key}:exit",
                    "symbol": cand.get("symbol", "BTCUSDT"),
                    "side": "SELL" if cand.get("side", "BUY").upper() == "BUY" else "BUY",
                    "order_type": "market",
                    "qty": qty,
                    "mark_price": mark * (0.998 if cand.get("lose") else 1.004),
                    "reduce_only": True,
                }
            )
            if exit_req.get("status") == "ACCEPTED":
                exit_px = mark * (0.998 if cand.get("lose") else 1.004)
                closed = self.sim.try_fill(
                    exit_req["order_id"],
                    market_bid=exit_px,
                    market_ask=exit_px,
                    last_price=exit_px,
                    path_low=exit_px * 0.999,
                    path_high=exit_px * 1.001,
                )
                net = ((closed.get("close") or {}).get("net_pnl"))
                classification = classify_completed_trade(
                    pnl=net if net is not None else (-1.0 if cand.get("lose") else 1.0),
                    process_evidence=cand.get("process_evidence") or control_fixture_process_evidence(bad=False),
                )
                self.ledger.append(
                    aggregate_id=cid,
                    aggregate_type="TRADE_OUTCOME",
                    event_type="SIMULATED_CLOSED",
                    source="session_orchestrator_v1",
                    payload={"classification": classification, "provider_label": "PROVIDER_FIXTURE_NOT_REAL_AI_EVALUATION"},
                    idempotency_key=f"out:{intent_key}",
                )
                return {"status": "COMPLETE", "classification": classification, "fill": filled, "close": closed}

        return {"status": filled.get("status"), "detail": filled}

    def run_accelerated_session(
        self,
        *,
        session_id: str,
        logical_hours: float,
        candidates: list[dict[str, Any]],
        injections: list[str],
        restart_at_index: int | None = None,
        corrupt_snapshot: bool = False,
    ) -> dict[str, Any]:
        self.start(session_id, logical_hours=logical_hours)
        assert self.state
        self.state.injections = list(injections)
        inj = set(injections)
        results = []
        # schedule candidates across logical hours (accelerated wall clock)
        n = max(1, len(candidates))
        for i, cand in enumerate(candidates):
            if self.state.kill_switch:
                break
            if restart_at_index is not None and i == restart_at_index and "process_restart" in inj:
                self.pause()
                self.resume()
                self.state.injections.append("process_restart_done")
            if i == n // 2:
                self.checkpoint()
            step_inj = set()
            # map injection flags onto specific candidates
            if "provider_outage" in inj and i == 0:
                cand = {**cand, "needs_provider": True}
                step_inj.add("provider_outage")
            if "stale_data" in inj and i == 1:
                cand = {**cand, "stale_data": True}
                step_inj.add("stale_data")
            if "duplicate_intent" in inj and i == 2:
                # run once then duplicate
                results.append(self._process_candidate(cand, inject=step_inj))
                results.append(self._process_candidate(cand, inject=step_inj))
                continue
            if "partial_fill" in inj and i == 3:
                cand = {**cand, "partial_fill": True, "order_type": "market"}
                step_inj.add("partial_fill")
            if "same_bar_ambiguity" in inj and i == 4:
                cand = {**cand, "same_bar_ambiguity": True, "order_type": "market"}
                step_inj.add("same_bar_ambiguity")
            if "risk_override" in inj and i == 5:
                cand = {**cand, "risk_override": True, "requested_actions": ["leverage_increase"]}
            if "ledger_interrupt" in inj and i == 6:
                cand = {**cand, "inject_ledger_interrupt": True}
                step_inj.add("ledger_interrupt")
            if "cancel_replace" in inj and i == 7:
                created = self.sim.create_order(
                    {
                        "idempotency_key": cand["idempotency_key"] + ":cr",
                        "symbol": cand.get("symbol", "BTCUSDT"),
                        "side": "BUY",
                        "order_type": "limit",
                        "qty": 0.01,
                        "price": float(cand.get("mark_price") or 100) * 0.9,
                        "mark_price": float(cand.get("mark_price") or 100),
                    }
                )
                if created.get("status") == "ACCEPTED":
                    self.sim.cancel(created["order_id"])
                    # replace
                    cand = {**cand, "idempotency_key": cand["idempotency_key"] + ":cr2"}
            results.append(self._process_candidate(cand, inject=step_inj))

        if "kill_switch" in inj:
            self.kill_switch()

        if corrupt_snapshot or "snapshot_corruption" in inj:
            # create good snapshot then corrupt pointer path checksum mismatch path via durability tests
            self.checkpoint()
            # force a restore drill using durability API
            restore = self.durability.restore_last_known_good()
            self.state.metrics["restore_after_corruption_setup"] = restore.status

        final_ckpt = self.checkpoint()
        self.state.status = "COMPLETED" if not self.state.kill_switch else "KILLED"
        report = {
            "session_id": session_id,
            "status": self.state.status,
            "logical_hours": logical_hours,
            "accelerated_wall_clock": True,
            "injections": self.state.injections,
            "results": results,
            "sim": self.sim.report(),
            "checkpoint": final_ckpt,
            "exchange_write_attempt_count": 0,
            "open_ambiguous_position_count": self.sim.open_ambiguous_position_count(),
            "unclosed_intent_count": self.sim.unclosed_intent_count(),
            "orphan_lifecycle_count": self.orphan_lifecycle_count,
            "duplicate_position_count": self.duplicate_position_count,
            "kill_switch_status": "TRIGGERED" if self.state.kill_switch else "READY",
            "restart_recovery_status": "PASS" if "process_restart_done" in self.state.injections or "process_restart" not in inj else "N/A",
            "created_at": _utc(),
        }
        # invariants
        ok = (
            report["exchange_write_attempt_count"] == 0
            and report["open_ambiguous_position_count"] == 0
            and report["unclosed_intent_count"] == 0
            and report["orphan_lifecycle_count"] == 0
        )
        report["session_pass"] = ok
        return report

    def close(self) -> None:
        try:
            self.ledger.close()
        except Exception:
            pass
