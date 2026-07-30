"""DEMO_AUTONOMOUS_6H_BOUNDED_VALIDATION session runner.

NOTE: persistence.py STREAMS must include:
  session_checkpoints, decision_deltas, cost_gates, session_summaries,
  universe_scans, bounded_candidates
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution import SERVICE_NAME
from backend.nexus_demo_execution.allocation import AllocationResult, MarginAllocator
from backend.nexus_demo_execution.bounded_universe import scan_dynamic_candidates
from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError
from backend.nexus_demo_execution.http_demo_reader import redact_secrets
from backend.nexus_demo_execution.kill_switch import KillSwitch, KillSwitchTrigger
from backend.nexus_demo_execution.reconciliation import DemoReconciler, ReconciliationState
from backend.nexus_demo_execution.runtime_identity import capture_runtime_identity
from backend.nexus_demo_execution.session_limits import (
    CHECKPOINT_OFFSETS_SEC,
    CYCLE_INTERVAL_SEC,
    FIXED_LEVERAGE,
    MARGIN_MODE,
    MARGIN_PER_TRADE_CAP,
    MAX_BAD_PROCESS_OUTCOMES,
    MAX_CONSECUTIVE_LOSSES,
    MAX_HOLD_SEC,
    MAX_SESSION_NET_LOSS,
    MAX_TOTAL_ENTRY_ORDERS,
    POLICY_VERSION,
    PROTECTION_VERIFY_DEADLINE_SEC,
    SCHEMA_VERSION,
    SESSION_DURATION_SEC,
    SESSION_GATE_NAME,
    SUPERVISOR_POLL_SEC,
)
from backend.nexus_demo_execution.session_mistake_memory import SessionMistakeMemory

_TRUE = {"1", "true", "yes", "on"}
_RECS = (
    "DEMO_AUTONOMOUS_6H_PASS_AWAITING_24H_APPROVAL",
    "DEMO_AUTONOMOUS_6H_COMPLETED_WITH_FINDINGS",
    "DEMO_AUTONOMOUS_6H_BLOCKED_NO_VALID_CANDIDATES",
    "DEMO_AUTONOMOUS_6H_FAILED_KILL_SWITCH_APPLIED",
)


def _load_founder_gate_file() -> None:
    """Load ./demo_founder_gate.env if process env missing FOUNDER_GATE."""
    if (os.environ.get("FOUNDER_GATE") or "").strip():
        return
    for path in (Path("demo_founder_gate.env"), Path("/app/demo_founder_gate.env")):
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            return
        break


def _env_true(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _TRUE


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = redact_secrets(payload) if isinstance(payload, dict) else payload
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")


@dataclass
class Bounded6HSession:
    """Bounded 6H demo validation — smoke write window only; never DEMO_AUTONOMOUS_ENABLED stage."""

    gate: Any
    reader: Any
    persistence: Any
    epoch_tracker: Any
    kill_switch: KillSwitch
    writer: DemoWriteClient
    approval: Any
    export_dir: Path
    data_root: Path
    reconciler: DemoReconciler = field(default_factory=DemoReconciler)
    memory: SessionMistakeMemory = field(default_factory=SessionMistakeMemory)

    session_id: str = ""
    session_write_enabled: bool = False
    session_autonomous_enabled: bool = False
    _thread: threading.Thread | None = field(default=None, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _state: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.export_dir = Path(self.export_dir)
        self.data_root = Path(self.data_root)
        self._reset_counters()

    def _reset_counters(self) -> None:
        self._state = {
            "status": "IDLE",
            "session_id": "",
            "started_at": 0.0,
            "ended_at": 0.0,
            "stop_reason": "",
            "account_epoch": "",
            "starting_wallet": 0.0,
            "ending_wallet": 0.0,
            "starting_equity": 0.0,
            "ending_equity": 0.0,
            "candidates_total": 0,
            "risk_critic_blocks": 0,
            "mistake_guard_blocks": 0,
            "cost_gate_blocks": 0,
            "entries_total": 0,
            "trades_completed": 0,
            "wins": 0,
            "losses": 0,
            "gross_pnl": 0.0,
            "entry_fees": 0.0,
            "exit_fees": 0.0,
            "total_fees": 0.0,
            "funding": 0.0,
            "net_pnl": 0.0,
            "good_process_wins": 0,
            "good_process_losses": 0,
            "bad_process_wins": 0,
            "bad_process_losses": 0,
            "decision_delta_count": 0,
            "protection_incidents": 0,
            "duplicate_order_incidents": 0,
            "reconciliation_incidents": 0,
            "kill_switch_events": 0,
            "consecutive_losses": 0,
            "checkpoints_done": [],
            "open_position": False,
            "recommendation": "",
            "export_path": "",
            "runtime_identity": {},
        }

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return redact_secrets({"ok": False, "reason": "already_running", **self.status()})
            _load_founder_gate_file()
            gate_env = (os.environ.get("FOUNDER_GATE") or "").strip()
            if gate_env != SESSION_GATE_NAME:
                return redact_secrets(
                    {
                        "ok": False,
                        "reason": "founder_gate_mismatch",
                        "expected": SESSION_GATE_NAME,
                        "got": gate_env or "MISSING",
                        "founder_6h_approved": _env_true("FOUNDER_6H_APPROVED"),
                    }
                )
            if not _env_true("FOUNDER_6H_APPROVED"):
                return redact_secrets({"ok": False, "reason": "founder_6h_not_approved", "got_gate": gate_env})
            if self.kill_switch.engaged:
                return redact_secrets({"ok": False, "reason": "kill_switch_engaged"})

            self._reset_counters()
            self._stop.clear()
            self.session_id = f"NEXUS-DEMO-6H-{uuid.uuid4().hex[:10]}"
            self._state["session_id"] = self.session_id
            self._state["status"] = "STARTING"
            self._thread = threading.Thread(target=self._safe_run, name="bounded-6h", daemon=True)
            self._thread.start()
            return redact_secrets({"ok": True, "session_id": self.session_id, "status": "STARTING"})

    def stop(self, reason: str = "OPERATOR_STOP") -> None:
        self._stop.set()
        with self._lock:
            self._state["stop_reason"] = reason
        if reason and not self.kill_switch.engaged:
            self.kill_switch.engage(reason, trigger=KillSwitchTrigger.OPERATOR_STOP)
            with self._lock:
                self._state["kill_switch_events"] += 1

    def status(self) -> dict[str, Any]:
        with self._lock:
            snap = dict(self._state)
            snap.update(
                {
                    "session_write_enabled": self.session_write_enabled,
                    "session_autonomous_enabled": self.session_autonomous_enabled,
                    "gate_autonomous_mode": getattr(
                        getattr(self.gate, "autonomous_mode", None), "value", "DEMO_AUTONOMOUS_DISABLED"
                    ),
                    "smoke_write_window_open": bool(getattr(self.gate, "smoke_write_window_open", False)),
                    "smoke_orders_remaining": int(getattr(self.gate, "smoke_orders_remaining", 0) or 0),
                    "kill_switch": self.kill_switch.snapshot(),
                    "mistake_memory": self.memory.summary(),
                    "thread_alive": bool(self._thread and self._thread.is_alive()),
                }
            )
        return redact_secrets(snap)

    def _safe_run(self) -> None:
        try:
            self.run_loop()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._state["status"] = "FAILED"
                self._state["stop_reason"] = f"exception:{type(exc).__name__}"
            if not self.kill_switch.engaged:
                self.kill_switch.engage(str(exc)[:200], trigger=KillSwitchTrigger.GATE_FAILURE)
            self._finalize("exception")

    def run_loop(self) -> None:
        export_root = self.export_dir / f"session_{self.session_id}"
        export_root.mkdir(parents=True, exist_ok=True)
        ckpt_dir = export_root / "checkpoints"
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        snap = self.reader.read_with_constitution()
        epoch = self.epoch_tracker.observe(snap)
        account_epoch = epoch.epoch_id
        identity = capture_runtime_identity(
            account_epoch=account_epoch,
            policy_version=POLICY_VERSION,
            schema_version=SCHEMA_VERSION,
            service_name=SERVICE_NAME,
            data_root=self.data_root,
        )
        started = time.time()
        with self._lock:
            self._state.update(
                {
                    "status": "RUNNING",
                    "started_at": started,
                    "account_epoch": account_epoch,
                    "starting_wallet": snap.wallet_balance,
                    "starting_equity": snap.equity,
                    "runtime_identity": identity.to_dict(),
                    "export_path": str(export_root),
                }
            )

        self.session_autonomous_enabled = True
        self.session_write_enabled = True
        self.gate.open_smoke_write_window(max_orders=MAX_TOTAL_ENTRY_ORDERS)
        # Do NOT advance SafetyGateStage to DEMO_AUTONOMOUS_ENABLED.
        self._seed_baseline_memory(account_epoch)
        self._checkpoint(0, export_root, account_epoch)

        active: dict[str, Any] | None = None
        deadline = started + SESSION_DURATION_SEC
        allocator = MarginAllocator(
            min_margin=MARGIN_PER_TRADE_CAP,
            max_margin=MARGIN_PER_TRADE_CAP,
            max_open=1,
            max_pending=1,
            fixed_leverage=FIXED_LEVERAGE,
        )

        while not self._stop.is_set() and time.time() < deadline and not self.kill_switch.engaged:
            elapsed = time.time() - started
            self._maybe_checkpoints(elapsed, export_root, account_epoch)

            if active:
                active = self._supervise(active, export_root, account_epoch)
                if active is None and self._state["entries_total"] >= MAX_TOTAL_ENTRY_ORDERS:
                    break
                if active:
                    time.sleep(SUPERVISOR_POLL_SEC)
                    continue

            if self._state["entries_total"] >= MAX_TOTAL_ENTRY_ORDERS:
                break
            if self._risk_kill(account_epoch):
                break

            active = self._try_entry(allocator, export_root, account_epoch)
            if active is None:
                time.sleep(CYCLE_INTERVAL_SEC)

        if active:
            self._force_flat(active.get("symbol", ""), active.get("side", "Buy"), str(active.get("qty") or "0"))
            self._record_exit(active, "SESSION_END", export_root, account_epoch)

        self._finalize("duration" if time.time() >= deadline else (self._state.get("stop_reason") or "completed"))

    def _seed_baseline_memory(self, account_epoch: str) -> None:
        try:
            outcomes = self.persistence.read_all("outcomes")
            smokes = self.persistence.read_all("smoke_sessions")
        except Exception:
            return
        if not outcomes and not smokes:
            return
        self.memory.remember_from_outcome(
            trade_case_id="baseline-smoke-btcusdt-sell",
            candidate={
                "symbol": "BTCUSDT",
                "direction": "Sell",
                "strategy": "SMOKE_MOMENTUM_15M",
                "regime": "TREND_DOWN",
            },
            outcome="GOOD_PROCESS_LOSS",
            cost_labels=["fee_churn_candidate", "direction_correct_but_net_loss"],
        )
        self.persistence.append(
            "decision_deltas",
            {"seed": True, "source": "baseline_smoke", "account_epoch": account_epoch},
            account_epoch=account_epoch,
        )

    def _try_entry(self, allocator: MarginAllocator, export_root: Path, account_epoch: str) -> dict[str, Any] | None:
        if not self.session_write_enabled or not self.gate.can_write_orders():
            return None
        positions = self.writer.list_positions()
        orders = self.writer.list_open_orders()
        if positions or orders:
            with self._lock:
                self._state["duplicate_order_incidents"] += 1
            self._kill("not_flat_before_entry", KillSwitchTrigger.GATE_FAILURE)
            return None

        candidates, scan_meta = scan_dynamic_candidates(limit=8)
        self.persistence.append("universe_scans", redact_secrets(scan_meta), account_epoch=account_epoch)
        with self._lock:
            self._state["candidates_total"] += len(candidates)

        for cand in candidates:
            cdict = cand.to_dict()
            self.persistence.append("bounded_candidates", redact_secrets(cdict), account_epoch=account_epoch)
            if cand.risk_critic_verdict not in {"PASS", "WATCH"}:
                with self._lock:
                    self._state["risk_critic_blocks"] += 1
                continue

            delta = self.memory.apply(candidate=cdict, before_score=cand.candidate_score, before_verdict="ALLOW")
            with self._lock:
                self._state["decision_delta_count"] = len(self.memory.decision_deltas)
            self.persistence.append("decision_deltas", redact_secrets(delta), account_epoch=account_epoch)
            if delta.get("after_verdict") == "BLOCK":
                with self._lock:
                    self._state["mistake_guard_blocks"] += 1
                continue

            try:
                snap = self.reader.read_with_constitution()
            except Exception:
                continue
            decision = allocator.allocate(snap, requested_margin=MARGIN_PER_TRADE_CAP, open_count=0, pending_count=0)
            if decision.result != AllocationResult.ALLOCATED:
                continue

            price = cand.last_price
            if price <= 0:
                continue
            try:
                info = self.writer.fetch_instrument(cand.symbol)
                qty = self.writer.compute_qty(
                    margin_usdt=decision.margin_usdt, leverage=FIXED_LEVERAGE, price=price, info=info
                )
                tick = self.writer.tick_size(info)
            except DemoWriteError:
                continue

            if cand.direction == "Buy":
                sl_f, tp_f = price * 0.992, price * 1.008
            else:
                sl_f, tp_f = price * 1.008, price * 0.992
            sl = self.writer.format_price(sl_f, tick)
            tp = self.writer.format_price(tp_f, tick)
            fee_rate = self.writer.fetch_fee_rate(cand.symbol)
            funding = cand.funding_rate if cand.funding_status == "KNOWN" else None
            cost = evaluate_cost_gate(
                entry_price=price,
                stop_loss=_f(sl),
                take_profit=_f(tp),
                qty=_f(qty),
                side=cand.direction,
                fee_rate=fee_rate,
                funding_rate=funding,
                slippage_bps=cand.spread_bps,
            )
            self.persistence.append("cost_gates", redact_secrets(cost.to_dict()), account_epoch=account_epoch)
            if not cost.allowed:
                with self._lock:
                    self._state["cost_gate_blocks"] += 1
                continue

            if self._state["net_pnl"] <= -MAX_SESSION_NET_LOSS:
                self._kill("session_net_loss", KillSwitchTrigger.GATE_FAILURE)
                return None
            if self._state["entries_total"] >= MAX_TOTAL_ENTRY_ORDERS:
                return None

            trade_case_id = f"case-{uuid.uuid4().hex[:12]}"
            order_link_id = f"NEXUS-6H-{uuid.uuid4().hex[:12]}"[:36]
            try:
                self.writer.set_leverage(cand.symbol, FIXED_LEVERAGE)
                resp = self.writer.create_market_order(
                    symbol=cand.symbol,
                    side=cand.direction,
                    qty=qty,
                    order_link_id=order_link_id,
                    stop_loss=sl,
                    take_profit=tp,
                )
            except DemoWriteError as exc:
                self._kill(f"order_fail:{exc.code}", KillSwitchTrigger.GATE_FAILURE)
                return None

            self.gate.smoke_orders_remaining = max(0, int(self.gate.smoke_orders_remaining) - 1)
            with self._lock:
                self._state["entries_total"] += 1
            self.persistence.append(
                "orders",
                redact_secrets(
                    {
                        "request": {
                            "symbol": cand.symbol,
                            "side": cand.direction,
                            "qty": qty,
                            "sl": sl,
                            "tp": tp,
                            "margin": decision.margin_usdt,
                            "leverage": FIXED_LEVERAGE,
                            "margin_mode": MARGIN_MODE,
                            "order_link_id": order_link_id,
                        },
                        "response": resp,
                        "trade_case_id": trade_case_id,
                    }
                ),
                account_epoch=account_epoch,
            )
            pos = self._wait_fill(cand.symbol)
            if not pos:
                self._kill("no_fill", KillSwitchTrigger.GATE_FAILURE)
                return None
            ok, _, pev = self._verify_protection(cand.symbol, sl, tp)
            self.persistence.append("protection_checks", redact_secrets(pev), account_epoch=account_epoch)
            if not ok:
                with self._lock:
                    self._state["protection_incidents"] += 1
                self._force_flat(cand.symbol, str(pos.get("side") or cand.direction), str(pos.get("size") or qty))
                self._kill("unprotected", KillSwitchTrigger.PROTECTION_NOT_VERIFIED)
                return None
            return {
                "symbol": cand.symbol,
                "side": str(pos.get("side") or cand.direction),
                "qty": str(pos.get("size") or qty),
                "entry_price": _f(pos.get("avgPrice"), price),
                "sl": sl,
                "tp": tp,
                "opened_at": time.time(),
                "trade_case_id": trade_case_id,
                "candidate": cdict,
                "cost_labels": list(cost.labels),
            }
        return None

    def _supervise(self, active: dict[str, Any], export_root: Path, account_epoch: str) -> dict[str, Any] | None:
        symbol = active["symbol"]
        rows = self.writer.list_positions(symbol)
        with self._lock:
            self._state["open_position"] = bool(rows)
        if not rows:
            self._record_exit(active, "TP_SL_OR_EXTERNAL", export_root, account_epoch)
            return None
        pos = rows[0]
        if not (pos.get("stopLoss") and pos.get("takeProfit")):
            with self._lock:
                self._state["protection_incidents"] += 1
            self._force_flat(symbol, active["side"], str(pos.get("size") or active["qty"]))
            self._kill("unprotected_supervise", KillSwitchTrigger.PROTECTION_NOT_VERIFIED)
            self._record_exit(active, "UNPROTECTED_KILL", export_root, account_epoch)
            return None
        if time.time() - float(active["opened_at"]) >= MAX_HOLD_SEC:
            self._force_flat(symbol, active["side"], str(pos.get("size") or active["qty"]))
            self._record_exit(active, "TIME_STOP", export_root, account_epoch)
            return None
        if self._risk_kill(account_epoch):
            self._force_flat(symbol, active["side"], str(pos.get("size") or active["qty"]))
            self._record_exit(active, "RISK_KILL", export_root, account_epoch)
            return None
        return active

    def _record_exit(self, active: dict[str, Any], reason: str, export_root: Path, account_epoch: str) -> None:
        closed = None
        try:
            closed = self.writer.closed_pnl(active["symbol"])
        except Exception:
            closed = None
        rpnl = _f((closed or {}).get("closedPnl"), 0.0) if closed else 0.0
        entry_fee = abs(_f((closed or {}).get("openFee"), 0.0))
        exit_fee = abs(_f((closed or {}).get("closeFee"), 0.0))
        funding = abs(_f((closed or {}).get("fundingFee"), 0.0))
        gross = rpnl + entry_fee + exit_fee + funding
        process_ok = True
        try:
            after = self.reader.read_with_constitution()
            recon = self.reconciler.reconcile(
                local_positions=[],
                local_orders=[],
                remote_positions=after.open_positions,
                remote_orders=after.open_orders,
            )
            if recon.state != ReconciliationState.MATCH:
                process_ok = False
                with self._lock:
                    self._state["reconciliation_incidents"] += 1
        except Exception:
            process_ok = False

        win = rpnl >= 0
        if process_ok and win:
            outcome = "GOOD_PROCESS_WIN"
        elif process_ok and not win:
            outcome = "GOOD_PROCESS_LOSS"
        elif (not process_ok) and win:
            outcome = "BAD_PROCESS_WIN"
        else:
            outcome = "BAD_PROCESS_LOSS"

        labels = list(active.get("cost_labels") or [])
        if win is False and gross > 0:
            labels.append("direction_correct_but_net_loss")
        action = self.memory.remember_from_outcome(
            trade_case_id=active["trade_case_id"],
            candidate=active.get("candidate") or {},
            outcome=outcome,
            cost_labels=labels,
        )
        reflection = {
            "trade_case_id": active["trade_case_id"],
            "outcome": outcome,
            "exit_reason": reason,
            "net_pnl": rpnl,
            "gross_pnl": gross,
            "mistake_action": action,
            "process_ok": process_ok,
        }
        self.persistence.append("outcomes", {"outcome": outcome, **reflection}, account_epoch=account_epoch)
        self.persistence.append("reflections", reflection, account_epoch=account_epoch)
        _write_json(export_root / f"outcome_{active['trade_case_id']}.json", reflection)

        with self._lock:
            st = self._state
            st["trades_completed"] += 1
            st["gross_pnl"] += gross
            st["entry_fees"] += entry_fee
            st["exit_fees"] += exit_fee
            st["total_fees"] += entry_fee + exit_fee
            st["funding"] += funding
            st["net_pnl"] += rpnl
            st["open_position"] = False
            if win:
                st["wins"] += 1
                st["consecutive_losses"] = 0
            else:
                st["losses"] += 1
                st["consecutive_losses"] += 1
            key = {
                "GOOD_PROCESS_WIN": "good_process_wins",
                "GOOD_PROCESS_LOSS": "good_process_losses",
                "BAD_PROCESS_WIN": "bad_process_wins",
                "BAD_PROCESS_LOSS": "bad_process_losses",
            }.get(outcome)
            if key:
                st[key] += 1
            if outcome.startswith("BAD_PROCESS"):
                if st["bad_process_wins"] + st["bad_process_losses"] >= MAX_BAD_PROCESS_OUTCOMES:
                    pass  # kill checked below

        if outcome.startswith("BAD_PROCESS"):
            self._kill("bad_process", KillSwitchTrigger.GATE_FAILURE)
        elif self._state["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES:
            self._kill("consecutive_losses", KillSwitchTrigger.GATE_FAILURE)
        elif self._state["net_pnl"] <= -MAX_SESSION_NET_LOSS:
            self._kill("session_net_loss", KillSwitchTrigger.GATE_FAILURE)

    def _risk_kill(self, account_epoch: str) -> bool:
        st = self._state
        if st["net_pnl"] <= -MAX_SESSION_NET_LOSS:
            self._kill("session_net_loss", KillSwitchTrigger.GATE_FAILURE)
            return True
        if st["consecutive_losses"] >= MAX_CONSECUTIVE_LOSSES:
            self._kill("consecutive_losses", KillSwitchTrigger.GATE_FAILURE)
            return True
        bad = st["bad_process_wins"] + st["bad_process_losses"]
        if bad >= MAX_BAD_PROCESS_OUTCOMES:
            self._kill("bad_process", KillSwitchTrigger.GATE_FAILURE)
            return True
        if st["protection_incidents"] > 0:
            self._kill("unprotected", KillSwitchTrigger.PROTECTION_NOT_VERIFIED)
            return True
        return self.kill_switch.engaged

    def _kill(self, reason: str, trigger: KillSwitchTrigger) -> None:
        if not self.kill_switch.engaged:
            self.kill_switch.engage(reason, trigger=trigger)
            with self._lock:
                self._state["kill_switch_events"] += 1
                self._state["stop_reason"] = reason
        self.session_write_enabled = False
        self.gate.close_smoke_write_window()

    def _finalize(self, reason: str) -> None:
        export_root = Path(self._state.get("export_path") or (self.export_dir / f"session_{self.session_id}"))
        export_root.mkdir(parents=True, exist_ok=True)
        account_epoch = str(self._state.get("account_epoch") or "")

        # Ensure flat
        try:
            for pos in self.writer.list_positions():
                self._force_flat(str(pos.get("symbol") or ""), str(pos.get("side") or "Buy"), str(pos.get("size") or "0"))
        except Exception:
            pass

        ending_wallet = self._state.get("starting_wallet", 0.0)
        ending_equity = self._state.get("starting_equity", 0.0)
        final_pos = final_ord = -1
        try:
            after = self.reader.read_with_constitution()
            ending_wallet, ending_equity = after.wallet_balance, after.equity
            final_pos, final_ord = len(after.open_positions), len(after.open_orders)
            recon = self.reconciler.reconcile(
                local_positions=[],
                local_orders=[],
                remote_positions=after.open_positions,
                remote_orders=after.open_orders,
            )
            if recon.state != ReconciliationState.MATCH or final_pos or final_ord:
                with self._lock:
                    self._state["reconciliation_incidents"] += 1
        except Exception:
            with self._lock:
                self._state["reconciliation_incidents"] += 1

        self.session_write_enabled = False
        self.session_autonomous_enabled = False
        self.gate.close_smoke_write_window()
        if hasattr(self.approval, "close_window"):
            try:
                self.approval.close_window(reason)
            except Exception:
                pass

        rec = self._recommend()
        ended = time.time()
        summary = redact_secrets(
            {
                **{k: self._state[k] for k in self._state if k != "runtime_identity"},
                "session_ended_at": ended,
                "ending_wallet": ending_wallet,
                "ending_equity": ending_equity,
                "final_position_count": final_pos,
                "final_open_order_count": final_ord,
                "demo_autonomous_final": False,
                "exchange_write_final": False,
                "recommendation": rec,
                "next_founder_gate": "FOUNDER_GATE=DEMO_AUTONOMOUS_24H_BOUNDED_VALIDATION",
                "policy_version": POLICY_VERSION,
                "schema_version": SCHEMA_VERSION,
                "stop_reason": reason or self._state.get("stop_reason"),
                "decision_delta_count": len(self.memory.decision_deltas),
            }
        )
        with self._lock:
            self._state.update(
                {
                    "status": "COMPLETED",
                    "ended_at": ended,
                    "ending_wallet": ending_wallet,
                    "ending_equity": ending_equity,
                    "recommendation": rec,
                    "export_path": str(export_root),
                }
            )

        _write_json(export_root / "session_summary.json", summary)
        _write_json(export_root / "runtime_identity.json", self._state.get("runtime_identity") or {})
        _write_json(
            export_root / "evidence_manifest.json",
            {"files": sorted(p.name for p in export_root.rglob("*") if p.is_file()), "export_path": str(export_root)},
        )
        try:
            self.persistence.append("session_summaries", summary, account_epoch=account_epoch or None)
        except Exception:
            pass
        # Final checkpoint at 6h offset if not already
        self._checkpoint(SESSION_DURATION_SEC, export_root, account_epoch)

    def _recommend(self) -> str:
        st = self._state
        if self.kill_switch.engaged or st.get("kill_switch_events", 0) > 0:
            return _RECS[3]
        if st.get("entries_total", 0) == 0:
            return _RECS[2]
        findings = (
            st.get("bad_process_wins", 0)
            + st.get("bad_process_losses", 0)
            + st.get("protection_incidents", 0)
            + st.get("reconciliation_incidents", 0)
            + st.get("duplicate_order_incidents", 0)
        )
        if findings > 0:
            return _RECS[1]
        return _RECS[0]

    def _maybe_checkpoints(self, elapsed: float, export_root: Path, account_epoch: str) -> None:
        done = set(self._state.get("checkpoints_done") or [])
        for off in CHECKPOINT_OFFSETS_SEC:
            if off in done:
                continue
            if elapsed + 1.0 >= off:
                self._checkpoint(off, export_root, account_epoch)

    def _checkpoint(self, offset: int, export_root: Path, account_epoch: str) -> None:
        payload = redact_secrets(
            {
                "offset_sec": offset,
                "observed_at": time.time(),
                "session_id": self.session_id,
                **{k: self._state[k] for k in (
                    "entries_total", "trades_completed", "net_pnl", "candidates_total",
                    "cost_gate_blocks", "mistake_guard_blocks", "risk_critic_blocks",
                    "decision_delta_count", "open_position", "kill_switch_events",
                )},
            }
        )
        try:
            self.persistence.append("session_checkpoints", payload, account_epoch=account_epoch or None)
        except Exception:
            pass
        _write_json(export_root / "checkpoints" / f"checkpoint_{offset:05d}.json", payload)
        with self._lock:
            done = list(self._state.get("checkpoints_done") or [])
            if offset not in done:
                done.append(offset)
                self._state["checkpoints_done"] = done

    def _wait_fill(self, symbol: str, timeout_sec: int = 60) -> dict[str, Any] | None:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            rows = self.writer.list_positions(symbol)
            if rows:
                return rows[0]
            time.sleep(2)
        return None

    def _verify_protection(self, symbol: str, sl: str, tp: str) -> tuple[bool, float, dict[str, Any]]:
        start = time.time()
        deadline = start + PROTECTION_VERIFY_DEADLINE_SEC
        position: dict[str, Any] = {}
        while time.time() < deadline:
            rows = self.writer.list_positions(symbol)
            if rows:
                position = rows[0]
                if position.get("stopLoss") and position.get("takeProfit"):
                    return True, time.time() - start, {
                        "verified": True,
                        "sl": position.get("stopLoss"),
                        "tp": position.get("takeProfit"),
                        "expected_sl": sl,
                        "expected_tp": tp,
                    }
            time.sleep(0.5)
        return False, time.time() - start, {
            "verified": False,
            "sl": position.get("stopLoss"),
            "tp": position.get("takeProfit"),
            "expected_sl": sl,
            "expected_tp": tp,
        }

    def _force_flat(self, symbol: str, side: str, qty: str) -> None:
        if not symbol or _f(qty) <= 0:
            return
        try:
            self.writer.close_reduce_only(
                symbol=symbol,
                side=side,
                qty=qty,
                order_link_id=f"NEXUS-6H-CLS-{uuid.uuid4().hex[:10]}"[:36],
            )
        except Exception:
            pass
