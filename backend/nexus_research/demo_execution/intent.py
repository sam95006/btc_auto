"""Demo order execution — intent and authorization.

DemoOrderIntent: declares what the system *wants* to do.
DemoOrderAuthorization: one-time hashed token, atomic consume,
  bound to symbol/side/qty/leverage/expiry, replay rejected.

order_sent is ALWAYS False in this module.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False


class WriteNotAuthorizedError(Exception):
    """Raised when a write operation is attempted without valid authorization."""


class NotAuthorizedError(Exception):
    """Raised when authorization is missing or invalid."""


class AuthorizationReplayError(Exception):
    """Raised when a consumed authorization token is replayed."""


@dataclass(frozen=True)
class DemoOrderIntent:
    """Declares the intent to place a demo order.

    This is a *request* — it does NOT authorize execution.
    """

    intent_id: str
    symbol: str
    side: str  # Buy | Sell
    qty: float
    leverage: int
    entry_price: float
    stop_loss_price: float
    take_profit_price: float | None
    risk_tier: str
    client_order_id: str
    source: str  # "strategy_evaluator" | "fixture" | "manual"
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    order_sent: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.order_sent:
            raise ValueError("order_sent must always be False")

    def binding_key(self) -> str:
        """Deterministic key that binds authorization to this intent."""
        raw = f"{self.symbol}:{self.side}:{self.qty}:{self.leverage}:{self.client_order_id}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "intentId": self.intent_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "leverage": self.leverage,
            "entryPrice": self.entry_price,
            "stopLossPrice": self.stop_loss_price,
            "takeProfitPrice": self.take_profit_price,
            "riskTier": self.risk_tier,
            "clientOrderId": self.client_order_id,
            "source": self.source,
            "createdAtMs": self.created_at_ms,
            "orderSent": False,
        }


@dataclass
class DemoOrderAuthorization:
    """One-time hashed token, atomic consume, bound to intent fields.

    Once consumed, any attempt to re-use raises AuthorizationReplayError.
    Expired tokens cannot authorize.
    """

    token_hash: str
    intent_binding_key: str
    symbol: str
    side: str
    qty: float
    leverage: int
    expires_at_ms: int
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    consumed: bool = False
    consumed_at_ms: int | None = None
    order_sent: bool = field(default=False, init=False)

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @staticmethod
    def create_for_intent(
        intent: DemoOrderIntent,
        *,
        ttl_ms: int = 300_000,
    ) -> DemoOrderAuthorization:
        """Create authorization token bound to a specific intent."""
        raw_token = secrets.token_hex(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = int(time.time() * 1000)
        return DemoOrderAuthorization(
            token_hash=token_hash,
            intent_binding_key=intent.binding_key(),
            symbol=intent.symbol,
            side=intent.side,
            qty=intent.qty,
            leverage=intent.leverage,
            expires_at_ms=now + ttl_ms,
            created_at_ms=now,
        )

    def is_expired(self) -> bool:
        return int(time.time() * 1000) > self.expires_at_ms

    def validate_binding(self, intent: DemoOrderIntent) -> bool:
        """Check that this auth is bound to the given intent."""
        return (
            self.intent_binding_key == intent.binding_key()
            and self.symbol == intent.symbol
            and self.side == intent.side
            and self.qty == intent.qty
            and self.leverage == intent.leverage
        )

    def consume(self, intent: DemoOrderIntent) -> None:
        """Atomically consume this authorization. Thread-safe, one-shot.

        Raises AuthorizationReplayError if already consumed.
        Raises NotAuthorizedError if expired or binding mismatch.
        """
        with self._lock:
            if self.consumed:
                raise AuthorizationReplayError(
                    f"Authorization {self.token_hash[:12]}... already consumed "
                    f"at {self.consumed_at_ms}"
                )
            if self.is_expired():
                raise NotAuthorizedError(
                    f"Authorization expired at {self.expires_at_ms}"
                )
            if not self.validate_binding(intent):
                raise NotAuthorizedError(
                    f"Authorization binding mismatch: "
                    f"expected {self.intent_binding_key[:12]}..., "
                    f"got {intent.binding_key()[:12]}..."
                )
            self.consumed = True
            self.consumed_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokenHashPrefix": self.token_hash[:12],
            "intentBindingKeyPrefix": self.intent_binding_key[:12],
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "leverage": self.leverage,
            "expiresAtMs": self.expires_at_ms,
            "createdAtMs": self.created_at_ms,
            "consumed": self.consumed,
            "consumedAtMs": self.consumed_at_ms,
            "orderSent": False,
        }
