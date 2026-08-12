"""Demo order adapter stub — write gated by safety gate stage."""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_demo_execution.safety_gate import DemoExecutionSafetyGate


class OrderAdapterError(RuntimeError):
    """Raised when order write is not permitted."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


@dataclass
class OrderIntent:
    symbol: str
    side: str
    qty: float
    margin_usdt: float
    leverage: int
    client_order_id: str = ""
    idempotency_key: str = ""

    def ensure_idempotency_key(self) -> str:
        if self.idempotency_key:
            return self.idempotency_key
        payload = f"{self.symbol}|{self.side}|{self.qty}|{self.client_order_id}"
        self.idempotency_key = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
        return self.idempotency_key


@dataclass
class OrderAdapterResult:
    accepted: bool
    order_id: str = ""
    idempotency_key: str = ""
    dry_run: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "order_id": self.order_id,
            "idempotency_key": self.idempotency_key,
            "dry_run": self.dry_run,
            "reason": self.reason,
        }


@dataclass
class DemoOrderAdapter:
    """Stub adapter — exchange write always disabled until Founder approval."""

    gate: DemoExecutionSafetyGate
    exchange_write_call_count: int = 0
    _idempotency_cache: dict[str, OrderAdapterResult] = field(default_factory=dict)

    def submit(self, intent: OrderIntent, *, dry_run: bool | None = None) -> OrderAdapterResult:
        key = intent.ensure_idempotency_key()
        if key in self._idempotency_cache:
            cached = self._idempotency_cache[key]
            return OrderAdapterResult(
                accepted=cached.accepted,
                order_id=cached.order_id,
                idempotency_key=key,
                dry_run=cached.dry_run,
                reason="idempotent_replay",
            )

        if dry_run is None:
            dry_run = True

        if dry_run or not self.gate.can_write_orders():
            result = OrderAdapterResult(
                accepted=False,
                idempotency_key=key,
                dry_run=True,
                reason="write_disabled_until_gate",
            )
            self._idempotency_cache[key] = result
            return result

        self.exchange_write_call_count += 1
        order_id = f"demo-{uuid.uuid4().hex[:12]}"
        result = OrderAdapterResult(
            accepted=True,
            order_id=order_id,
            idempotency_key=key,
            dry_run=False,
            reason="demo_order_submitted",
        )
        self._idempotency_cache[key] = result
        return result

    def counters(self) -> dict[str, Any]:
        return {
            "exchange_write_call_count": self.exchange_write_call_count,
            "idempotency_cache_size": len(self._idempotency_cache),
            "write_enabled": self.gate.can_write_orders(),
            "timestamp": time.time(),
        }
