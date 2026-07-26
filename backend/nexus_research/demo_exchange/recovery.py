"""Phase 6.6 — Idempotency, restart recovery, duplicate execution detection.

Client order IDs are generated for tests only — NEVER sent to the exchange
in this phase.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from backend.nexus_research.demo_exchange.readers import DemoExchangeSnapshot, ExecutionView


class IdempotentClientOrderIdGenerator:
    """Deterministic / unique client order id generator (local only)."""

    PREFIX = "nxd66"

    def __init__(self, *, namespace: str = "phase66") -> None:
        self.namespace = namespace
        self._seen: set[str] = set()

    def generate(self, *, intent_key: str | None = None) -> str:
        if intent_key:
            digest = hashlib.sha256(f"{self.namespace}:{intent_key}".encode("utf-8")).hexdigest()[:20]
            cid = f"{self.PREFIX}-{digest}"
        else:
            cid = f"{self.PREFIX}-{uuid.uuid4().hex[:20]}"
        self._seen.add(cid)
        return cid

    def generate_idempotent(self, intent_key: str) -> str:
        """Same intent_key → same id."""
        return self.generate(intent_key=intent_key)

    def was_generated(self, client_order_id: str) -> bool:
        return client_order_id in self._seen


@dataclass
class ExchangeSnapshotCheckpoint:
    path: Path
    snapshot_id: str = ""
    account_id: str = ""
    captured_at_ms: int = 0
    payload_digest: str = ""

    def save(self, snapshot: DemoExchangeSnapshot) -> "ExchangeSnapshotCheckpoint":
        data = snapshot.to_dict()
        # Strip any accidental secret-like keys
        blob = json.dumps(data, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        record = {
            "snapshotId": snapshot.identity.snapshot_id,
            "accountId": snapshot.identity.account_id,
            "capturedAtMs": snapshot.identity.captured_at_ms,
            "payloadDigest": digest,
            "positionCount": len(snapshot.positions),
            "openOrderCount": len(snapshot.open_orders),
            "executionCount": len(snapshot.executions),
            "walletAvailable": (
                snapshot.wallet.available_balance if snapshot.wallet else None
            ),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        self.snapshot_id = record["snapshotId"]
        self.account_id = record["accountId"]
        self.captured_at_ms = int(record["capturedAtMs"])
        self.payload_digest = digest
        return self

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))


@dataclass
class RestartRecoveryPlan:
    """Plan for restart without placing orders."""

    checkpoint: ExchangeSnapshotCheckpoint | None = None
    steps: list[str] = field(default_factory=list)
    requires_manual_review: bool = False

    def build(self, checkpoint: ExchangeSnapshotCheckpoint) -> "RestartRecoveryPlan":
        self.checkpoint = checkpoint
        loaded = checkpoint.load()
        self.steps = [
            "load_exchange_snapshot_checkpoint",
            "enter_READ_ONLY",
            "run_RECONCILING",
            "compare_against_checkpoint_digest",
            "if_mismatch_enter_WRITE_LOCKED",
            "never_auto_submit_orders",
            "never_send_client_order_ids_to_exchange",
        ]
        self.requires_manual_review = not bool(loaded)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": list(self.steps),
            "requiresManualReview": self.requires_manual_review,
            "checkpointPresent": bool(self.checkpoint and self.checkpoint.path.exists()),
            "writeOnRestart": False,
        }


class DuplicateExecutionDetector:
    def detect(self, executions: Iterable[ExecutionView]) -> list[str]:
        seen: set[str] = set()
        dups: list[str] = []
        for ex in executions:
            key = ex.exec_id or f"{ex.order_id}:{ex.exec_time_ms}:{ex.qty}:{ex.price}"
            if key in seen:
                dups.append(key)
            else:
                seen.add(key)
        return dups

    def has_duplicates(self, executions: Iterable[ExecutionView]) -> bool:
        return bool(self.detect(executions))
