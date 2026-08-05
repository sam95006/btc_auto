"""Disaster Recovery Control V12 — orchestrates restart / restore / kill switch.

Builds on RuntimeDurabilityV2 + DisasterRecoveryV2. Never silently guesses.
No Demo / exchange write / mainnet surface.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_execution.execution_simulator_v1_1 import AutonomousExecutionSimulatorV11
from backend.nexus_recovery.dr_control_v12.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    HARD_BANS,
    KILL_SWITCH_TRIGGERED,
    PRESERVED_FACTS,
    RECOVERED_EXACT,
    RECOVERED_LAST_KNOWN_GOOD,
    STATE_BLOCKED,
    STATE_COLD,
    STATE_KILLED,
    STATE_RECOVERING,
    STATE_RUNNING,
    STATE_WARM,
)
from backend.nexus_recovery.dr_control_v12.storage_migration import migrate_ledger_schema
from backend.nexus_recovery.dr_v2.recovery import DisasterRecoveryV2
from backend.nexus_runtime.durability_v2.constants import SNAPSHOT_OK
from backend.nexus_runtime.durability_v2.engine import RuntimeDurabilityV2


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ControlStatus:
    state: str
    kill_switch_engaged: bool = False
    kill_switch_reason: str | None = None
    last_recovery: dict[str, Any] = field(default_factory=dict)
    exchange_write_attempt_count: int = 0
    demo_order_count: int = 0
    mainnet_attempt_count: int = 0
    silent_recovery_guess: bool = False
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "kill_switch_engaged": self.kill_switch_engaged,
            "kill_switch_reason": self.kill_switch_reason,
            "last_recovery": dict(self.last_recovery),
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
            "demo_order_count": self.demo_order_count,
            "mainnet_attempt_count": self.mainnet_attempt_count,
            "silent_recovery_guess": self.silent_recovery_guess,
            "detail": dict(self.detail),
            **PRESERVED_FACTS,
            "hard_bans": HARD_BANS,
        }


class DisasterRecoveryControlV12:
    """Founder-private DR control plane for V12-D."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.dr = DisasterRecoveryV2(self.root / "dr")
        self.durability: RuntimeDurabilityV2 = self.dr.durability
        self._lock = threading.RLock()
        self._state = STATE_COLD
        self._kill_switch_engaged = False
        self._kill_switch_reason: str | None = None
        self._last_recovery: dict[str, Any] = {}
        self._intent_owners_path = self.root / "intent_owners.json"
        self._control_meta_path = self.root / "dr_control_v12_meta.json"
        self._exchange_write_attempt_count = 0
        self._load_meta()

    # ------------------------------------------------------------------
    # Meta / intent-owner durability (owner-only duplicate intent)
    # ------------------------------------------------------------------

    def _load_meta(self) -> None:
        if self._control_meta_path.exists():
            try:
                meta = json.loads(self._control_meta_path.read_text(encoding="utf-8"))
                self._state = str(meta.get("state") or STATE_COLD)
                self._kill_switch_engaged = bool(meta.get("kill_switch_engaged"))
                self._kill_switch_reason = meta.get("kill_switch_reason")
                self._last_recovery = dict(meta.get("last_recovery") or {})
            except (OSError, json.JSONDecodeError):
                # Corrupt meta is ambiguous — leave COLD; caller must recover/block.
                self._state = STATE_BLOCKED
                self._last_recovery = {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "control_meta_unreadable",
                    "silent_recovery_guess": False,
                }

    def _persist_meta(self) -> None:
        payload = {
            "state": self._state,
            "kill_switch_engaged": self._kill_switch_engaged,
            "kill_switch_reason": self._kill_switch_reason,
            "last_recovery": self._last_recovery,
            "updated_at": _utc(),
            **PRESERVED_FACTS,
        }
        self._control_meta_path.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    def load_intent_owners(self) -> dict[str, str]:
        if not self._intent_owners_path.exists():
            return {}
        try:
            data = json.loads(self._intent_owners_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            return {str(k): str(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError):
            return {}

    def save_intent_owners(self, owners: dict[str, str]) -> None:
        self._intent_owners_path.write_text(
            json.dumps(owners, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Status / guards
    # ------------------------------------------------------------------

    def status(self) -> ControlStatus:
        with self._lock:
            return ControlStatus(
                state=self._state,
                kill_switch_engaged=self._kill_switch_engaged,
                kill_switch_reason=self._kill_switch_reason,
                last_recovery=dict(self._last_recovery),
                exchange_write_attempt_count=self._exchange_write_attempt_count,
                detail={"root": str(self.root)},
            )

    def _assert_not_killed(self) -> dict[str, Any] | None:
        if self._kill_switch_engaged or self._state == STATE_KILLED:
            return {
                "status": "KILL_SWITCH_BLOCKS",
                "kill_switch_status": KILL_SWITCH_TRIGGERED,
                "kill_switch_reason": self._kill_switch_reason,
                "state": self._state,
                "silent_recovery_guess": False,
                **PRESERVED_FACTS,
            }
        return None

    # ------------------------------------------------------------------
    # Lifecycle: cold / warm / recover
    # ------------------------------------------------------------------

    def seed_events(self, n: int = 10, *, prefix: str = "seed") -> dict[str, Any]:
        blocked = self._assert_not_killed()
        if blocked:
            return blocked
        with self._lock:
            led = self.durability.open_ledger()
            try:
                for i in range(n):
                    r = led.append(
                        aggregate_id=f"{prefix}-{i}",
                        aggregate_type="DECISION",
                        event_type="SEED",
                        source="dr_control_v12",
                        payload={"i": i, "prefix": prefix},
                        idempotency_key=f"{prefix}-{i}",
                    )
                    if r.status not in {"APPENDED", "DUPLICATE_IGNORED"}:
                        return {"status": "FAIL", "append": r.status, "reason": r.reason}
                snap = self.durability.create_snapshot(led)
                count = led.event_count()
            finally:
                led.close()
            if snap.status != SNAPSHOT_OK:
                return {"status": "FAIL", "snapshot": snap.to_dict()}
            self._state = STATE_RUNNING
            self._persist_meta()
            return {
                "status": "PASS",
                "event_count": count,
                "snapshot": snap.to_dict(),
                "state": self._state,
            }

    def cold_stop(self) -> dict[str, Any]:
        """Fully stop — no open handles; process-equivalent cold boundary."""
        with self._lock:
            # Ensure WAL checkpointed by opening+closing if ledger exists.
            if self.durability.ledger_path.exists():
                led = self.durability.open_ledger()
                led.close()
            self._state = STATE_COLD
            self._persist_meta()
            return {"status": "PASS", "state": self._state, "mode": "cold_stop"}

    def warm_stop(self) -> dict[str, Any]:
        """Warm boundary — ledger durable, control marked WARM (restart-in-place)."""
        with self._lock:
            if self.durability.ledger_path.exists():
                led = self.durability.open_ledger()
                led.close()
            self._state = STATE_WARM
            self._persist_meta()
            return {"status": "PASS", "state": self._state, "mode": "warm_stop"}

    def cold_restart(self) -> dict[str, Any]:
        """Cold restart: reload meta, assess, recover if needed, resume or block."""
        blocked = self._assert_not_killed()
        if blocked:
            return blocked
        with self._lock:
            self._load_meta()
            self._state = STATE_RECOVERING
            self._persist_meta()
            outcome = self.dr.recover()
            self._last_recovery = dict(outcome)
            status = outcome.get("status")
            if status in {RECOVERED_EXACT, RECOVERED_LAST_KNOWN_GOOD, "NO_RECOVERY_NEEDED"}:
                self._state = STATE_RUNNING
                self._persist_meta()
                return {
                    "status": "PASS",
                    "mode": "cold_restart",
                    "state": self._state,
                    "recovery": outcome,
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            self._state = STATE_BLOCKED
            self._persist_meta()
            return {
                "status": BLOCKED_AMBIGUOUS_STATE
                if status == BLOCKED_AMBIGUOUS_STATE
                else "FAIL",
                "mode": "cold_restart",
                "state": self._state,
                "recovery": outcome,
                "silent_recovery_guess": False,
                **PRESERVED_FACTS,
            }

    def warm_restart(self) -> dict[str, Any]:
        """Warm restart: reopen healthy live ledger without LKG overwrite."""
        blocked = self._assert_not_killed()
        if blocked:
            return blocked
        with self._lock:
            self._load_meta()
            if self._state not in {STATE_WARM, STATE_RUNNING, STATE_COLD}:
                if self._state == STATE_BLOCKED:
                    return {
                        "status": BLOCKED_AMBIGUOUS_STATE,
                        "reason": "warm_restart_from_blocked",
                        "silent_recovery_guess": False,
                        **PRESERVED_FACTS,
                    }
            assessment = self.dr.assess()
            if assessment.get("status") != "LIVE_HEALTHY":
                # Do not guess — fall through to full recover which may block.
                outcome = self.dr.recover()
                self._last_recovery = dict(outcome)
                if outcome.get("status") not in {
                    RECOVERED_EXACT,
                    RECOVERED_LAST_KNOWN_GOOD,
                    "NO_RECOVERY_NEEDED",
                }:
                    self._state = STATE_BLOCKED
                    self._persist_meta()
                    return {
                        "status": BLOCKED_AMBIGUOUS_STATE,
                        "mode": "warm_restart",
                        "assessment": assessment,
                        "recovery": outcome,
                        "silent_recovery_guess": False,
                        **PRESERVED_FACTS,
                    }
            # Healthy warm path: reopen, verify chain, continue.
            led = self.durability.open_ledger()
            try:
                chain = led.verify_hash_chain()
                count = led.event_count()
                max_seq = led.max_sequence()
            finally:
                led.close()
            if chain.get("ledger_hash_chain_status") != "PASS":
                self._state = STATE_BLOCKED
                self._persist_meta()
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "warm_restart_chain_failed",
                    "chain": chain,
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            self._state = STATE_RUNNING
            self._persist_meta()
            return {
                "status": "PASS",
                "mode": "warm_restart",
                "state": self._state,
                "event_count": count,
                "max_sequence": max_seq,
                "assessment": assessment,
                "silent_recovery_guess": False,
                **PRESERVED_FACTS,
            }

    def restore_lkg(self) -> dict[str, Any]:
        blocked = self._assert_not_killed()
        if blocked:
            return blocked
        with self._lock:
            self._state = STATE_RECOVERING
            self._persist_meta()
            result = self.durability.restore_last_known_good()
            self._last_recovery = {"status": result.status, "detail": result.detail}
            if result.status in {RECOVERED_EXACT, RECOVERED_LAST_KNOWN_GOOD}:
                self._state = STATE_RUNNING
                self._persist_meta()
                return {
                    "status": "PASS",
                    "restore_status": result.status,
                    "detail": result.detail,
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            self._state = STATE_BLOCKED
            self._persist_meta()
            return {
                "status": result.status,
                "detail": result.detail,
                "silent_recovery_guess": False,
                **PRESERVED_FACTS,
            }

    def restore_checkpoint(self) -> dict[str, Any]:
        """Restore via sealed checkpoint — unbound seals block (R2-C-005)."""
        blocked = self._assert_not_killed()
        if blocked:
            return blocked
        with self._lock:
            seal = self.durability.validate_checkpoint_seal()
            if seal.get("status") != "PASS":
                self._state = STATE_BLOCKED
                self._last_recovery = {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": seal.get("reason"),
                    "seal": seal,
                }
                self._persist_meta()
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "seal": seal,
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            # Sealed checkpoint authorizes LKG restore path.
            return self.restore_lkg()

    def reconcile_ledger_tail(self) -> dict[str, Any]:
        """Reconcile LKG position against checksummed snapshot bytes (not live race)."""
        with self._lock:
            if not self.durability.lkg_path.exists():
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "missing_lkg_for_reconcile",
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            pointer = json.loads(self.durability.lkg_path.read_text(encoding="utf-8"))
            if pointer.get("position_source") != "checksummed_main_file":
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "position_source_not_checksummed",
                    "position_source": pointer.get("position_source"),
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            snap = Path(pointer.get("snapshot_path") or "")
            if not snap.exists():
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "snapshot_missing_for_reconcile",
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            file_count, file_max = RuntimeDurabilityV2._count_events_in_sqlite(snap)
            claimed = int(pointer.get("source_ledger_position") or -1)
            match = claimed == file_count
            live_count = None
            if self.durability.ledger_path.exists():
                led = self.durability.open_ledger()
                try:
                    live_count = led.event_count()
                finally:
                    led.close()
            return {
                "status": "PASS" if match else "FAIL",
                "claimed_position": claimed,
                "checksummed_file_count": file_count,
                "checksummed_max_sequence": file_max,
                "live_count": live_count,
                "position_source": pointer.get("position_source"),
                "tail_match": match,
                "silent_recovery_guess": False,
                **PRESERVED_FACTS,
            }

    def kill_switch(self, reason: str = "post_recovery_kill") -> dict[str, Any]:
        with self._lock:
            self._kill_switch_engaged = True
            self._kill_switch_reason = reason or "kill_switch"
            self._state = STATE_KILLED
            self._persist_meta()
            return {
                "status": "PASS",
                "kill_switch_status": KILL_SWITCH_TRIGGERED,
                "kill_switch_reason": self._kill_switch_reason,
                "state": self._state,
                "silent_recovery_guess": False,
                **PRESERVED_FACTS,
            }

    def migrate_storage(self) -> dict[str, Any]:
        blocked = self._assert_not_killed()
        if blocked:
            return blocked
        with self._lock:
            if not self.durability.ledger_path.exists():
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "no_ledger_to_migrate",
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            result = migrate_ledger_schema(self.durability.ledger_path)
            if result.get("status") != "PASS":
                self._state = STATE_BLOCKED
                self._persist_meta()
                return {**result, **PRESERVED_FACTS}
            # After migration, seal must still validate if checkpoint present.
            seal = self.durability.validate_checkpoint_seal()
            if seal.get("status") not in {"PASS"}:
                self._state = STATE_BLOCKED
                self._persist_meta()
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "post_migration_checkpoint_seal_failed",
                    "seal": seal,
                    "migration": result,
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            self._state = STATE_RUNNING
            self._persist_meta()
            return {
                "status": "PASS",
                "migration": result,
                "checkpoint_seal": seal,
                "state": self._state,
                "silent_recovery_guess": False,
                **PRESERVED_FACTS,
            }

    def restore_owner_only_intents(
        self, sim: AutonomousExecutionSimulatorV11 | None = None
    ) -> dict[str, Any]:
        """Restore intent ownership map without requiring order records (V11.1)."""
        owners = self.load_intent_owners()
        sim = sim or AutonomousExecutionSimulatorV11()
        sim.intent_owners.update(owners)
        # Prove duplicate still ignored even if order record absent.
        proofs: list[dict[str, Any]] = []
        for key, oid in owners.items():
            sim.intent_owners[key] = oid
            if oid in sim.orders:
                del sim.orders[oid]
            req = {
                "idempotency_key": key,
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "qty": "0.001",
            }
            out = sim.create_order(req, mark_price="50000")
            audit = sim.audit[-1] if sim.audit else {}
            proofs.append(
                {
                    "idempotency_key": key,
                    "status": out.get("status"),
                    "state": out.get("state"),
                    "order_record_present": bool(audit.get("order_record_present")),
                }
            )
            if out.get("status") != "DUPLICATE_IGNORED":
                return {
                    "status": "FAIL",
                    "reason": "owner_only_duplicate_not_ignored",
                    "proofs": proofs,
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
            if out.get("state") != "RECOVERED_OWNER_WITHOUT_ORDER":
                return {
                    "status": "FAIL",
                    "reason": "expected_recovered_owner_without_order_state",
                    "proofs": proofs,
                    "silent_recovery_guess": False,
                    **PRESERVED_FACTS,
                }
        return {
            "status": "PASS",
            "owners_restored": len(owners),
            "proofs": proofs,
            "silent_recovery_guess": False,
            **PRESERVED_FACTS,
        }
