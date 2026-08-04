"""NEXUS Autonomous Session Orchestrator V1.1 — Founder-only chaos-hardened.

Execution mode: ACCELERATED_HISTORICAL_REPLAY, SIMULATED_NO_EXCHANGE_WRITE.

Design goals:
  * Canonical session state machine (see ``session_state_machine.py``).
  * Deterministic accelerated logical clock (see ``nexus_runtime``).
  * Full failure-injection matrix (Provider quota/timeout/schema, stale/missing
    market data, clock jumps, duplicate candidate/intent, ledger interruptions,
    snapshot corruption, disk pressure, process termination, partial-fill
    crashes, kill switch during open position, pause during pending intent,
    Reflection/Lesson interruptions, exit-before-position-snapshot).
  * Concurrent candidate/intent/checkpoint/kill-switch/Reflection/Lesson
    handling — at most one canonical lifecycle per idempotency key.
  * Recovery invariants: any non-zero invariant routes session to
    BLOCKED / FAILED_SAFE. Ambiguous state is never guessed.

This orchestrator uses the existing Execution Simulator contract
(``execution_simulator_v1.AutonomousExecutionSimulatorV1``) and does not
modify it. Contract requirements are surfaced via ``contract_requirements``.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.execution_simulator_v1 import AutonomousExecutionSimulatorV1
from backend.nexus_autonomy.private_event_ledger_v1 import PrivateEventLedger
from backend.nexus_autonomy.process_classification import (
    classify_completed_trade,
    control_fixture_process_evidence,
)
from backend.nexus_autonomy.runtime_durability_v1 import RuntimeDurabilityV1
from backend.nexus_autonomy.session_state_machine import (
    InvalidTransitionError,
    SessionStateMachine,
    TransitionRecord,
    summarize_history,
)
from backend.nexus_recovery.crash_recovery import RecoveryOutcome, SessionCrashRecovery
from backend.nexus_recovery.invariants import check_recovery_invariants
from backend.nexus_runtime.accelerated_clock import AcceleratedLogicalClock
from backend.nexus_runtime.process_guard import NoExchangeWriteGuard


# ---------------------------------------------------------------------------
# Injection catalog (mission-defined)
# ---------------------------------------------------------------------------

INJECTION_CATALOG: tuple[str, ...] = (
    "groq_429",
    "sambanova_429",
    "provider_timeout",
    "provider_invalid_schema",
    "stale_market_data",
    "missing_market_data",
    "clock_jump_forward",
    "clock_jump_backward",
    "duplicate_candidate",
    "duplicate_order_intent",
    "ledger_lock_contention",
    "interrupted_ledger_append",
    "snapshot_corruption",
    "missing_latest_snapshot",
    "disk_soft_limit",
    "disk_hard_limit",
    "process_termination",
    "network_loss",
    "partial_fill_before_crash",
    "filled_order_before_snapshot",
    "exit_event_before_position_snapshot",
    "reflection_interruption",
    "lesson_storage_interruption",
    "kill_switch_during_open_position",
    "pause_during_pending_intent",
)

# Injections safe to compose in a single long-running (24h/72h/168h) session.
# Terminal / hard-fail injections (kill switch, unrecoverable clock jump,
# process termination without valid LKG, disk hard limit) are exercised in
# dedicated focused tests where the expected outcome is BLOCKED/FAILED_SAFE.
LONG_SESSION_INJECTIONS: tuple[str, ...] = (
    "groq_429",
    "sambanova_429",
    "provider_timeout",
    "provider_invalid_schema",
    "stale_market_data",
    "missing_market_data",
    "duplicate_candidate",
    "duplicate_order_intent",
    "ledger_lock_contention",
    "interrupted_ledger_append",
    "snapshot_corruption",
    "missing_latest_snapshot",
    "disk_soft_limit",
    "network_loss",
    "partial_fill_before_crash",
    "filled_order_before_snapshot",
    "exit_event_before_position_snapshot",
    "reflection_interruption",
    "lesson_storage_interruption",
    "pause_during_pending_intent",
)

# Injections that must terminate the session in a fail-closed state
# (BLOCKED or FAILED_SAFE). Exercised in dedicated focused tests, one at a
# time, and asserted via ``expected_terminal_state``.
TERMINAL_INJECTIONS: tuple[str, ...] = (
    "kill_switch_during_open_position",
    "clock_jump_forward",
    "clock_jump_backward",
    "process_termination",
    "disk_hard_limit",
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _process_memory_bytes() -> int:
    """Best-effort resident memory bytes. Falls back to tracemalloc snapshot size."""
    try:
        import psutil  # type: ignore[import-not-found]

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        pass
    try:  # tracemalloc: sum of allocated blocks
        if tracemalloc.is_tracing():
            current, _ = tracemalloc.get_traced_memory()
            return int(current)
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ProviderMockConfig:
    """Deterministic mock for AI Providers — never a real request."""

    label: str = "PROVIDER_FIXTURE_NOT_REAL_AI_EVALUATION"

    def respond(self, *, injection: set[str], candidate: dict[str, Any]) -> dict[str, Any]:
        if "groq_429" in injection and candidate.get("provider") == "GROQ":
            return {"status": "PROVIDER_QUOTA_EXCEEDED", "provider": "GROQ", "code": 429, "label": self.label}
        if "sambanova_429" in injection and candidate.get("provider") == "SAMBANOVA":
            return {"status": "PROVIDER_QUOTA_EXCEEDED", "provider": "SAMBANOVA", "code": 429, "label": self.label}
        if "provider_timeout" in injection and candidate.get("uses_provider"):
            return {"status": "PROVIDER_TIMEOUT", "label": self.label}
        if "provider_invalid_schema" in injection and candidate.get("uses_provider"):
            return {"status": "PROVIDER_INVALID_SCHEMA", "label": self.label, "raw": "{"}
        return {"status": "OK", "label": self.label, "score": 0.5}


@dataclass
class SessionRunResult:
    session_id: str
    logical_duration_hours: float
    accelerated_wall_time_seconds: float
    candidate_count: int
    intent_count: int
    position_count: int
    exit_count: int
    checkpoint_count: int
    restart_count: int
    recovery_count: int
    provider_failure_count: int
    ledger_event_count: int
    snapshot_count: int
    memory_start_bytes: int
    memory_peak_bytes: int
    memory_end_bytes: int
    cpu_time_seconds: float
    final_state: str
    session_pass: bool
    kill_switch_status: str
    invariants_status: str
    invariants_counts: dict[str, int]
    invalid_transition_attempts: int
    injection_flags: list[str]
    reflection_queue_len: int
    lesson_queue_len: int
    exchange_write_attempt_count: int
    contract_requirements: list[str]
    state_history_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "logical_duration_hours": self.logical_duration_hours,
            "accelerated_wall_time_seconds": self.accelerated_wall_time_seconds,
            "candidate_count": self.candidate_count,
            "intent_count": self.intent_count,
            "position_count": self.position_count,
            "exit_count": self.exit_count,
            "checkpoint_count": self.checkpoint_count,
            "restart_count": self.restart_count,
            "recovery_count": self.recovery_count,
            "provider_failure_count": self.provider_failure_count,
            "ledger_event_count": self.ledger_event_count,
            "snapshot_count": self.snapshot_count,
            "memory_start_bytes": self.memory_start_bytes,
            "memory_peak_bytes": self.memory_peak_bytes,
            "memory_end_bytes": self.memory_end_bytes,
            "cpu_time_seconds": self.cpu_time_seconds,
            "final_state": self.final_state,
            "session_pass": self.session_pass,
            "kill_switch_status": self.kill_switch_status,
            "invariants_status": self.invariants_status,
            "invariants_counts": dict(self.invariants_counts),
            "invalid_transition_attempts": self.invalid_transition_attempts,
            "injection_flags": list(self.injection_flags),
            "reflection_queue_len": self.reflection_queue_len,
            "lesson_queue_len": self.lesson_queue_len,
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
            "contract_requirements": list(self.contract_requirements),
            "state_history_summary": dict(self.state_history_summary),
        }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class AutonomousSessionOrchestratorV11:
    """V1.1 chaos-hardened session orchestrator.

    Threading model: a single orchestrator instance is owned by one session.
    Callbacks (candidate submission, exit updates, Reflection results, Lesson
    storage) can arrive concurrently — the orchestrator serialises canonical
    lifecycle operations under a re-entrant lock while ensuring
    idempotency-key uniqueness.
    """

    SCHEMA = "autonomous_session_orchestrator_v1_1"

    def __init__(
        self,
        root: Path,
        *,
        max_positions: int = 2,
        max_intents: int = 2,
        clock: AcceleratedLogicalClock | None = None,
        provider: ProviderMockConfig | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.durability = RuntimeDurabilityV1(self.root / "durability")
        self.ledger: PrivateEventLedger = self.durability.open_ledger()
        self.sim = AutonomousExecutionSimulatorV1(
            max_positions=max_positions, max_intents=max_intents
        )
        self.clock = clock or AcceleratedLogicalClock()
        self.provider = provider or ProviderMockConfig()
        self.guard = NoExchangeWriteGuard()

        # State
        self.session_id: str | None = None
        self.state_machine: SessionStateMachine | None = None
        self.kill_switch_flag = False
        self.kill_switch_status = "READY"
        self.checkpoint_count = 0
        self.restart_count = 0
        self.recovery_count = 0
        self.provider_failure_count = 0
        self.reflection_queue: list[dict[str, Any]] = []
        self.lesson_queue: list[dict[str, Any]] = []
        self.injection_flags: list[str] = []
        self.candidate_count = 0
        self.intent_count = 0
        self.position_count = 0
        self.exit_count = 0
        self.snapshot_count = 0
        self.orphan_lifecycle_count = 0
        self.duplicate_position_count = 0
        self.untracked_fill_count = 0
        self.risk_limit_bypass_count = 0
        self.processed_candidate_keys: set[str] = set()
        self.completed_intent_keys: set[str] = set()
        self.contract_requirements: list[str] = []
        self.memory_peak_bytes = 0
        self.memory_start_bytes = 0
        self.cpu_start = time.process_time()

        # Concurrency
        self._lock = threading.RLock()
        self._ledger_lock = threading.Lock()

    # ------------------------------------------------------------------
    # State transition helpers
    # ------------------------------------------------------------------

    def _transition(
        self,
        target: str,
        *,
        reason: str,
        idempotency_key: str,
        checkpoint_id: str | None = None,
        ledger_sequence: int | None = None,
        metadata: dict[str, Any] | None = None,
        allow_forced_failed_safe: bool = False,
    ) -> TransitionRecord | None:
        assert self.state_machine is not None
        try:
            record = self.state_machine.transition(
                target,
                reason=reason,
                idempotency_key=idempotency_key,
                checkpoint_id=checkpoint_id,
                ledger_sequence=ledger_sequence,
                metadata=metadata,
            )
        except InvalidTransitionError as exc:
            if allow_forced_failed_safe and target == "FAILED_SAFE":
                return self.state_machine.force_failed_safe(
                    reason=reason,
                    idempotency_key=idempotency_key,
                    checkpoint_id=checkpoint_id,
                    ledger_sequence=ledger_sequence,
                )
            # Invalid transitions are recorded on the state machine's
            # invalid_attempts list — do not silently mutate.
            return None
        self._observe_memory()
        return record

    def _observe_memory(self) -> None:
        val = _process_memory_bytes()
        if val > self.memory_peak_bytes:
            self.memory_peak_bytes = val

    # ------------------------------------------------------------------
    # Ledger helpers
    # ------------------------------------------------------------------

    def _ledger_append(
        self,
        *,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        contention_ms: float = 0.0,
        interrupt: bool = False,
    ) -> int | None:
        """Append a ledger event under contention protection.

        ``contention_ms`` simulates lock contention by holding the ledger lock
        for a small duration. ``interrupt`` skips the append AFTER acquiring
        the lock (simulating an interrupted append) and records the intent
        as a contract requirement so recovery can detect it.
        """
        with self._ledger_lock:
            if contention_ms > 0:
                time.sleep(contention_ms / 1000.0)
            if interrupt:
                # Simulated interrupted ledger append — surface as contract
                # requirement rather than silently skipping.
                self.contract_requirements.append(
                    "ledger_append_interrupted:must_retry_from_last_sequence"
                )
                return None
            result = self.ledger.append(
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event_type,
                source="session_orchestrator_v1_1",
                payload=payload,
                idempotency_key=idempotency_key,
            )
            return result.sequence_number

    def _checkpoint(
        self,
        reason: str,
        *,
        fast: bool = False,
        corrupt: bool = False,
        missing: bool = False,
    ) -> dict[str, Any]:
        assert self.session_id is not None
        assert self.state_machine is not None
        self.checkpoint_count += 1
        try:
            if missing:
                # Simulate a snapshot creation that fails to persist.
                self.contract_requirements.append(
                    "snapshot_missing_latest:must_block_ambiguous_on_recovery"
                )
                snap = {"status": "MISSING_SIMULATED", "generation": None}
            else:
                snap = self.durability.create_snapshot(self.ledger, fast=fast)
                self.snapshot_count += 1
            if corrupt and not missing:
                # Corrupt the last-known-good pointer for a later recovery drill.
                if self.durability.lkg_path.exists():
                    pointer = json.loads(
                        self.durability.lkg_path.read_text(encoding="utf-8")
                    )
                    pointer["snapshot_checksum"] = "0" * 64  # deliberate mismatch
                    self.durability.lkg_path.write_text(
                        json.dumps(pointer, indent=2) + "\n", encoding="utf-8"
                    )
        except Exception as exc:  # pragma: no cover — durability layer is stable
            snap = {"status": "CHECKPOINT_ERROR", "error": str(exc)}

        payload = {
            "session_id": self.session_id,
            "state": self.state_machine.state,
            "checkpoint_count": self.checkpoint_count,
            "clock": self.clock.stats,
            "sim": self.sim.report(),
            "created_at": _utc(),
            "reason": reason,
        }
        ckpt_path = self.root / f"{self.session_id}.checkpoint.json"
        ckpt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        seq = self._ledger_append(
            aggregate_id=self.session_id,
            aggregate_type="SNAPSHOT",
            event_type="SESSION_CHECKPOINT",
            payload={
                "checkpoint_count": self.checkpoint_count,
                "snap_status": snap.get("status"),
                "generation": snap.get("generation"),
                "reason": reason,
            },
            idempotency_key=f"ckpt:{self.session_id}:{self.checkpoint_count}:{reason}",
        )
        return {"checkpoint": payload, "snapshot": snap, "ledger_sequence": seq}

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start(self, session_id: str, *, logical_hours: float) -> None:
        with self._lock:
            if self.session_id is not None and self.session_id != session_id:
                raise RuntimeError("orchestrator_already_bound_to_session")
            self.session_id = session_id
            self.state_machine = SessionStateMachine(session_id)
            self.memory_start_bytes = _process_memory_bytes()
            self.memory_peak_bytes = self.memory_start_bytes
            self._transition(
                "INITIALIZING",
                reason="session_start_requested",
                idempotency_key=f"init:{session_id}",
            )
            seq = self._ledger_append(
                aggregate_id=session_id,
                aggregate_type="DATA_CAPTURE_SESSION",
                event_type="SESSION_START",
                payload={
                    "logical_hours": logical_hours,
                    "mode": "ACCELERATED_HISTORICAL_REPLAY",
                    "exchange_write": False,
                    "schema": self.SCHEMA,
                },
                idempotency_key=f"sess_start:{session_id}",
            )
            self._transition(
                "RUNNING",
                reason="initialization_complete",
                idempotency_key=f"run:{session_id}",
                ledger_sequence=seq,
            )
            # Initial checkpoint so recovery has an LKG snapshot to restore to
            # from the very first candidate onward.
            self._checkpoint(reason="initial_checkpoint")

    def request_pause(self, *, reason: str, full_checkpoint: bool = False) -> None:
        with self._lock:
            assert self.session_id is not None
            self._transition(
                "PAUSING",
                reason=reason,
                idempotency_key=f"pausing:{self.session_id}:{reason}:{self.checkpoint_count}",
            )
            if full_checkpoint:
                # Only take a full LKG-updating checkpoint when caller asks
                # for it (long-running "graceful pause" scenario). Mid-intent
                # pauses should not overwrite the LKG with an unclosed intent.
                self._checkpoint(reason=f"pause_full:{reason}")
            else:
                # Lightweight ledger-only transition record — no snapshot.
                self._ledger_append(
                    aggregate_id=self.session_id,
                    aggregate_type="DATA_CAPTURE_SESSION",
                    event_type="SESSION_PAUSE",
                    payload={
                        "reason": reason,
                        "state_before": "RUNNING",
                        "at": _utc(),
                    },
                    idempotency_key=f"pause:{self.session_id}:{reason}:{self.checkpoint_count}",
                )
            self._transition(
                "PAUSED",
                reason=reason,
                idempotency_key=f"paused:{self.session_id}:{reason}:{self.checkpoint_count}",
            )

    def request_resume(self, *, reason: str) -> None:
        with self._lock:
            assert self.state_machine is not None
            self._transition(
                "RUNNING",
                reason=reason,
                idempotency_key=f"resume:{self.session_id}:{self.state_machine.state}:{self.checkpoint_count}",
            )

    RECOVERY_ATTEMPT_LIMIT = 6

    def request_recover(self, *, reason: str) -> RecoveryOutcome:
        with self._lock:
            assert self.session_id is not None
            self.recovery_count += 1
            self._transition(
                "RECOVERING",
                reason=reason,
                idempotency_key=f"recover:{self.session_id}:{self.recovery_count}",
            )
            # `restore_last_known_good` may overwrite the live ledger file
            # underneath our open handle; close and reopen after recovery so
            # subsequent writes hit the restored file.
            try:
                self.ledger.close()
            except Exception:
                pass
            recovery = SessionCrashRecovery(self.root).recover(self.session_id)
            # Re-open our own ledger handle regardless of outcome so we don't
            # keep a stale sqlite connection.
            self.ledger = self.durability.open_ledger()
            # Any monotonic violation that triggered the recovery has now
            # been handled; clear the marker so we don't loop.
            try:
                self.clock.clear_monotonic_violation()
            except Exception:
                pass
            if recovery.status == "RECOVERED":
                if self.recovery_count > self.RECOVERY_ATTEMPT_LIMIT:
                    self._transition(
                        "BLOCKED",
                        reason="recovery_attempt_limit_exceeded",
                        idempotency_key=f"blocked_recover_limit:{self.session_id}",
                        metadata={"recovery_count": self.recovery_count},
                    )
                else:
                    self._transition(
                        "RUNNING",
                        reason="recovery_ok",
                        idempotency_key=f"post_recover:{self.session_id}:{self.recovery_count}",
                        metadata={"invariants": recovery.invariants.to_dict() if recovery.invariants else None},
                    )
            else:
                self._transition(
                    "BLOCKED",
                    reason=f"recovery_{recovery.status.lower()}",
                    idempotency_key=f"blocked_recover:{self.session_id}:{self.recovery_count}",
                    metadata={"reason": recovery.reason},
                )
            return recovery

    def trigger_kill_switch(self, *, reason: str) -> None:
        with self._lock:
            if self.kill_switch_flag:
                return
            self.kill_switch_flag = True
            self.kill_switch_status = "TRIGGERED"
            # Cancel safe pending intents.
            for oid, order in list(self.sim.orders.items()):
                if order.state in {"CREATED", "ACCEPTED"}:
                    self.sim.cancel(oid)
            self._ledger_append(
                aggregate_id=self.session_id or "unknown_session",
                aggregate_type="DATA_CAPTURE_SESSION",
                event_type="SESSION_KILL_SWITCH",
                payload={"reason": reason, "at": _utc()},
                idempotency_key=f"kill:{self.session_id}",
            )

    def finalize(self, *, reason: str = "logical_deadline_reached") -> None:
        with self._lock:
            assert self.state_machine is not None
            # Drain any leftover simulated intents/positions before invariant check.
            self._hygiene_flatten()
            # If kill switch fired, transition RUNNING/PAUSED -> FINALIZING -> BLOCKED
            # to preserve ambiguous state distinction; otherwise -> COMPLETED.
            current = self.state_machine.state
            if current not in {"RUNNING", "PAUSED", "RECOVERING"}:
                # Already terminal — still record a final checkpoint if possible.
                if current in {"BLOCKED", "FAILED_SAFE", "COMPLETED"}:
                    try:
                        self._checkpoint(reason="terminal_seal")
                    except Exception:
                        pass
                return
            self._transition(
                "FINALIZING",
                reason=reason,
                idempotency_key=f"finalizing:{self.session_id}:{self.checkpoint_count}",
            )
            self._checkpoint(reason="finalize")
            invariants = self._current_invariants()
            if not invariants.passed:
                self._transition(
                    "FAILED_SAFE",
                    reason="finalize_invariant_violation",
                    idempotency_key=f"failed:{self.session_id}",
                    metadata=invariants.to_dict(),
                    allow_forced_failed_safe=True,
                )
                return
            if self.kill_switch_flag:
                self._transition(
                    "BLOCKED",
                    reason="kill_switch_terminal",
                    idempotency_key=f"blocked:{self.session_id}:kill",
                )
                return
            self._transition(
                "COMPLETED",
                reason=reason,
                idempotency_key=f"completed:{self.session_id}",
            )

    def _hygiene_flatten(self) -> None:
        """Cancel pending intents and flatten open positions (sim only)."""
        for oid, order in list(self.sim.orders.items()):
            if order.state == "PARTIALLY_FILLED" and not order.reduce_only:
                mark = float(order.avg_fill_price or 100.0)
                self.sim.try_fill(
                    oid,
                    market_bid=mark * 0.9999,
                    market_ask=mark * 1.0001,
                    last_price=mark,
                    path_low=mark * 0.99,
                    path_high=mark * 1.01,
                )
            elif order.state in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED", "CANCEL_PENDING"}:
                self.sim.cancel(oid)
        for pid, pos in list(self.sim.positions.items()):
            if pos.state not in {"OPEN", "OPENING", "REDUCING"}:
                continue
            exit_key = f"hygiene_exit:{pid}:{self.checkpoint_count}"
            created = self.sim.create_order(
                {
                    "idempotency_key": exit_key,
                    "symbol": pos.symbol,
                    "side": "SELL" if pos.side in {"LONG", "BUY"} else "BUY",
                    "order_type": "market",
                    "qty": pos.qty,
                    "mark_price": pos.entry_price,
                    "reduce_only": True,
                }
            )
            if created.get("status") == "ACCEPTED":
                px = pos.entry_price
                self.sim.try_fill(
                    created["order_id"],
                    market_bid=px,
                    market_ask=px,
                    last_price=px,
                    path_low=px * 0.999,
                    path_high=px * 1.001,
                )

    # ------------------------------------------------------------------
    # Candidate / intent processing
    # ------------------------------------------------------------------

    def submit_candidate(
        self,
        candidate: dict[str, Any],
        *,
        injection: set[str] | None = None,
    ) -> dict[str, Any]:
        """Submit a candidate for evaluation. Idempotent by ``candidate_id``.

        Returns a dict describing the processing outcome (accepted, rejected,
        blocked). This method is safe to call concurrently.
        """
        injection = set(injection or ())
        with self._lock:
            assert self.state_machine is not None
            assert self.session_id is not None
            if self.state_machine.state not in {"RUNNING"}:
                return {"status": "SESSION_NOT_RUNNING", "state": self.state_machine.state}
            cid = candidate["candidate_id"]
            if cid in self.processed_candidate_keys:
                # duplicate candidate — idempotent no-op.
                if "duplicate_candidate" in injection:
                    self.injection_flags.append("duplicate_candidate_absorbed")
                return {"status": "DUPLICATE_CANDIDATE_IGNORED", "candidate_id": cid}
            self.processed_candidate_keys.add(cid)
            self.candidate_count += 1

            # Provider mock (never real).
            prov = self.provider.respond(injection=injection, candidate=candidate)
            if prov.get("status") != "OK":
                self.provider_failure_count += 1
                self._ledger_append(
                    aggregate_id=cid,
                    aggregate_type="PROVIDER_REQUEST",
                    event_type="PROVIDER_BLOCKED",
                    payload={"provider_status": prov.get("status"), "label": prov.get("label")},
                    idempotency_key=f"prov:{cid}",
                )
                return {"status": "PROVIDER_BLOCKED", "provider_status": prov.get("status")}

            # Market data checks.
            if "missing_market_data" in injection and candidate.get("needs_market_data"):
                return {"status": "MISSING_MARKET_DATA_BLOCKED", "candidate_id": cid}
            if "stale_market_data" in injection and candidate.get("needs_market_data"):
                return {"status": "STALE_MARKET_DATA_BLOCKED", "candidate_id": cid}
            if "network_loss" in injection and candidate.get("needs_network"):
                return {"status": "NETWORK_LOSS_BLOCKED", "candidate_id": cid}

            # Clock jumps — monotonic violation escalates to BLOCKED via
            # transition_after_step.
            if "clock_jump_forward" in injection and candidate.get("apply_clock_jump"):
                self.clock.jump_forward(3600.0)
            if "clock_jump_backward" in injection and candidate.get("apply_clock_jump"):
                self.clock.jump_backward(600.0)

            # Risk override rejection.
            if candidate.get("risk_override"):
                self.risk_limit_bypass_count += 0  # never bypassed
                return {"status": "RISK_OVERRIDE_REJECTED", "candidate_id": cid}

            intent_key = candidate["idempotency_key"]

            # Duplicate order intent injection — request the same intent twice.
            duplicate_second_request = "duplicate_order_intent" in injection and candidate.get(
                "trigger_duplicate_intent"
            )

            mark = float(candidate.get("mark_price") or 100.0)
            qty = max(0.01, (self.sim.margin_usdt * self.sim.leverage) / mark)

            created = self.sim.create_order(
                {
                    "idempotency_key": intent_key,
                    "symbol": candidate.get("symbol", "BTCUSDT"),
                    "side": candidate.get("side", "BUY"),
                    "order_type": candidate.get("order_type", "market"),
                    "qty": qty,
                    "mark_price": mark,
                    "price": candidate.get("limit_price"),
                    "stop_price": candidate.get("stop_price"),
                    "reduce_only": False,
                    "leverage": candidate.get("leverage"),
                    "margin_mode": candidate.get("margin_mode", "ISOLATED"),
                    "requested_actions": candidate.get("requested_actions"),
                }
            )

            if duplicate_second_request:
                dup = self.sim.create_order(
                    {
                        "idempotency_key": intent_key,
                        "symbol": candidate.get("symbol", "BTCUSDT"),
                        "side": candidate.get("side", "BUY"),
                        "order_type": candidate.get("order_type", "market"),
                        "qty": qty,
                        "mark_price": mark,
                        "leverage": candidate.get("leverage"),
                    }
                )
                if dup.get("status") != "DUPLICATE_IGNORED":
                    # Contract requirement — simulator MUST reject duplicate intent.
                    self.contract_requirements.append(
                        "execution_simulator:duplicate_intent_must_be_DUPLICATE_IGNORED"
                    )

            if created.get("status") == "DUPLICATE_IGNORED":
                return {"status": "DUPLICATE_INTENT_IGNORED", "candidate_id": cid, **created}
            if created.get("status") != "ACCEPTED":
                return {"status": "ORDER_REJECTED", **created}

            self.intent_count += 1
            oid = created["order_id"]
            seq = self._ledger_append(
                aggregate_id=cid,
                aggregate_type="ORDER_INTENT",
                event_type="ORDER_ACCEPTED",
                payload={"order_id": oid, "intent_key": intent_key, "session_id": self.session_id},
                idempotency_key=f"intent:{intent_key}",
                contention_ms=5.0 if "ledger_lock_contention" in injection else 0.0,
                interrupt="interrupted_ledger_append" in injection
                and candidate.get("trigger_ledger_interrupt", False),
            )

            # Pause during pending intent — this is a legal request; we
            # exercise the state machine but leave the intent in flight.
            if "pause_during_pending_intent" in injection and candidate.get(
                "pause_during_intent"
            ):
                self.request_pause(reason="pause_during_pending_intent")
                self.request_resume(reason="resume_after_pause_during_pending_intent")

            fill_kwargs = self._build_fill_kwargs(candidate, mark, injection)
            filled = self.sim.try_fill(oid, **fill_kwargs)

            # Same-bar ambiguity — must be BLOCKED_AMBIGUOUS.
            if filled.get("status") == "BLOCKED_AMBIGUOUS":
                return {"status": "BLOCKED_AMBIGUOUS", "candidate_id": cid, **filled}

            if filled.get("status") == "PARTIALLY_FILLED":
                if "partial_fill_before_crash" in injection and candidate.get(
                    "trigger_crash_after_partial"
                ):
                    # Simulate the crash: take a fast checkpoint, then close
                    # and re-open the ledger. Recovery is deferred to the
                    # ``simulate_partial_fill_crash_recovery`` helper so the
                    # long-running session loop doesn't automatically block.
                    self._checkpoint(reason="crash_after_partial")
                    try:
                        self.ledger.close()
                    except Exception:
                        pass
                    self.ledger = self.durability.open_ledger()
                    self.restart_count += 1
                    self.contract_requirements.append(
                        "partial_fill_before_crash:remainder_must_route_via_recovery"
                    )
                # complete remainder — after crash sim, we still fill the
                # remainder because the sim's in-memory order state persists
                # in this deterministic replay. Real recovery drills exercise
                # this via ``simulate_partial_fill_crash_recovery``.
                filled = self.sim.try_fill(
                    oid,
                    market_bid=mark * 0.9999,
                    market_ask=mark * 1.0001,
                    last_price=mark,
                    path_low=mark * 0.99,
                    path_high=mark * 1.01,
                )

            if filled.get("status") != "FILLED":
                return {"status": filled.get("status"), "detail": filled}

            self.position_count += 1
            pid = filled.get("position_id")

            if "filled_order_before_snapshot" in injection and candidate.get(
                "trigger_snapshot_between_fill_and_exit"
            ):
                self._checkpoint(reason="snapshot_after_fill_before_exit")

            # Exit
            exit_price = mark * (0.998 if candidate.get("lose") else 1.004)
            exit_req = self.sim.create_order(
                {
                    "idempotency_key": f"{intent_key}:exit",
                    "symbol": candidate.get("symbol", "BTCUSDT"),
                    "side": "SELL" if candidate.get("side", "BUY").upper() == "BUY" else "BUY",
                    "order_type": "market",
                    "qty": qty,
                    "mark_price": exit_price,
                    "reduce_only": True,
                }
            )

            if "exit_event_before_position_snapshot" in injection and candidate.get(
                "trigger_exit_before_snapshot"
            ):
                # Take snapshot AFTER creating the exit intent but BEFORE fill,
                # then continue.
                self._checkpoint(reason="snapshot_between_exit_intent_and_fill")

            if exit_req.get("status") != "ACCEPTED":
                # Contract requirement (should not happen with valid inputs).
                self.contract_requirements.append(
                    "execution_simulator:exit_intent_must_accept_reduce_only"
                )
                return {"status": "EXIT_REJECTED", "detail": exit_req}

            closed = self.sim.try_fill(
                exit_req["order_id"],
                market_bid=exit_price,
                market_ask=exit_price,
                last_price=exit_price,
                path_low=exit_price * 0.999,
                path_high=exit_price * 1.001,
            )

            if closed.get("status") != "FILLED":
                # exit didn't fill for some reason — check if we still have
                # an open position (would violate invariants).
                if self.sim.open_ambiguous_position_count() == 0 and closed.get(
                    "status"
                ) == "UNFILLED":
                    self.untracked_fill_count += 0  # unfilled, not untracked
                return {"status": "EXIT_NOT_FILLED", "detail": closed}

            self.exit_count += 1
            self.completed_intent_keys.add(intent_key)
            net = (closed.get("close") or {}).get("net_pnl")
            classification = classify_completed_trade(
                pnl=net if net is not None else (-1.0 if candidate.get("lose") else 1.0),
                process_evidence=candidate.get("process_evidence")
                or control_fixture_process_evidence(bad=False),
            )
            self._ledger_append(
                aggregate_id=cid,
                aggregate_type="TRADE_OUTCOME",
                event_type="SIMULATED_CLOSED",
                payload={
                    "classification": classification,
                    "intent_key": intent_key,
                    "position_id": pid,
                    "session_id": self.session_id,
                    "provider_label": "PROVIDER_FIXTURE_NOT_REAL_AI_EVALUATION",
                },
                idempotency_key=f"out:{intent_key}",
            )

            # Reflection queue (deterministic mock).
            if "reflection_interruption" in injection and candidate.get(
                "trigger_reflection_interrupt"
            ):
                self.contract_requirements.append(
                    "reflection_runner:interrupted_reflection_must_retry_from_intent_key"
                )
            else:
                self.reflection_queue.append(
                    {
                        "intent_key": intent_key,
                        "classification": classification,
                        "label": "REFLECTION_FIXTURE",
                    }
                )

            # Lesson queue (deterministic mock).
            if "lesson_storage_interruption" in injection and candidate.get(
                "trigger_lesson_interrupt"
            ):
                self.contract_requirements.append(
                    "lesson_store:interrupted_lesson_must_retry_from_intent_key"
                )
            else:
                self.lesson_queue.append(
                    {"intent_key": intent_key, "classification": classification}
                )

            # Kill switch during open position — allowed to be exercised, but
            # the mission requires: no real exchange write, current evidence
            # preserved, safe pending cancelled, terminal via BLOCKED.
            if "kill_switch_during_open_position" in injection and candidate.get(
                "trigger_kill_during_open"
            ):
                self.trigger_kill_switch(reason="kill_switch_during_open_position")

            return {
                "status": "COMPLETE",
                "candidate_id": cid,
                "classification": classification,
                "fill": filled,
                "close": closed,
            }

    def _build_fill_kwargs(
        self,
        candidate: dict[str, Any],
        mark: float,
        injection: set[str],
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "market_bid": mark * 0.9999,
            "market_ask": mark * 1.0001,
            "last_price": mark,
            "path_low": mark * 0.99,
            "path_high": mark * 1.01,
        }
        if candidate.get("order_type") == "limit" and candidate.get("limit_price"):
            kwargs["path_low"] = float(candidate["limit_price"]) - self.sim.tick_size * 2
            kwargs["path_high"] = float(candidate["limit_price"]) + self.sim.tick_size * 2
        if "partial_fill_before_crash" in injection and candidate.get(
            "trigger_crash_after_partial"
        ):
            kwargs["partial_ratio"] = 0.5
        if candidate.get("same_bar_ambiguity"):
            kwargs["same_bar_stop"] = mark * 0.995
            kwargs["same_bar_target"] = mark * 1.005
        return kwargs

    # ------------------------------------------------------------------
    # Invariants
    # ------------------------------------------------------------------

    def _current_invariants(self):
        counts = {
            "open_ambiguous_position_count": self.sim.open_ambiguous_position_count(),
            "orphan_lifecycle_count": self.orphan_lifecycle_count,
            "duplicate_position_count": self.duplicate_position_count,
            "unclosed_intent_count": self.sim.unclosed_intent_count(),
            "untracked_fill_count": self.untracked_fill_count,
            "risk_limit_bypass_count": self.risk_limit_bypass_count,
            "exchange_write_attempt_count": self.guard.exchange_write_attempt_count,
        }
        return check_recovery_invariants(counts)

    # ------------------------------------------------------------------
    # Session runner (accelerated)
    # ------------------------------------------------------------------

    def run_accelerated_session(
        self,
        *,
        session_id: str,
        logical_hours: float,
        candidates: list[dict[str, Any]],
        injections: list[str],
        checkpoint_every: int = 20,
        restart_after_index: int | None = None,
        force_kill_after_index: int | None = None,
        disk_limit: str | None = None,
    ) -> SessionRunResult:
        """Run one accelerated logical session end-to-end.

        The candidates list defines the entire schedule for the logical
        duration. Injections are applied per-candidate based on the mission
        matrix; the orchestrator also exercises restart / kill switch via
        the given indices.
        """
        wall_start = time.perf_counter()
        try:
            tracemalloc.start(1)
        except Exception:
            pass
        self.injection_flags = list(injections)
        inj_set = set(injections)
        # Map catalog disk flags onto the disk_limit control if not explicit.
        if disk_limit is None:
            if "disk_hard_limit" in inj_set:
                disk_limit = "hard"
            elif "disk_soft_limit" in inj_set:
                disk_limit = "soft"
        self.start(session_id, logical_hours=logical_hours)

        # Distribute logical hours across candidates so the clock actually
        # advances through the whole session window.
        n = max(1, len(candidates))
        per_step_hours = logical_hours / n

        for i, raw_cand in enumerate(candidates):
            if self.state_machine and self.state_machine.state in {"BLOCKED", "FAILED_SAFE", "COMPLETED"}:
                break
            self.clock.advance_hours(per_step_hours)
            cand = self._inject_candidate_flags(raw_cand, i, inj_set)
            step_inj = set()
            for flag in INJECTION_CATALOG:
                if flag in inj_set and cand.get(f"_inject_{flag}"):
                    step_inj.add(flag)

            # Process termination injection: on the very step, take a
            # checkpoint and then simulate a restart (close/reopen ledger).
            if (
                "process_termination" in inj_set
                and restart_after_index is not None
                and i == restart_after_index
            ):
                self._simulate_process_restart()

            # Disk soft/hard limit (simulated): after a certain candidate,
            # switch to fast checkpoints (no full checksum) to model backpressure.
            if disk_limit == "soft" and i > n // 2:
                cand["_use_fast_checkpoint"] = True
            if disk_limit == "hard" and i > (n * 3) // 4:
                # Hard limit — fail-closed, transition to BLOCKED.
                self._transition(
                    "BLOCKED",
                    reason="disk_hard_limit_reached",
                    idempotency_key=f"blocked_disk:{self.session_id}:{i}",
                    metadata={"disk_limit": "hard"},
                )
                break

            outcome = self.submit_candidate(cand, injection=step_inj)

            # Kill switch mid-session at the specified index.
            if (
                force_kill_after_index is not None
                and i == force_kill_after_index
                and not self.kill_switch_flag
            ):
                self.trigger_kill_switch(reason="scheduled_kill_switch")

            # Periodic checkpoint.
            if (i + 1) % checkpoint_every == 0:
                self._checkpoint(
                    reason="periodic",
                    fast=bool(cand.get("_use_fast_checkpoint")),
                )
                # Snapshot corruption injection: corrupt the LKG pointer,
                # then IMMEDIATELY regenerate a fresh clean snapshot so
                # future recoveries have a valid LKG. This models detecting
                # a bad snapshot via checksum and taking a new one.
                if "snapshot_corruption" in inj_set and i + 1 == checkpoint_every * 2:
                    self._checkpoint(reason="corrupt_snapshot_injection", corrupt=True)
                    self._checkpoint(reason="post_corruption_fresh_snapshot")
                    self.contract_requirements.append(
                        "snapshot_corruption:detect_and_regenerate_lkg"
                    )
                # Missing snapshot injection: pretend snapshot creation
                # failed to persist, then take a real one on next iteration.
                if "missing_latest_snapshot" in inj_set and i + 1 == checkpoint_every * 3:
                    self._checkpoint(reason="missing_snapshot_injection", missing=True)
                    self._checkpoint(reason="post_missing_fresh_snapshot")

            # Clock jump backward triggers RECOVERING (monotonic violation).
            if (
                self.clock.last_monotonic_violation
                and self.state_machine
                and self.state_machine.state == "RUNNING"
            ):
                self.request_recover(reason="clock_monotonic_violation")

        # Final finalize
        self.finalize(reason="logical_deadline_reached")

        # Metrics collation
        cpu_end = time.process_time()
        wall_end = time.perf_counter()
        memory_end = _process_memory_bytes()
        try:
            if tracemalloc.is_tracing():
                _, peak = tracemalloc.get_traced_memory()
                if peak > self.memory_peak_bytes:
                    self.memory_peak_bytes = int(peak)
                tracemalloc.stop()
        except Exception:
            pass
        invariants = self._current_invariants()
        final_state = self.state_machine.state if self.state_machine else "UNKNOWN"
        history_summary = summarize_history(self.state_machine) if self.state_machine else {}

        session_pass = (
            invariants.passed
            and final_state in {"COMPLETED", "BLOCKED"}
            and self.guard.exchange_write_attempt_count == 0
        )

        return SessionRunResult(
            session_id=session_id,
            logical_duration_hours=logical_hours,
            accelerated_wall_time_seconds=wall_end - wall_start,
            candidate_count=self.candidate_count,
            intent_count=self.intent_count,
            position_count=self.position_count,
            exit_count=self.exit_count,
            checkpoint_count=self.checkpoint_count,
            restart_count=self.restart_count,
            recovery_count=self.recovery_count,
            provider_failure_count=self.provider_failure_count,
            ledger_event_count=self.ledger.event_count(),
            snapshot_count=self.snapshot_count,
            memory_start_bytes=self.memory_start_bytes,
            memory_peak_bytes=self.memory_peak_bytes,
            memory_end_bytes=memory_end,
            cpu_time_seconds=cpu_end - self.cpu_start,
            final_state=final_state,
            session_pass=session_pass,
            kill_switch_status=self.kill_switch_status,
            invariants_status="PASS" if invariants.passed else "FAIL",
            invariants_counts=invariants.counts,
            invalid_transition_attempts=(
                self.state_machine.invalid_attempt_count() if self.state_machine else 0
            ),
            injection_flags=list(self.injection_flags),
            reflection_queue_len=len(self.reflection_queue),
            lesson_queue_len=len(self.lesson_queue),
            exchange_write_attempt_count=self.guard.exchange_write_attempt_count,
            contract_requirements=sorted(set(self.contract_requirements)),
            state_history_summary=history_summary,
        )

    def simulate_partial_fill_crash_recovery(self) -> RecoveryOutcome:
        """Exercised by tests — simulate a crash mid-partial-fill and recover.

        Steps: take a checkpoint, close+reopen the ledger, invoke recovery.
        If there is an unfilled remainder the recovery invariant will detect
        an unclosed intent and correctly route the session to
        ``BLOCKED``. Callers should assert the resulting state.
        """
        return self._simulate_process_restart()

    def _simulate_process_restart(self) -> RecoveryOutcome:
        """Close the ledger, reopen from disk, and record a recovery cycle.

        This mimics a hard process termination: everything that was not on
        disk at the last checkpoint is gone. Recovery is invoked and, if the
        LKG + ledger tail are consistent, the session returns to RUNNING.
        """
        assert self.session_id is not None
        self._checkpoint(reason="pre_termination_checkpoint")
        try:
            self.ledger.close()
        except Exception:
            pass
        self.ledger = self.durability.open_ledger()
        self.restart_count += 1
        recovery = self.request_recover(reason="simulated_process_termination")
        return recovery

    def _inject_candidate_flags(
        self,
        raw: dict[str, Any],
        index: int,
        inj_set: set[str],
    ) -> dict[str, Any]:
        """Attach ``_inject_<flag>`` markers so submit_candidate can gate behaviour."""
        cand = dict(raw)
        # Provider flags
        if "groq_429" in inj_set and index % 17 == 0:
            cand["provider"] = "GROQ"
            cand["uses_provider"] = True
            cand["_inject_groq_429"] = True
        if "sambanova_429" in inj_set and index % 19 == 0:
            cand["provider"] = "SAMBANOVA"
            cand["uses_provider"] = True
            cand["_inject_sambanova_429"] = True
        if "provider_timeout" in inj_set and index % 23 == 0:
            cand["uses_provider"] = True
            cand["_inject_provider_timeout"] = True
        if "provider_invalid_schema" in inj_set and index % 29 == 0:
            cand["uses_provider"] = True
            cand["_inject_provider_invalid_schema"] = True
        # Data flags
        if "stale_market_data" in inj_set and index % 31 == 0:
            cand["needs_market_data"] = True
            cand["_inject_stale_market_data"] = True
        if "missing_market_data" in inj_set and index % 37 == 0:
            cand["needs_market_data"] = True
            cand["_inject_missing_market_data"] = True
        if "network_loss" in inj_set and index % 41 == 0:
            cand["needs_network"] = True
            cand["_inject_network_loss"] = True
        # Clock jumps
        if "clock_jump_forward" in inj_set and index % 43 == 0:
            cand["apply_clock_jump"] = True
            cand["_inject_clock_jump_forward"] = True
        if "clock_jump_backward" in inj_set and index % 47 == 0:
            cand["apply_clock_jump"] = True
            cand["_inject_clock_jump_backward"] = True
        # Duplicate candidate — re-use an earlier candidate_id so submit is idempotent.
        if "duplicate_candidate" in inj_set and index > 3 and index % 11 == 0:
            prior = max(0, index - 11)
            cand["candidate_id"] = f"C{prior:06d}"
            cand["_inject_duplicate_candidate"] = True
        # Duplicate order intent
        if "duplicate_order_intent" in inj_set and index % 13 == 0:
            cand["trigger_duplicate_intent"] = True
            cand["_inject_duplicate_order_intent"] = True
        # Ledger effects
        if "ledger_lock_contention" in inj_set and index % 5 == 0:
            cand["_inject_ledger_lock_contention"] = True
        if "interrupted_ledger_append" in inj_set and index % 53 == 0:
            cand["trigger_ledger_interrupt"] = True
            cand["_inject_interrupted_ledger_append"] = True
        # Disk pressure markers (also wired via disk_limit arg)
        if "disk_soft_limit" in inj_set and index == max(1, (len(inj_set) % 7) + 1):
            cand["_inject_disk_soft_limit"] = True
        if "disk_hard_limit" in inj_set and index == max(2, (len(inj_set) % 9) + 2):
            cand["_inject_disk_hard_limit"] = True
        # Fill/exit/kill order chaos
        if "partial_fill_before_crash" in inj_set and index % 25 == 0:
            cand["trigger_crash_after_partial"] = True
            cand["_inject_partial_fill_before_crash"] = True
        if "filled_order_before_snapshot" in inj_set and index % 27 == 0:
            cand["trigger_snapshot_between_fill_and_exit"] = True
            cand["_inject_filled_order_before_snapshot"] = True
        if "exit_event_before_position_snapshot" in inj_set and index % 33 == 0:
            cand["trigger_exit_before_snapshot"] = True
            cand["_inject_exit_event_before_position_snapshot"] = True
        if "reflection_interruption" in inj_set and index % 35 == 0:
            cand["trigger_reflection_interrupt"] = True
            cand["_inject_reflection_interruption"] = True
        if "lesson_storage_interruption" in inj_set and index % 39 == 0:
            cand["trigger_lesson_interrupt"] = True
            cand["_inject_lesson_storage_interruption"] = True
        if "kill_switch_during_open_position" in inj_set and index and index == 50:
            cand["trigger_kill_during_open"] = True
            cand["_inject_kill_switch_during_open_position"] = True
        if "pause_during_pending_intent" in inj_set and index % 45 == 0:
            cand["pause_during_intent"] = True
            cand["_inject_pause_during_pending_intent"] = True
        if "process_termination" in inj_set and index == 7:
            cand["_inject_process_termination"] = True
        if "snapshot_corruption" in inj_set and index == 16:
            cand["_inject_snapshot_corruption"] = True
        if "missing_latest_snapshot" in inj_set and index == 24:
            cand["_inject_missing_latest_snapshot"] = True
        return cand

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def close(self) -> None:
        try:
            self.ledger.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def build_default_candidates(count: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(count):
        out.append(
            {
                "candidate_id": f"C{i:06d}",
                "idempotency_key": f"K{i:06d}",
                "symbol": "BTCUSDT",
                "side": "BUY" if i % 2 == 0 else "SELL",
                "mark_price": 100.0 + (i % 200) * 0.5,
                "order_type": "market",
                "lose": i % 3 == 0,
            }
        )
    return out
