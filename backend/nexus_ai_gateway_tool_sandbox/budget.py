"""Budget policy, request cache, and dedupe for V18-E gateway."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_ai_gateway_tool_sandbox.constants import (
    DEFAULT_BUDGET_CALLS,
    DEFAULT_BUDGET_TOKENS,
    DEFAULT_CACHE_TTL_S,
)
from backend.nexus_ai_gateway_tool_sandbox.contracts import GatewayResponse


@dataclass
class BudgetPolicy:
    max_tokens: int = DEFAULT_BUDGET_TOKENS
    max_calls: int = DEFAULT_BUDGET_CALLS
    tokens_used: int = 0
    calls_used: int = 0

    def remaining_tokens(self) -> int:
        return max(0, self.max_tokens - self.tokens_used)

    def remaining_calls(self) -> int:
        return max(0, self.max_calls - self.calls_used)

    def can_spend(self, *, tokens: int = 0) -> bool:
        if self.calls_used >= self.max_calls:
            return False
        if self.tokens_used + max(0, tokens) > self.max_tokens:
            return False
        return True

    def record(self, *, tokens: int = 0) -> None:
        self.calls_used += 1
        self.tokens_used += max(0, tokens)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "max_calls": self.max_calls,
            "tokens_used": self.tokens_used,
            "calls_used": self.calls_used,
            "remaining_tokens": self.remaining_tokens(),
            "remaining_calls": self.remaining_calls(),
        }


@dataclass
class CacheEntry:
    fingerprint: str
    response: GatewayResponse
    stored_at: float
    ttl_s: float

    def expired(self, now: float | None = None) -> bool:
        ts = time.monotonic() if now is None else now
        return (ts - self.stored_at) > self.ttl_s


@dataclass
class ResponseCache:
    ttl_s: float = DEFAULT_CACHE_TTL_S
    _store: dict[str, CacheEntry] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def get(self, fingerprint: str) -> GatewayResponse | None:
        entry = self._store.get(fingerprint)
        if entry is None:
            self.misses += 1
            return None
        if entry.expired():
            self._store.pop(fingerprint, None)
            self.misses += 1
            return None
        self.hits += 1
        cached = entry.response
        cached.cache_hit = True
        return cached

    def put(self, fingerprint: str, response: GatewayResponse) -> None:
        self._store[fingerprint] = CacheEntry(
            fingerprint=fingerprint,
            response=response,
            stored_at=time.monotonic(),
            ttl_s=self.ttl_s,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ttl_s": self.ttl_s,
            "size": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
        }


@dataclass
class InFlightDedupe:
    """Collapse identical in-flight fingerprints — no busy re-dispatch."""

    _inflight: dict[str, GatewayResponse | None] = field(default_factory=dict)
    hits: int = 0

    def begin(self, fingerprint: str) -> GatewayResponse | None | bool:
        """
        Returns:
          - GatewayResponse if a prior identical request already finished and
            is still marked inflight (rare),
          - True if another call is currently executing (caller should treat
            as DEDUPE_HIT / wait for shared result — we return a marker),
          - False if this caller owns the slot.
        """
        if fingerprint in self._inflight:
            self.hits += 1
            existing = self._inflight[fingerprint]
            if existing is not None:
                existing.dedupe_hit = True
                return existing
            return True
        self._inflight[fingerprint] = None
        return False

    def finish(self, fingerprint: str, response: GatewayResponse) -> None:
        self._inflight[fingerprint] = response

    def clear(self, fingerprint: str) -> None:
        self._inflight.pop(fingerprint, None)

    def to_dict(self) -> dict[str, Any]:
        return {"inflight": len(self._inflight), "hits": self.hits}
