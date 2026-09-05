"""Shared BoundedAutonomousSessionEngine for 6H V2 and 12H V3.

Policy/config differ; trading loop components are shared.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
from backend.nexus_demo_execution.session_mistake_memory import SessionMistakeMemory
from backend.nexus_demo_execution.session_policy import BoundedSessionPolicy, policy_6h_v2
from backend.nexus_demo_execution.v2_session_recovery import SessionRecoverySnapshot, SessionRecoveryStore

_TRUE = {"1", "true", "yes", "on"}


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
class BoundedAutonomousSessionEngine:
    """Bounded autonomous demo validation — smoke write window only; never DEMO_AUTONOMOUS_ENABLED."""

    gate: Any
    reader: Any
    persistence: Any
    epoch_tracker: Any
    kill_switch: KillSwitch
    writer: DemoWriteClient
    approval: Any
    export_dir: Path
    data_root: Path
    policy: BoundedSessionPolicy = field(default_factory=policy_6h_v2)
    reconciler: DemoReconciler = field(default_factory=DemoReconciler)
    memory: SessionMistakeMemory = field(default_factory=SessionMistakeMemory)
    source_6h_session_id: str = ""
    leader_token: str = ""
    _recovery: SessionRecoveryStore | None = field(default=None, repr=False)

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
            "risk_critic_pass_total": 0,
            "mistake_guard_blocks": 0,
            "mistake_guard_pass_total": 0,
            "cost_gate_evaluated_total": 0,
            "cost_gate_pass_total": 0,
            "cost_gate_blocks": 0,
            "cost_gate_block_reason_distribution": {},
            "pre_cost_drop_total": 0,
            "pre_cost_drop_reason_distribution": {},
            "valid_intent_total": 0,
            "order_intent_total": 0,
            "exchange_write_attempt_total": 0,
            "exchange_write_authorized_total": 0,
            "exchange_write_blocked_total": 0,
            "exchange_request_total": 0,
            "exchange_accepted_total": 0,
            "exchange_rejected_total": 0,
            "last_exchange_rejection_code": "",
            "last_exchange_rejection_reason": "",
            "fills_total": 0,
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
            "deadline_ts": None,
            "automatic_extension": False,
            "source_6h_session_id": "",
            "controller_type": "FULL_AUTONOMOUS_ENGINE",
            "market_cycles_total": 0,
            "universe_scans_total": 0,
            "geometry_evaluated_total": 0,
            "geometry_complete_total": 0,
            "geometry_missing_total": 0,
            "reflections_total": 0,
            "learning_proposals_total": 0,
            "completed_outcomes": 0,
            "cost_gate_block_total": 0,
            "pre_cost_silent_drop_total": 0,
            "pre_cost_silent_drop_reason_distribution": {},
            "risk_critic_evaluated_total": 0,
            "risk_critic_block_total": 0,
            "mistake_guard_evaluated_total": 0,
            "mistake_guard_block_total": 0,
            "instrument_qty_error_distribution": {},
            "instrument_qty_error_by_symbol": {},
            "completed_trades_total": 0,
            "duplicate_intent_count": 0,
            "duplicate_entry_order_count": 0,
            "protection_incident_count": 0,
            "reconciliation_incident_count": 0,
            "similar_case_matches": 0,
            "slippage": None,
            "maximum_drawdown": None,
            "observability": {
                "completed_trades_total": "ZERO_WITH_EVIDENCE",
                "slippage": "NOT_APPLICABLE",
                "maximum_drawdown": "NOT_APPLICABLE",
                "duplicate_intent_count": "ZERO_WITH_EVIDENCE",
                "duplicate_entry_order_count": "ZERO_WITH_EVIDENCE",
                "protection_incident_count": "ZERO_WITH_EVIDENCE",
                "reconciliation_incident_count": "ZERO_WITH_EVIDENCE",
                "leader_lock_status": "AVAILABLE",
                "similar_case_matches": "ZERO_WITH_EVIDENCE",
            },
            "leader_lock_status": "HELD",
        }

    def _founder_start_authorization(self, gate_env: str) -> dict[str, Any] | None:
        """Founder start authorization for the LEGACY (non-certified) engine:
        requires the founder-approval env (e.g. FOUNDER_6H_APPROVED=true). Returns
        an error dict to block, or None to allow.

        Overridable hook: certified runtimes replace ONLY this authorization step
        with signed one-shot authorization; the surrounding gate-label / kill-switch
        / session-id / thread-spawn logic is unchanged. Legacy behavior here is
        intentionally byte-for-byte the original env check."""
        if not _env_true(self.policy.founder_approval_env):
            return redact_secrets(
                {"ok": False, "reason": "founder_not_approved", "env": self.policy.founder_approval_env, "got_gate": gate_env}
            )
        return None

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return redact_secrets({"ok": False, "reason": "already_running", **self.status()})
            _load_founder_gate_file()
            gate_env = (os.environ.get("FOUNDER_GATE") or "").strip()
            if gate_env not in self.policy.allowed_gates:
                return redact_secrets(
                    {
                        "ok": False,
                        "reason": "founder_gate_mismatch",
                        "expected": self.policy.session_gate_name,
                        "got": gate_env or "MISSING",
                        "founder_6h_approved": _env_true("FOUNDER_6H_APPROVED"),
                    }
                )
            founder_block = self._founder_start_authorization(gate_env)
            if founder_block is not None:
                return founder_block
            if self.kill_switch.engaged:
                return redact_secrets({"ok": False, "reason": "kill_switch_engaged"})

            prior_session_id = (self.session_id or "").strip()
            source_6h = self.source_6h_session_id
            self._reset_counters()
            self._stop.clear()
            if prior_session_id.startswith(self.policy.session_id_prefix):
                self.session_id = prior_session_id
            else:
                utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                nonce = uuid.uuid4().hex[:8]
                self.session_id = f"{self.policy.session_id_prefix}-{utc}-{nonce}"
            self.source_6h_session_id = source_6h
            self._state["session_id"] = self.session_id
            self._state["source_6h_session_id"] = source_6h
            self._state["status"] = "STARTING"
            self._state["policy_version"] = self.policy.policy_version
            self._state["founder_gate"] = gate_env
            self._state["controller_type"] = self.policy.controller_type
            self._thread = threading.Thread(target=self._safe_run, name=self.policy.thread_name, daemon=True)
            self._thread.start()
            return redact_secrets({"ok": True, "session_id": self.session_id, "status": "STARTING"})

    def stop(self, reason: str = "OPERATOR_STOP") -> None:
        """Stop session loop. Ordinary deadline finalize must NOT engage Kill Switch."""
        reason = (reason or "OPERATOR_STOP").strip() or "OPERATOR_STOP"
        self._stop.set()
        with self._lock:
            self._state["stop_reason"] = reason
            if reason.upper().startswith("DEADLINE_FINALIZE"):
                self._state["status"] = "FINALIZING"
        # Deadline / orderly finalize: close write window without Kill Switch.
        if reason.upper().startswith("DEADLINE_FINALIZE"):
            self.session_write_enabled = False
            self.session_autonomous_enabled = False
            try:
                self.gate.close_smoke_write_window()
            except Exception:
                pass
            return
        if reason and not self.kill_switch.engaged:
            self.kill_switch.engage(reason, trigger=KillSwitchTrigger.OPERATOR_STOP)
            with self._lock:
                self._state["kill_switch_events"] += 1

    def status(self) -> dict[str, Any]:
        with self._lock:
            snap = dict(self._state)
            obs = dict(snap.get("observability") or {})
            # Keep aliases synchronized without converting missing → zero silently.
            snap["completed_trades_total"] = int(snap.get("trades_completed") or 0)
            snap["duplicate_entry_order_count"] = int(snap.get("duplicate_order_incidents") or 0)
            snap["duplicate_intent_count"] = int(snap.get("duplicate_intent_count") or snap.get("duplicate_order_incidents") or 0)
            snap["protection_incident_count"] = int(snap.get("protection_incidents") or 0)
            snap["reconciliation_incident_count"] = int(snap.get("reconciliation_incidents") or 0)
            if int(snap.get("entries_total") or 0) == 0:
                obs.setdefault("slippage", "NOT_APPLICABLE")
                obs.setdefault("maximum_drawdown", "NOT_APPLICABLE")
                obs.setdefault("completed_trades_total", "ZERO_WITH_EVIDENCE")
            obs.setdefault("duplicate_intent_count", "ZERO_WITH_EVIDENCE")
            obs.setdefault("duplicate_entry_order_count", "ZERO_WITH_EVIDENCE")
            obs.setdefault("protection_incident_count", "ZERO_WITH_EVIDENCE")
            obs.setdefault("reconciliation_incident_count", "ZERO_WITH_EVIDENCE")
            obs.setdefault("similar_case_matches", "ZERO_WITH_EVIDENCE")
            obs["leader_lock_status"] = "AVAILABLE" if snap.get("leader_lock_status") else "UNKNOWN"
            snap["observability"] = obs
            snap.update(
                {
                    "session_write_enabled": self.session_write_enabled,
                    "session_autonomous_enabled": self.session_autonomous_enabled,
                    "session_write_window_open": bool(
                        self.session_write_enabled or getattr(self.gate, "smoke_write_window_open", False)
                    ),
                    "effective_demo_write_authorized": bool(
                        self.session_write_enabled and getattr(self.gate, "smoke_write_window_open", False)
                    ),
                    "gate_autonomous_mode": getattr(
                        getattr(self.gate, "autonomous_mode", None), "value", "DEMO_AUTONOMOUS_DISABLED"
                    ),
                    "smoke_write_window_open": bool(getattr(self.gate, "smoke_write_window_open", False)),
                    "smoke_orders_remaining": int(getattr(self.gate, "smoke_orders_remaining", 0) or 0),
                    "kill_switch": self.kill_switch.snapshot(),
                    "mistake_memory": self.memory.summary(),
                    "thread_alive": bool(self._thread and self._thread.is_alive()),
                    "controller_type": self.policy.controller_type,
                    "bounded_full_engine_ready": True,
                    "authorization_scope": (
                        "DEMO_12H_V3_SESSION_ONLY" if self.policy.label == "12H_V3" else "DEMO_6H_V2_SESSION_ONLY"
                    ),
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
            policy_version=self.policy.policy_version,
            schema_version=self.policy.schema_version,
            service_name=SERVICE_NAME,
            data_root=self.data_root,
        )
        started = time.time()
        deadline = started + self.policy.session_duration_sec
        with self._lock:
            self._state.update(
                {
                    "status": "RUNNING",
                    "started_at": started,
                    "deadline_ts": deadline,
                    "automatic_extension": False,
                    "account_epoch": account_epoch,
                    "source_6h_session_id": self.source_6h_session_id,
                    "starting_wallet": snap.wallet_balance,
                    "starting_equity": snap.equity,
                    "runtime_identity": identity.to_dict(),
                    "export_path": str(export_root),
                    "controller_type": self.policy.controller_type,
                    "policy_version": self.policy.policy_version,
                    "schema_version": self.policy.schema_version,
                }
            )
        self._persist_recovery()

        self.session_autonomous_enabled = True
        self.session_write_enabled = True
        self.gate.open_smoke_write_window(max_orders=self.policy.max_total_entry_orders)
        # Do NOT advance SafetyGateStage to DEMO_AUTONOMOUS_ENABLED.
        self._seed_baseline_memory(account_epoch)
        self._checkpoint(0, export_root, account_epoch)

        active: dict[str, Any] | None = None
        allocator = MarginAllocator(
            min_margin=self.policy.margin_per_trade,
            max_margin=self.policy.margin_per_trade,
            max_open=1,
            max_pending=1,
            fixed_leverage=self.policy.leverage,
        )

        while not self._stop.is_set() and time.time() < deadline and not self.kill_switch.engaged:
            elapsed = time.time() - started
            self._maybe_checkpoints(elapsed, export_root, account_epoch)

            if active:
                active = self._supervise(active, export_root, account_epoch)
                if active is None and self._state["entries_total"] >= self.policy.max_total_entry_orders:
                    break
                if active:
                    time.sleep(self.policy.supervisor_poll_sec)
                    continue

            if self._state["entries_total"] >= self.policy.max_total_entry_orders:
                break
            if self._risk_kill(account_epoch):
                break

            active = self._try_entry(allocator, export_root, account_epoch)
            self._persist_recovery()
            if active is None:
                time.sleep(self.policy.cycle_interval_sec)

        if active:
            self._force_flat(active.get("symbol", ""), active.get("side", "Buy"), str(active.get("qty") or "0"))
            self._record_exit(active, "SESSION_END", export_root, account_epoch)

        # Ordinary deadline completion uses DEADLINE_FINALIZE (not Kill Switch / OPERATOR_STOP).
        if time.time() >= deadline:
            finalize_reason = "DEADLINE_FINALIZE"
        else:
            finalize_reason = str(self._state.get("stop_reason") or "completed")
        self._finalize(finalize_reason)

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
                self._state["duplicate_entry_order_count"] = int(
                    self._state.get("duplicate_order_incidents") or 0
                )
            self._kill("not_flat_before_entry", KillSwitchTrigger.GATE_FAILURE)
            return None

        candidates, scan_meta = scan_dynamic_candidates(limit=8)
        self.persistence.append("universe_scans", redact_secrets(scan_meta), account_epoch=account_epoch)
        with self._lock:
            self._state["candidates_total"] += len(candidates)
            self._state["universe_scans_total"] += 1
            self._state["market_cycles_total"] += 1

        for cand in candidates:
            cdict = cand.to_dict()
            self.persistence.append("bounded_candidates", redact_secrets(cdict), account_epoch=account_epoch)
            if cand.risk_critic_verdict not in {"PASS", "WATCH"}:
                with self._lock:
                    self._state["risk_critic_blocks"] += 1
                    self._state["risk_critic_block_total"] += 1
                    self._state["risk_critic_evaluated_total"] += 1
                continue
            with self._lock:
                self._state["risk_critic_pass_total"] += 1
                self._state["risk_critic_evaluated_total"] += 1

            delta = self.memory.apply(candidate=cdict, before_score=cand.candidate_score, before_verdict="ALLOW")
            with self._lock:
                self._state["decision_delta_count"] = len(self.memory.decision_deltas)
            self.persistence.append("decision_deltas", redact_secrets(delta), account_epoch=account_epoch)
            if delta.get("after_verdict") == "BLOCK":
                with self._lock:
                    self._state["mistake_guard_blocks"] += 1
                    self._state["mistake_guard_block_total"] += 1
                    self._state["mistake_guard_evaluated_total"] += 1
                continue
            with self._lock:
                self._state["mistake_guard_pass_total"] += 1
                self._state["mistake_guard_evaluated_total"] += 1

            try:
                snap = self.reader.read_with_constitution()
            except Exception:
                with self._lock:
                    self._state["pre_cost_drop_total"] += 1
                    self._state["pre_cost_silent_drop_total"] += 1
                    dist = dict(self._state.get("pre_cost_drop_reason_distribution") or {})
                    dist["READER_EXCEPTION"] = int(dist.get("READER_EXCEPTION") or 0) + 1
                    self._state["pre_cost_drop_reason_distribution"] = dist
                    self._state["pre_cost_silent_drop_reason_distribution"] = dist
                continue
            decision = allocator.allocate(snap, requested_margin=self.policy.margin_per_trade, open_count=0, pending_count=0)
            if decision.result != AllocationResult.ALLOCATED:
                with self._lock:
                    self._state["pre_cost_drop_total"] += 1
                    dist = dict(self._state.get("pre_cost_drop_reason_distribution") or {})
                    dist["ALLOCATOR_BLOCK"] = int(dist.get("ALLOCATOR_BLOCK") or 0) + 1
                    self._state["pre_cost_drop_reason_distribution"] = dist
                continue

            price = cand.last_price
            if price <= 0:
                with self._lock:
                    self._state["pre_cost_drop_total"] += 1
                    dist = dict(self._state.get("pre_cost_drop_reason_distribution") or {})
                    dist["PRICE_INVALID"] = int(dist.get("PRICE_INVALID") or 0) + 1
                    self._state["pre_cost_drop_reason_distribution"] = dist
                continue
            try:
                info = self.writer.fetch_instrument(cand.symbol)
                qty = self.writer.compute_qty(
                    margin_usdt=decision.margin_usdt, leverage=self.policy.leverage, price=price, info=info
                )
                tick = self.writer.tick_size(info)
            except DemoWriteError as exc:
                from backend.nexus_demo_execution.instrument_qty_classify import classify_from_exc

                sub = classify_from_exc(exc)
                with self._lock:
                    self._state["pre_cost_drop_total"] += 1
                    self._state["pre_cost_silent_drop_total"] = int(
                        self._state.get("pre_cost_silent_drop_total") or 0
                    ) + 1
                    dist = dict(self._state.get("pre_cost_drop_reason_distribution") or {})
                    dist["INSTRUMENT_OR_QTY_ERROR"] = int(dist.get("INSTRUMENT_OR_QTY_ERROR") or 0) + 1
                    self._state["pre_cost_drop_reason_distribution"] = dist
                    sub_dist = dict(self._state.get("instrument_qty_error_distribution") or {})
                    sub_dist[sub] = int(sub_dist.get(sub) or 0) + 1
                    self._state["instrument_qty_error_distribution"] = sub_dist
                    by_sym = dict(self._state.get("instrument_qty_error_by_symbol") or {})
                    sym_bucket = dict(by_sym.get(cand.symbol) or {})
                    sym_bucket[sub] = int(sym_bucket.get(sub) or 0) + 1
                    by_sym[cand.symbol] = sym_bucket
                    self._state["instrument_qty_error_by_symbol"] = by_sym
                    silent = dict(self._state.get("pre_cost_silent_drop_reason_distribution") or {})
                    silent[sub] = int(silent.get(sub) or 0) + 1
                    self._state["pre_cost_silent_drop_reason_distribution"] = silent
                continue

            if cand.direction == "Buy":
                sl_f, tp_f = price * 0.992, price * 1.008
            else:
                sl_f, tp_f = price * 1.008, price * 0.992
            sl = self.writer.format_price(sl_f, tick)
            tp = self.writer.format_price(tp_f, tick)
            fee_quote = self.writer.fetch_fee_rate_quote(cand.symbol)
            funding = cand.funding_rate if cand.funding_status == "KNOWN" else None
            cost = evaluate_cost_gate(
                entry_price=price,
                stop_loss=_f(sl),
                take_profit=_f(tp),
                qty=_f(qty),
                side=cand.direction,
                fee_rate=fee_quote.usable_taker,
                funding_rate=funding,
                slippage_bps=cand.spread_bps,
                fee_meta=fee_quote.to_dict(),
            )
            self.persistence.append("cost_gates", redact_secrets(cost.to_dict()), account_epoch=account_epoch)
            with self._lock:
                self._state["cost_gate_evaluated_total"] += 1
            if not cost.allowed:
                with self._lock:
                    self._state["cost_gate_blocks"] += 1
                    self._state["cost_gate_block_total"] += 1
                    dist = dict(self._state.get("cost_gate_block_reason_distribution") or {})
                    reason = str(cost.reason or "UNKNOWN")
                    dist[reason] = int(dist.get(reason) or 0) + 1
                    self._state["cost_gate_block_reason_distribution"] = dist
                    self._state["geometry_evaluated_total"] += 1
                    self._state["geometry_complete_total"] += 1
                continue
            with self._lock:
                self._state["cost_gate_pass_total"] += 1
                self._state["valid_intent_total"] += 1
                self._state["geometry_evaluated_total"] += 1
                self._state["geometry_complete_total"] += 1

            if self._state["net_pnl"] <= -self.policy.max_session_net_loss:
                self._kill("session_net_loss", KillSwitchTrigger.GATE_FAILURE)
                return None
            if self._state["entries_total"] >= self.policy.max_total_entry_orders:
                return None

            trade_case_id = f"case-{uuid.uuid4().hex[:12]}"
            order_link_id = f"NEXUS-{self.policy.label}-{uuid.uuid4().hex[:10]}"[:36]
            with self._lock:
                self._state["order_intent_total"] += 1
                self._state["exchange_write_attempt_total"] += 1
                self._state["exchange_request_total"] += 1
            try:
                self.writer.set_leverage(cand.symbol, self.policy.leverage)
                resp = self.writer.create_market_order(
                    symbol=cand.symbol,
                    side=cand.direction,
                    qty=qty,
                    order_link_id=order_link_id,
                    stop_loss=sl,
                    take_profit=tp,
                )
            except DemoWriteError as exc:
                with self._lock:
                    self._state["exchange_rejected_total"] += 1
                    self._state["last_exchange_rejection_code"] = str(exc.code)
                    self._state["last_exchange_rejection_reason"] = str(exc.detail or "")[:200]
                self._kill(f"order_fail:{exc.code}", KillSwitchTrigger.GATE_FAILURE)
                return None
            with self._lock:
                self._state["exchange_accepted_total"] += 1
                self._state["exchange_write_authorized_total"] += 1

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
                            "leverage": self.policy.leverage,
                            "margin_mode": self.policy.margin_mode,
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
            with self._lock:
                self._state["fills_total"] += 1
            ok, _, pev = self._verify_protection(cand.symbol, sl, tp)
            self.persistence.append("protection_checks", redact_secrets(pev), account_epoch=account_epoch)
            if not ok:
                with self._lock:
                    self._state["protection_incidents"] += 1
                    self._state["protection_incident_count"] = int(self._state.get("protection_incidents") or 0)
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
        if time.time() - float(active["opened_at"]) >= self.policy.max_hold_sec:
            self._force_flat(symbol, active["side"], str(pos.get("size") or active["qty"]))
            self._record_exit(active, "TIME_STOP", export_root, account_epoch)
            return None
        if self._risk_kill(account_epoch):
            self._force_flat(symbol, active["side"], str(pos.get("size") or active["qty"]))
            self._record_exit(active, "RISK_KILL", export_root, account_epoch)
            return None
        return active

    def _record_exit(self, active: dict[str, Any], reason: str, export_root: Path, account_epoch: str) -> None:
        from backend.nexus_demo_execution.pnl_reconcile import reconcile_via_writer

        pnl = reconcile_via_writer(self.writer, active["symbol"])
        # Session risk accounting: only accumulate when status is AVAILABLE/DERIVED.
        net_known = pnl.get("net_pnl_status") in {"AVAILABLE", "DERIVED"} and pnl.get("net_pnl") is not None
        rpnl = float(pnl["net_pnl"]) if net_known else None
        entry_fee = float(pnl["entry_fee"]) if pnl.get("entry_fee") is not None else None
        exit_fee = float(pnl["exit_fee"]) if pnl.get("exit_fee") is not None else None
        funding = float(pnl["funding"]) if pnl.get("funding") is not None else None
        gross = float(pnl["gross_pnl"]) if pnl.get("gross_pnl") is not None else None
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
                    self._state["reconciliation_incident_count"] = int(
                        self._state.get("reconciliation_incidents") or 0
                    )
        except Exception:
            process_ok = False

        # Unknown net PnL is treated as process defect (do not fake win/loss zeros).
        if not net_known:
            process_ok = False
            win = False
        else:
            win = float(rpnl) >= 0
        if process_ok and win:
            outcome = "GOOD_PROCESS_WIN"
        elif process_ok and not win:
            outcome = "GOOD_PROCESS_LOSS"
        elif (not process_ok) and win:
            outcome = "BAD_PROCESS_WIN"
        else:
            outcome = "BAD_PROCESS_LOSS"

        labels = list(active.get("cost_labels") or [])
        if win is False and gross is not None and gross > 0 and net_known and float(rpnl) < 0:
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
            "net_pnl": pnl.get("net_pnl"),
            "gross_pnl": pnl.get("gross_pnl"),
            "entry_fee": pnl.get("entry_fee"),
            "exit_fee": pnl.get("exit_fee"),
            "total_fees": pnl.get("total_fees"),
            "funding": pnl.get("funding"),
            "fee_source": pnl.get("fee_source"),
            "actual_fees_status": pnl.get("actual_fees_status"),
            "net_pnl_status": pnl.get("net_pnl_status"),
            "pnl_availability_reason": pnl.get("availability_reason"),
            "learning_status": "PROPOSED",
            "mistake_action": action,
            "process_ok": process_ok,
        }
        self.persistence.append("outcomes", {"outcome": outcome, **reflection}, account_epoch=account_epoch)
        self.persistence.append("reflections", reflection, account_epoch=account_epoch)
        with self._lock:
            self._state["reflections_total"] += 1
            self._state["learning_proposals_total"] += 1
            self._state["completed_outcomes"] += 1
        _write_json(export_root / f"outcome_{active['trade_case_id']}.json", reflection)

        with self._lock:
            st = self._state
            st["trades_completed"] += 1
            st["completed_trades_total"] = int(st.get("trades_completed") or 0)
            obs = dict(st.get("observability") or {})
            obs["completed_trades_total"] = "AVAILABLE"
            obs["slippage"] = "AVAILABLE" if st.get("slippage") is not None else "UNKNOWN"
            obs["maximum_drawdown"] = "AVAILABLE" if st.get("maximum_drawdown") is not None else "UNKNOWN"
            st["observability"] = obs
            if gross is not None:
                st["gross_pnl"] += gross
            if entry_fee is not None:
                st["entry_fees"] += entry_fee
            if exit_fee is not None:
                st["exit_fees"] += exit_fee
            if entry_fee is not None or exit_fee is not None:
                st["total_fees"] += float(entry_fee or 0.0) + float(exit_fee or 0.0)
            if funding is not None:
                st["funding"] += funding
            if net_known and rpnl is not None:
                st["net_pnl"] += float(rpnl)
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
                if st["bad_process_wins"] + st["bad_process_losses"] >= self.policy.max_bad_process_outcomes:
                    pass  # kill checked below

        if outcome.startswith("BAD_PROCESS"):
            self._kill("bad_process", KillSwitchTrigger.GATE_FAILURE)
        elif self._state["consecutive_losses"] >= self.policy.max_consecutive_losses:
            self._kill("consecutive_losses", KillSwitchTrigger.GATE_FAILURE)
        elif self._state["net_pnl"] <= -self.policy.max_session_net_loss:
            self._kill("session_net_loss", KillSwitchTrigger.GATE_FAILURE)

    def _risk_kill(self, account_epoch: str) -> bool:
        st = self._state
        if st["net_pnl"] <= -self.policy.max_session_net_loss:
            self._kill("session_net_loss", KillSwitchTrigger.GATE_FAILURE)
            return True
        if st["consecutive_losses"] >= self.policy.max_consecutive_losses:
            self._kill("consecutive_losses", KillSwitchTrigger.GATE_FAILURE)
            return True
        bad = st["bad_process_wins"] + st["bad_process_losses"]
        if bad >= self.policy.max_bad_process_outcomes:
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

    def _next_gate_metadata(self) -> dict[str, Any]:
        return {
            "next_machine_gate": (
                "NONE" if self.policy.label == "12H_V3" else "DEMO_AUTONOMOUS_12H_V3_EXTENDED_OBSERVATION"
            ),
            "next_founder_gate": "FOUNDER_GATE=DEMO_AUTONOMOUS_24H_BOUNDED_VALIDATION",
            "next_founder_gate_approved": False,
            "24H_GATE_APPROVED": False,
        }

    def _finalize(self, reason: str) -> None:
        from backend.nexus_demo_execution.count_semantics import reconcile_flat

        export_root = Path(self._state.get("export_path") or (self.export_dir / f"session_{self.session_id}"))
        export_root.mkdir(parents=True, exist_ok=True)
        account_epoch = str(self._state.get("account_epoch") or "")
        with self._lock:
            self._state["status"] = "FINALIZING"
            if reason and str(reason).upper().startswith("DEADLINE"):
                self._state["stop_reason"] = reason

        # Ensure flat
        try:
            for pos in self.writer.list_positions():
                self._force_flat(str(pos.get("symbol") or ""), str(pos.get("side") or "Buy"), str(pos.get("size") or "0"))
        except Exception:
            pass

        ending_wallet = self._state.get("starting_wallet", 0.0)
        ending_equity = self._state.get("starting_equity", 0.0)
        final_pos: int | None = None
        final_ord: int | None = None
        recon_final = "UNKNOWN"
        try:
            after = self.reader.read_with_constitution()
            ending_wallet, ending_equity = after.wallet_balance, after.equity
            final_pos = len(after.open_positions)
            final_ord = len(after.open_orders)
            recon = self.reconciler.reconcile(
                local_positions=[],
                local_orders=[],
                remote_positions=after.open_positions,
                remote_orders=after.open_orders,
            )
            recon_final = reconcile_flat(final_pos, final_ord)
            if recon.state != ReconciliationState.MATCH or (final_pos or final_ord):
                with self._lock:
                    self._state["reconciliation_incidents"] += 1
                    self._state["reconciliation_incident_count"] = int(
                        self._state.get("reconciliation_incidents") or 0
                    )
                    if recon_final == "MATCH" and recon.state != ReconciliationState.MATCH:
                        recon_final = "MISMATCH"
        except Exception:
            with self._lock:
                self._state["reconciliation_incidents"] += 1
                self._state["reconciliation_incident_count"] = int(
                    self._state.get("reconciliation_incidents") or 0
                )
            final_pos = None
            final_ord = None
            recon_final = "UNKNOWN"

        self.session_write_enabled = False
        self.session_autonomous_enabled = False
        self.gate.close_smoke_write_window()
        if hasattr(self.approval, "close_window"):
            try:
                self.approval.close_window(reason)
            except Exception:
                pass

        with self._lock:
            self._state["completed_trades_total"] = int(self._state.get("trades_completed") or 0)
            self._state["duplicate_entry_order_count"] = int(self._state.get("duplicate_order_incidents") or 0)
            self._state["duplicate_intent_count"] = int(self._state.get("duplicate_order_incidents") or 0)
            self._state["protection_incident_count"] = int(self._state.get("protection_incidents") or 0)
            self._state["reconciliation_incident_count"] = int(self._state.get("reconciliation_incidents") or 0)
            # Zero-entry session: slippage/drawdown are N/A, not silent zeros.
            obs = dict(self._state.get("observability") or {})
            if int(self._state.get("entries_total") or 0) == 0:
                obs["slippage"] = "NOT_APPLICABLE"
                obs["maximum_drawdown"] = "NOT_APPLICABLE"
                obs["completed_trades_total"] = "ZERO_WITH_EVIDENCE"
            self._state["observability"] = obs

        rec = self._recommend()
        ended = time.time()
        # Ordinary deadline completion is COMPLETED, not KILLED.
        terminal = "COMPLETED"
        if self.kill_switch.engaged and not str(self._state.get("stop_reason") or "").upper().startswith(
            "DEADLINE_FINALIZE"
        ):
            terminal = "KILLED"
        summary = redact_secrets(
            {
                **{k: self._state[k] for k in self._state if k != "runtime_identity"},
                "session_ended_at": ended,
                "ending_wallet": ending_wallet,
                "ending_equity": ending_equity,
                "final_position_count": final_pos,
                "final_open_order_count": final_ord,
                "position_count_final": final_pos,
                "open_order_count_final": final_ord,
                "reconciliation_final": recon_final,
                "demo_autonomous_final": False,
                "exchange_write_final": False,
                "recommendation": rec,
                **self._next_gate_metadata(),
                "policy_version": self.policy.policy_version,
                "schema_version": self.policy.schema_version,
                "stop_reason": reason or self._state.get("stop_reason"),
                "decision_delta_count": len(self.memory.decision_deltas),
            }
        )
        with self._lock:
            self._state.update(
                {
                    "status": terminal,
                    "ended_at": ended,
                    "ending_wallet": ending_wallet,
                    "ending_equity": ending_equity,
                    "recommendation": rec,
                    "export_path": str(export_root),
                    "position_count_final": final_pos,
                    "open_order_count_final": final_ord,
                    "reconciliation_final": recon_final,
                    "session_write_enabled": False,
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
        self._checkpoint(self.policy.session_duration_sec, export_root, account_epoch)

    def _recommend(self) -> str:
        st = self._state
        recs = self.policy.recommendations
        failed = next((r for r in recs if r.endswith("_FAILED")), recs[-1])
        inconclusive = next((r for r in recs if "INCONCLUSIVE" in r), failed)
        pass_findings = next((r for r in recs if "PASS_WITH_FINDINGS" in r), failed)
        passed = next((r for r in recs if r.endswith("_PASS")), failed)
        stop_reason = str(st.get("stop_reason") or "")
        # Deadline finalize must not be classified as Kill Switch failure.
        if stop_reason.upper().startswith("DEADLINE_FINALIZE"):
            if st.get("entries_total", 0) == 0:
                return inconclusive
        elif self.kill_switch.engaged or st.get("kill_switch_events", 0) > 0:
            return failed
        findings = (
            st.get("bad_process_wins", 0)
            + st.get("bad_process_losses", 0)
            + st.get("protection_incidents", 0)
            + st.get("reconciliation_incidents", 0)
            + st.get("duplicate_order_incidents", 0)
        )
        if st.get("entries_total", 0) == 0:
            if findings == 0:
                return inconclusive
            return failed
        if findings > 0:
            return pass_findings
        return passed

    def _maybe_checkpoints(self, elapsed: float, export_root: Path, account_epoch: str) -> None:
        done = set(self._state.get("checkpoints_done") or [])
        for off in self.policy.checkpoint_offsets_sec:
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


    def _persist_recovery(self) -> None:
        try:
            if self._recovery is None:
                self._recovery = SessionRecoveryStore(self.data_root / "artifacts" / "session_recovery" / self.policy.label)
            token = self.leader_token or f"leader-{self.session_id}"
            self.leader_token = token
            self._recovery.acquire(token, session_id=self.session_id)
            st = self._state
            snap = SessionRecoverySnapshot(
                session_id=self.session_id,
                policy_version=self.policy.policy_version,
                state=str(st.get("status") or "RUNNING"),
                deadline_ts=float(st.get("deadline_ts") or 0.0),
                entries_total=int(st.get("entries_total") or 0),
                completed_trades=int(st.get("trades_completed") or 0),
                consecutive_losses=int(st.get("consecutive_losses") or 0),
                bad_process_outcomes=int(st.get("bad_process_wins") or 0) + int(st.get("bad_process_losses") or 0),
                session_net_pnl=float(st.get("net_pnl") or 0.0),
                write_window_open=bool(self.session_write_enabled),
                leader_token=token,
            )
            self._recovery.save(snap)
            # Also persist epoch tracker if supported.
            if hasattr(self.epoch_tracker, "persist"):
                self.epoch_tracker.persist(self.data_root)
        except Exception:
            pass

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
        deadline = start + self.policy.protection_verify_deadline_sec
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
                order_link_id=f"NEXUS-{self.policy.label}-CLS-{uuid.uuid4().hex[:8]}"[:36],
            )
        except Exception:
            pass
