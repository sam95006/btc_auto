"""Audit log helpers for subscription product boundary events."""
from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from backend.nexus_public_subscription_boundary.hard_bans import (
    is_forbidden_product,
    refuse_forbidden_product,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"sub_aud_{uuid.uuid4().hex[:16]}"


@dataclass
class SubscriptionAuditEvent:
    event_id: str
    account_id: Optional[str]
    action: str
    product_id: Optional[str]
    result: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)


class SubscriptionAuditLog:
    """In-memory audit trail for product authorize / deny / grant attempts."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.events: list[SubscriptionAuditEvent] = []

    def record(
        self,
        *,
        action: str,
        result: str,
        account_id: Optional[str] = None,
        product_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SubscriptionAuditEvent:
        meta = dict(metadata or {})
        meta.setdefault("execution_controls", False)
        meta.setdefault("live_billing", False)
        if product_id and is_forbidden_product(product_id) and result == "granted":
            refuse_forbidden_product(product_id)
        event = SubscriptionAuditEvent(
            event_id=_new_id(),
            account_id=account_id,
            action=action,
            product_id=product_id,
            result=result,
            metadata=meta,
        )
        with self._lock:
            self.events.append(event)
        return deepcopy(event)

    def list_events(self, *, account_id: Optional[str] = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.events
            if account_id:
                rows = [e for e in rows if e.account_id == account_id]
            return [asdict(e) for e in rows]

    def denied_forbidden_count(self) -> int:
        with self._lock:
            return sum(
                1
                for e in self.events
                if e.result == "denied"
                and e.product_id
                and is_forbidden_product(e.product_id)
            )

    def granted_execution_control_count(self) -> int:
        """Must remain 0 — any grant of forbidden/execution product is a defect."""
        with self._lock:
            return sum(
                1
                for e in self.events
                if e.result in {"granted", "authorized"}
                and e.product_id
                and is_forbidden_product(e.product_id)
            )


_default_log: Optional[SubscriptionAuditLog] = None


def get_default_audit_log() -> SubscriptionAuditLog:
    global _default_log
    if _default_log is None:
        _default_log = SubscriptionAuditLog()
    return _default_log
