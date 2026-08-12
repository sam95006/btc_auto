"""One-shot Founder smoke-order approval nonce — in-memory only, never logged."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any


SMOKE_GATE_NAME = "FIRST_BYBIT_DEMO_SMOKE_ORDER"
NONCE_TTL_SEC = 15 * 60
MAX_ORDER_CREATE = 1
MAX_OPEN_POSITION = 1
MAX_PENDING_ORDER = 1
APPROVED_MARGIN_CAP = 20.0
SMOKE_HOLD_MAX_SEC = 10 * 60
SMOKE_HOLD_DEFAULT_SEC = 90  # within max; early time-stop for lifecycle validation
SMOKE_SYMBOL_WHITELIST = frozenset({"BTCUSDT", "ETHUSDT"})


@dataclass
class FounderSmokeNonce:
    """Opaque approval token — store hash only; plaintext returned once to caller."""

    nonce_hash: str
    deployment_id: str
    account_epoch: str
    dry_run_intent_id: str
    issued_at: float
    expires_at: float
    consumed: bool = False
    orders_created: int = 0

    def is_expired(self, now: float | None = None) -> bool:
        return (now or time.time()) > self.expires_at


@dataclass
class FounderSmokeApprovalStore:
    """Process-local one-shot write window. Never persist nonce plaintext."""

    deployment_id: str = ""
    gate_name: str = SMOKE_GATE_NAME
    approval_active: bool = False
    new_order_blocked: bool = True
    maximum_order_create_count: int = 0
    maximum_open_position_count: int = MAX_OPEN_POSITION
    maximum_pending_order_count: int = MAX_PENDING_ORDER
    approved_margin_cap: float = APPROVED_MARGIN_CAP
    _active: FounderSmokeNonce | None = field(default=None, repr=False)
    _history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.deployment_id:
            self.deployment_id = (
                os.environ.get("NEXUS_DEPLOYMENT_ID")
                or os.environ.get("ZEABUR_DEPLOYMENT_ID")
                or os.environ.get("GITHUB_SHA")
                or f"local-{int(time.time())}"
            )[:64]

    def env_gate_approved(self) -> bool:
        """Env may authorize the window; autonomous must stay false."""
        if (os.environ.get("DEMO_AUTONOMOUS_ENABLED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return False
        if (os.environ.get("FOUNDER_SMOKE_ALREADY_EXECUTED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return False
        gate = (os.environ.get("FOUNDER_GATE") or "").strip()
        approved = (os.environ.get("FOUNDER_SMOKE_ORDER_APPROVED") or "").strip().lower()
        return gate == SMOKE_GATE_NAME and approved in {"1", "true", "yes", "on"}

    def mark_executed_persisted(self) -> None:
        """Best-effort marker so operators can unset approval env after smoke."""
        self._history.append({"event": "smoke_executed_marker"})
        self.close_window("smoke_executed")

    def issue(
        self,
        *,
        account_epoch: str,
        dry_run_intent_id: str,
        deployment_id: str | None = None,
    ) -> str:
        """Create one-shot nonce. Returns plaintext once — caller must not log it."""
        if not self.env_gate_approved():
            raise RuntimeError("SMOKE_ORDER_BLOCKED:founder_gate_not_approved")
        if not account_epoch or account_epoch in {"epoch-unknown", "MISSING", "UNKNOWN"}:
            raise RuntimeError("SMOKE_ORDER_BLOCKED:account_epoch_invalid")
        if not dry_run_intent_id:
            raise RuntimeError("SMOKE_ORDER_BLOCKED:dry_run_intent_missing")

        # Invalidate any previous unused nonce.
        if self._active and not self._active.consumed:
            self._active.consumed = True
            self._history.append({"event": "nonce_superseded"})

        plaintext = secrets.token_urlsafe(32)
        nonce_hash = _hash_nonce(plaintext)
        now = time.time()
        self._active = FounderSmokeNonce(
            nonce_hash=nonce_hash,
            deployment_id=(deployment_id or self.deployment_id)[:64],
            account_epoch=account_epoch,
            dry_run_intent_id=dry_run_intent_id,
            issued_at=now,
            expires_at=now + NONCE_TTL_SEC,
        )
        self.approval_active = True
        self.new_order_blocked = False
        self.maximum_order_create_count = MAX_ORDER_CREATE
        self._history.append(
            {
                "event": "nonce_issued",
                "deployment_id": self._active.deployment_id,
                "account_epoch": account_epoch,
                "dry_run_intent_id": dry_run_intent_id,
                "expires_at": self._active.expires_at,
                # never store plaintext / hash in history for safety
            }
        )
        return plaintext

    def consume(
        self,
        plaintext: str,
        *,
        account_epoch: str,
        dry_run_intent_id: str,
        deployment_id: str | None = None,
    ) -> bool:
        active = self._active
        if active is None:
            return False
        if active.consumed or active.is_expired():
            self._close_window("expired_or_consumed")
            return False
        if not hmac.compare_digest(active.nonce_hash, _hash_nonce(plaintext)):
            self._history.append({"event": "nonce_mismatch"})
            return False
        dep = (deployment_id or self.deployment_id)[:64]
        if active.deployment_id != dep:
            self._history.append({"event": "deployment_mismatch"})
            return False
        if active.account_epoch != account_epoch:
            self._history.append({"event": "epoch_mismatch"})
            return False
        if active.dry_run_intent_id != dry_run_intent_id:
            self._history.append({"event": "intent_mismatch"})
            return False
        active.consumed = True
        self._history.append({"event": "nonce_consumed"})
        return True

    def register_order_create(self) -> None:
        if self._active is None:
            raise RuntimeError("SMOKE_ORDER_BLOCKED:no_active_nonce")
        if self._active.orders_created >= MAX_ORDER_CREATE:
            raise RuntimeError("DUPLICATE_ORDER_BLOCKED")
        if self.maximum_order_create_count <= 0:
            raise RuntimeError("SMOKE_ORDER_BLOCKED:create_count_exhausted")
        self._active.orders_created += 1
        self.maximum_order_create_count = max(0, self.maximum_order_create_count - 1)

    def close_window(self, reason: str = "completed") -> None:
        self._close_window(reason)

    def _close_window(self, reason: str) -> None:
        self.approval_active = False
        self.new_order_blocked = True
        self.maximum_order_create_count = 0
        if self._active and not self._active.consumed:
            self._active.consumed = True
        self._history.append({"event": "window_closed", "reason": reason})

    def can_write(self) -> bool:
        if self.new_order_blocked or not self.approval_active:
            return False
        if self._active is None or self._active.is_expired():
            return False
        if self.maximum_order_create_count <= 0:
            return False
        return self.env_gate_approved()

    def snapshot(self) -> dict[str, Any]:
        active = self._active
        return {
            "gate_name": self.gate_name,
            "env_gate_approved": self.env_gate_approved(),
            "approval_active": self.approval_active,
            "new_order_blocked": self.new_order_blocked,
            "maximum_order_create_count": self.maximum_order_create_count,
            "maximum_open_position_count": self.maximum_open_position_count,
            "maximum_pending_order_count": self.maximum_pending_order_count,
            "approved_margin_cap": self.approved_margin_cap,
            "deployment_id": self.deployment_id,
            "nonce_present": active is not None and not active.consumed and not active.is_expired(),
            "nonce_consumed": bool(active and active.consumed),
            "orders_created": active.orders_created if active else 0,
            "history_count": len(self._history),
            # never expose nonce / hash
        }


def _hash_nonce(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
