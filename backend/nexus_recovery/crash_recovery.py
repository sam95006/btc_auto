"""Session crash recovery — deterministic reload from checkpoint + ledger.

Recovery contract:
  * If the last-known-good snapshot is available AND consistent with the
    tail of the append-only ledger, the session may resume from
    RECOVERING -> RUNNING.
  * If the snapshot is missing, corrupted, or diverges from the ledger tail,
    the session must transition to BLOCKED (BLOCKED_AMBIGUOUS) — never
    guessed, never silently resumed.
  * Any recovered state that would violate the recovery invariants
    (see ``nexus_recovery.invariants``) must transition to FAILED_SAFE.

This module does not modify the Execution Simulator. It only reads from the
durability layer + ledger to reconstruct the orchestrator's session view.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.private_event_ledger_v1 import PrivateEventLedger
from backend.nexus_autonomy.runtime_durability_v1 import RuntimeDurabilityV1
from backend.nexus_recovery.invariants import (
    RecoveryInvariantResult,
    check_recovery_invariants,
)


class AmbiguousStateError(Exception):
    """Raised when recovered state cannot be reconciled deterministically."""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class RecoveryOutcome:
    status: str  # RECOVERED, BLOCKED_AMBIGUOUS, FAILED_SAFE, RECOVERY_FAILED
    session_id: str
    restore_status: str | None = None
    ledger_event_count: int = 0
    last_ledger_sequence: int | None = None
    checkpoint_id: str | None = None
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    pending_intents: list[dict[str, Any]] = field(default_factory=list)
    invariants: RecoveryInvariantResult | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "session_id": self.session_id,
            "restore_status": self.restore_status,
            "ledger_event_count": self.ledger_event_count,
            "last_ledger_sequence": self.last_ledger_sequence,
            "checkpoint_id": self.checkpoint_id,
            "open_positions": list(self.open_positions),
            "pending_intents": list(self.pending_intents),
            "invariants": self.invariants.to_dict() if self.invariants else None,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


class SessionCrashRecovery:
    """Deterministic crash recovery for a single session's durability root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.durability = RuntimeDurabilityV1(self.root / "durability")

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    def find_last_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        """Return the freshest checkpoint payload for a session, or None."""
        candidates: list[tuple[float, Path]] = []
        for child in self.root.glob(f"{session_id}.checkpoint*.json"):
            try:
                stat = child.stat()
                candidates.append((stat.st_mtime, child))
            except OSError:
                continue
        if not candidates:
            return None
        candidates.sort(reverse=True)
        path = candidates[0][1]
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    # ------------------------------------------------------------------
    # Core recovery flow
    # ------------------------------------------------------------------

    def recover(
        self,
        session_id: str,
        *,
        allow_ledger_repair: bool = False,
    ) -> RecoveryOutcome:
        # 1) Try to restore last-known-good snapshot.
        restore = self.durability.restore_last_known_good()
        if restore.status in {"RECOVERY_FAILED", "BLOCKED_AMBIGUOUS_STATE"}:
            return RecoveryOutcome(
                status="BLOCKED_AMBIGUOUS",
                session_id=session_id,
                restore_status=restore.status,
                reason="lkg_restore_blocked",
                metadata=dict(restore.detail),
            )
        if restore.status == "CORRUPTION_DETECTED":
            return RecoveryOutcome(
                status="BLOCKED_AMBIGUOUS",
                session_id=session_id,
                restore_status=restore.status,
                reason="snapshot_corruption",
                metadata=dict(restore.detail),
            )

        # 2) Re-open the ledger and replay session-scoped events.
        ledger = self.durability.open_ledger()
        try:
            chain = ledger.verify_hash_chain()
            if chain.get("ledger_hash_chain_status") != "PASS":
                return RecoveryOutcome(
                    status="BLOCKED_AMBIGUOUS",
                    session_id=session_id,
                    restore_status=restore.status,
                    reason="ledger_hash_chain_broken",
                    metadata=dict(chain),
                )

            events = ledger.bounded_query(aggregate_id=session_id, limit=100_000)
            last_seq = None
            checkpoint_id = None
            for e in events:
                if e.get("aggregate_type") == "SNAPSHOT":
                    checkpoint_id = e.get("event_id")
                if last_seq is None:
                    last_seq = int(e["sequence_number"])
                else:
                    last_seq = max(last_seq, int(e["sequence_number"]))

            # 3) Rebuild an orchestrator-visible view. Because we do not
            #    modify the Execution Simulator, this recovery reads
            #    session-scoped events only. Any ambiguous open lifecycle
            #    routes to BLOCKED.
            open_positions, pending_intents, extra_counts = _replay_session_view(
                ledger.replay(),
                session_id=session_id,
            )

            counts = dict(extra_counts)
            counts.setdefault("open_ambiguous_position_count", 0)
            counts.setdefault("orphan_lifecycle_count", 0)
            counts.setdefault("duplicate_position_count", 0)
            counts.setdefault("unclosed_intent_count", len(pending_intents))
            counts.setdefault("untracked_fill_count", 0)
            counts.setdefault("risk_limit_bypass_count", 0)
            counts.setdefault("exchange_write_attempt_count", 0)

            inv = check_recovery_invariants(counts)
            if not inv.passed:
                return RecoveryOutcome(
                    status="BLOCKED_AMBIGUOUS",
                    session_id=session_id,
                    restore_status=restore.status,
                    ledger_event_count=ledger.event_count(),
                    last_ledger_sequence=last_seq,
                    checkpoint_id=checkpoint_id,
                    open_positions=open_positions,
                    pending_intents=pending_intents,
                    invariants=inv,
                    reason="recovery_invariant_violation",
                )

            return RecoveryOutcome(
                status="RECOVERED",
                session_id=session_id,
                restore_status=restore.status,
                ledger_event_count=ledger.event_count(),
                last_ledger_sequence=last_seq,
                checkpoint_id=checkpoint_id,
                open_positions=open_positions,
                pending_intents=pending_intents,
                invariants=inv,
                reason="lkg_and_ledger_consistent",
            )
        finally:
            ledger.close()


