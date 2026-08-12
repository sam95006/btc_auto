"""V15-J Continuous Autonomy Operations Control Plane.

Founder-only mutating ops: start / pause / resume / safe_stop / kill / recover.
Each mutation requires: Founder auth proof, idempotency, ledger event,
checkpoint, and deterministic safety gate. No exchange writes.
"""
from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.continuous_ops_control_v15.auth import FounderAuthStore
from backend.nexus_autonomy.continuous_ops_control_v15.blocks import BlockRegistry
from backend.nexus_autonomy.continuous_ops_control_v15.constants import (
    DENIED,
    DUPLICATE,
    HARD_BANS,
    MUTATING_OPS,
    PRESERVED_FACTS,
    PROGRAM_ID,
    SCHEMA,
    STATE_BLOCKED,
    STATE_COLD,
    STATE_KILLED,
    STATE_PAUSED,
    STATE_PAUSING,
    STATE_RECOVERING,
    STATE_RUNNING,
    STATE_SAFE_STOPPING,
    STATE_STARTING,
    STATE_STOPPED,
)
from backend.nexus_autonomy.continuous_ops_control_v15.safety_gate import SafetyGateV15
from backend.nexus_runtime.durability_v2.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    CORRUPTION_DETECTED,
    RECOVERED_EXACT,
    RECOVERED_LAST_KNOWN_GOOD,
    RECOVERY_FAILED,
    SNAPSHOT_OK,
)
from backend.nexus_runtime.durability_v2.engine import RuntimeDurabilityV2


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ContinuousAutonomyOpsControlV15:
    """Founder-only continuous autonomy operations control plane."""

    SCHEMA = SCHEMA
    PROGRAM_ID = PROGRAM_ID

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.durability = RuntimeDurabilityV2(self.root / "durability")
        self.auth = FounderAuthStore()
        self.gate = SafetyGateV15()
        self.blocks = BlockRegistry(root=self.root / "blocks")
        self._lock = threading.RLock()
        self._state = STATE_COLD
        self._kill_engaged = False
        self._kill_reason: str | None = None
        self._session_id = "ops-session-uninitialized"
        self._checkpoint_count = 0
        self._idempotency_index: dict[str, dict[str, Any]] = {}
        self._ledger = self.durability.open_ledger()
        self._meta_path = self.root / "ops_control_meta.json"
        self._load_meta()

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            try:
                self._ledger.close()
            except Exception:
                pass

    def _load_meta(self) -> None:
        if not self._meta_path.exists():
            return
        try:
            meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            self._state = str(meta.get("state") or STATE_COLD)
            self._kill_engaged = bool(meta.get("kill_engaged"))
            self._kill_reason = meta.get("kill_reason")
            self._session_id = str(meta.get("session_id") or self._session_id)
            self._checkpoint_count = int(meta.get("checkpoint_count") or 0)
            idx = meta.get("idempotency_index") or {}
            if isinstance(idx, dict):
                self._idempotency_index = {
                    str(k): dict(v) for k, v in idx.items() if isinstance(v, dict)
                }
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self._state = STATE_BLOCKED

    def _persist_meta(self) -> None:
        payload = {
            "schema": self.SCHEMA,
            "program_id": self.PROGRAM_ID,
            "state": self._state,
            "kill_engaged": self._kill_engaged,
            "kill_reason": self._kill_reason,
            "session_id": self._session_id,
            "checkpoint_count": self._checkpoint_count,
            "idempotency_index": self._idempotency_index,
            "updated_at": _utc(),
            **PRESERVED_FACTS,
            "hard_bans": HARD_BANS,
        }
        tmp = self._meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self._meta_path)

    def issue_founder_proof(self, *, op: str, idempotency_key: str) -> dict[str, Any]:
        with self._lock:
            return self.auth.issue(
                op=op,
                idempotency_key=idempotency_key,
                session_id=self._session_id,
            )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema": self.SCHEMA,
                "program_id": self.PROGRAM_ID,
                "state": self._state,
                "session_id": self._session_id,
                "kill_engaged": self._kill_engaged,
                "kill_reason": self._kill_reason,
                "checkpoint_count": self._checkpoint_count,
                "gate_counters": self.gate.counters(),
                "blocks": self.blocks.all_blocks(
                    control_state=self._state, kill_engaged=self._kill_engaged
                ),
                **PRESERVED_FACTS,
                "hard_bans": HARD_BANS,
                "exchange_write_attempt_count": self.gate.exchange_write_attempt_count,
            }

    # ------------------------------------------------------------------
    # Mutation core
    # ------------------------------------------------------------------

    def mutate(
        self,
        op: str,
        *,
        idempotency_key: str,
        founder_proof: dict[str, Any] | None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if op not in MUTATING_OPS:
            return {
                "status": DENIED,
                "reason": "unknown_mutating_op",
                "op": op,
                **PRESERVED_FACTS,
            }
        if not idempotency_key:
            return {
                "status": DENIED,
                "reason": "idempotency_key_required",
                "op": op,
                **PRESERVED_FACTS,
            }

        with self._lock:
            # Idempotency short-circuit (before consuming a new proof)
            existing = self._idempotency_index.get(idempotency_key)
            if existing is not None:
                replay = deepcopy(existing)
                replay["status"] = DUPLICATE
                replay["duplicate"] = True
                replay["idempotency_key"] = idempotency_key
                return replay

            payload = dict(payload or {})
            payload["op"] = op

            gate = self.gate.check(
                op=op,
                state=self._state,
                payload=payload,
                kill_engaged=self._kill_engaged,
            )
            if not gate.get("allowed"):
                return {
                    "status": DENIED,
                    "reason": gate.get("reason"),
                    "op": op,
                    "gate": gate,
                    "state": self._state,
                    **PRESERVED_FACTS,
                    "exchange_write_attempt_count": self.gate.exchange_write_attempt_count,
                }

            auth = self.auth.verify(
                founder_proof,
                op=op,
                idempotency_key=idempotency_key,
                session_id=self._session_id,
                consume=True,
            )
            if not auth.get("ok"):
                return {
                    "status": DENIED,
                    "reason": auth.get("reason"),
                    "op": op,
                    "founder_authorization_present": False,
                    "state": self._state,
                    **PRESERVED_FACTS,
                }

            # Apply state transition
            before = self._state
            self._apply_transition(op, payload)
            after = self._state

            if op == "recover" and after == STATE_BLOCKED:
                self._persist_meta()
                return {
                    "status": "FAIL",
                    "reason": "recovery_blocked_fail_closed",
                    "op": op,
                    "state_before": before,
                    "state_after": after,
                    "founder_authorization_present": True,
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }

            # Ledger event (redacted auth)
            append = self._ledger.append(
                aggregate_id=self._session_id,
                aggregate_type="DATA_CAPTURE_SESSION",
                event_type=f"OPS_{op.upper()}",
                source="continuous_ops_control_v15",
                payload={
                    "op": op,
                    "state_before": before,
                    "state_after": after,
                    "at": _utc(),
                    "auth": self.auth.public_audit_view(founder_proof),
                    "gate_reason": gate.get("reason"),
                    "exchange_write": False,
                },
                idempotency_key=idempotency_key,
            )
            if append.status not in {"APPENDED", "DUPLICATE_IGNORED"}:
                # Roll back is not attempted; fail closed.
                self._state = STATE_BLOCKED
                self._persist_meta()
                return {
                    "status": "FAIL",
                    "reason": f"ledger_append_{append.status}",
                    "op": op,
                    "ledger": {
                        "status": append.status,
                        "reason": append.reason,
                    },
                    **PRESERVED_FACTS,
                }

            # Checkpoint after every successful mutation
            snap = self.durability.create_snapshot(self._ledger)
            if snap.status != SNAPSHOT_OK:
                self._state = STATE_BLOCKED
                self._persist_meta()
                return {
                    "status": "FAIL",
                    "reason": "checkpoint_failed",
                    "op": op,
                    "snapshot": snap.to_dict(),
                    **PRESERVED_FACTS,
                }
            self._checkpoint_count += 1
            self._persist_meta()

            result = {
                "status": "PASS",
                "op": op,
                "duplicate": bool(append.duplicate),
                "idempotency_key": idempotency_key,
                "state_before": before,
                "state_after": after,
                "state": after,
                "founder_authorization_present": True,
                "auth_reason": auth.get("reason"),
                "ledger": {
                    "status": append.status,
                    "event_id": append.event_id,
                    "sequence_number": append.sequence_number,
                    "duplicate": append.duplicate,
                },
                "checkpoint": {
                    "status": snap.status,
                    "count": self._checkpoint_count,
                    "detail": snap.to_dict(),
                },
                "gate": {"allowed": True, "reason": gate.get("reason")},
                "kill_engaged": self._kill_engaged,
                "exchange_write": False,
                **PRESERVED_FACTS,
                "exchange_write_attempt_count": self.gate.exchange_write_attempt_count,
            }
            # Store replay payload without nested duplicate flag confusion
            stored = deepcopy(result)
            stored["status"] = "PASS"
            self._idempotency_index[idempotency_key] = stored
            self._persist_meta()
            return result

    def _apply_transition(self, op: str, payload: dict[str, Any]) -> None:
        if op == "start":
            self._session_id = str(payload.get("session_id") or f"ops-{_utc()}")
            self._state = STATE_STARTING
            self.blocks.decision_state = "MONITORING"
            self.blocks.execution_state = "READY"
            self.blocks.reflection_state = "IDLE"
            self.blocks.lesson_gate_state = "CLOSED"
            self.blocks.capture_status = "OBSERVING"
            self.blocks.provider_soft_cap = int(payload.get("provider_soft_cap") or 1000)
            self.blocks.provider_tokens_remaining = int(
                payload.get("provider_tokens_remaining") or 1000
            )
            self._state = STATE_RUNNING
        elif op == "pause":
            self._state = STATE_PAUSING
            self._state = STATE_PAUSED
        elif op == "resume":
            self._state = STATE_RUNNING
        elif op == "safe_stop":
            self._state = STATE_SAFE_STOPPING
            self.blocks.decision_state = "IDLE"
            self.blocks.execution_state = "IDLE"
            self.blocks.capture_status = "STOPPED_SAFE"
            self._state = STATE_STOPPED
        elif op == "kill":
            self._kill_engaged = True
            self._kill_reason = str(payload.get("reason") or "founder_kill")
            self.blocks.decision_state = "KILLED"
            self.blocks.execution_state = "KILLED"
            self.blocks.capture_status = "KILLED"
            self.blocks.lesson_gate_state = "CLOSED"
            self._state = STATE_KILLED
        elif op == "recover":
            self._state = STATE_RECOVERING
            # Close live handle before LKG restore (Windows-safe; no silent guess).
            try:
                self._ledger.close()
            except Exception:
                pass
            restored = self.durability.restore_last_known_good(allow_ambiguous=False)
            self._ledger = self.durability.open_ledger()
            status = str(restored.status)
            if status in {RECOVERED_EXACT, RECOVERED_LAST_KNOWN_GOOD}:
                self.blocks.decision_state = "MONITORING"
                self.blocks.execution_state = "READY"
                self.blocks.capture_status = "OBSERVING"
                self.blocks.health_notes.append(f"recovered:{status}")
                self._state = STATE_RUNNING
            elif status in {
                BLOCKED_AMBIGUOUS_STATE,
                CORRUPTION_DETECTED,
                RECOVERY_FAILED,
            }:
                self.blocks.health_notes.append(f"recover_blocked:{status}")
                self._state = STATE_BLOCKED
            else:
                self.blocks.health_notes.append(f"recover_unexpected:{status}")
                self._state = STATE_BLOCKED

    # ------------------------------------------------------------------
    # Read ops
    # ------------------------------------------------------------------

    def read(self, block: str) -> dict[str, Any]:
        with self._lock:
            mapping = {
                "health": lambda: self.blocks.health(
                    control_state=self._state, kill_engaged=self._kill_engaged
                ),
                "storage": self.blocks.storage,
                "provider_capacity": self.blocks.provider_capacity,
                "capture_health": self.blocks.capture_health,
                "decision_lifecycle": self.blocks.decision_lifecycle,
                "execution_lifecycle": self.blocks.execution_lifecycle,
                "reflection_lifecycle": self.blocks.reflection_lifecycle,
                "lesson_gate": self.blocks.lesson_gate,
                "qualification_blocks": self.blocks.qualification_blocks,
            }
            fn = mapping.get(block)
            if fn is None:
                return {"status": DENIED, "reason": "unknown_read_block", "block": block}
            result = fn()
            result["control_state"] = self._state
            result["read_only"] = True
            result["mutation"] = False
            return result

    def attempt_qualification_advance(self, stage: str) -> dict[str, Any]:
        """Explicitly refuse any qualification advance (hard ban)."""
        with self._lock:
            gate = self.gate.check(
                op="qualification_advance",
                state=self._state,
                payload={"advance_qualification": True, "stage": stage},
                kill_engaged=self._kill_engaged,
            )
            return {
                "status": DENIED,
                "reason": gate.get("reason") or "qualification_advance_banned",
                "stage": stage,
                "executed": False,
                "qualification_blocks": self.blocks.qualification_blocks(),
                **PRESERVED_FACTS,
            }

    def attempt_exchange_write(self, **flags: Any) -> dict[str, Any]:
        """Trap: any exchange-write intent is counted and refused."""
        with self._lock:
            payload = dict(flags)
            payload["op"] = "exchange_write_trap"
            gate = self.gate.check(
                op="start",  # op ignored once ban keys hit
                state=self._state,
                payload=payload,
                kill_engaged=self._kill_engaged,
            )
            return {
                "status": DENIED,
                "reason": gate.get("reason"),
                "executed": False,
                "gate": gate,
                **PRESERVED_FACTS,
                "exchange_write_attempt_count": self.gate.exchange_write_attempt_count,
            }