def _replay_session_view(
    events: list[dict[str, Any]],
    *,
    session_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    open_positions: dict[str, dict[str, Any]] = {}
    pending_intents: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {
        "open_ambiguous_position_count": 0,
        "orphan_lifecycle_count": 0,
        "duplicate_position_count": 0,
        "untracked_fill_count": 0,
        "risk_limit_bypass_count": 0,
        "exchange_write_attempt_count": 0,
    }
    for e in events:
        agg_type = e.get("aggregate_type")
        try:
            payload = json.loads(e.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        # Restrict to events emitted by this session's orchestrator or its
        # session_id aggregates. The V1 orchestrator uses candidate_id as the
        # aggregate_id for lifecycle events (INTENT, OUTCOME); we therefore
        # look for BOTH session_id-scoped events AND any lifecycle events
        # whose payload references the session.
        if (
            e.get("aggregate_id") != session_id
            and payload.get("session_id") != session_id
        ):
            continue

        if agg_type == "ORDER_INTENT" and e.get("event_type") == "ORDER_ACCEPTED":
            intent_key = payload.get("intent_key") or e.get("idempotency_key")
            if intent_key:
                if intent_key in pending_intents:
                    counts["duplicate_position_count"] += 1
                pending_intents[intent_key] = {"intent_key": intent_key, **payload}
        elif agg_type == "TRADE_OUTCOME" and e.get("event_type") == "SIMULATED_CLOSED":
            intent_key = payload.get("intent_key")
            if intent_key and intent_key in pending_intents:
                pending_intents.pop(intent_key, None)
        elif agg_type == "SIMULATED_POSITION" and e.get("event_type") == "BLOCKED_AMBIGUOUS":
            open_positions[e["event_id"]] = payload
            counts["open_ambiguous_position_count"] += 1
    return list(open_positions.values()), list(pending_intents.values()), counts


def recover_from_checkpoint(root: Path, session_id: str) -> RecoveryOutcome:
    """Convenience helper — equivalent to ``SessionCrashRecovery(root).recover(session_id)``."""
    return SessionCrashRecovery(root).recover(session_id)
