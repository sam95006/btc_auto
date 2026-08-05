"""Backpressure and slow-client isolation for public realtime fan-out."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from backend.nexus_public_realtime_transport.constants import (
    BACKPRESSURE_HIGH_WATERMARK,
    BACKPRESSURE_LOW_WATERMARK,
    SLOW_CLIENT_ISOLATE_AFTER_TICKS,
)
from backend.nexus_public_realtime_transport.event_model import PublicStreamEvent


@dataclass
class OfferResult:
    accepted: bool
    action: str  # enqueued | coalesced | dropped | isolated | rejected_isolated
    queue_depth: int
    isolated: bool = False


@dataclass
class ClientDeliveryWindow:
    """Per-client outbound window. Slow clients are isolated, not hub-blocking."""

    client_id: str
    max_depth: int = BACKPRESSURE_HIGH_WATERMARK
    low_watermark: int = BACKPRESSURE_LOW_WATERMARK
    isolate_after_ticks: int = SLOW_CLIENT_ISOLATE_AFTER_TICKS
    queue: Deque[PublicStreamEvent] = field(default_factory=deque)
    enqueued: int = 0
    delivered: int = 0
    dropped: int = 0
    coalesced: int = 0
    backpressure_ticks: int = 0
    isolated: bool = False
    isolation_reason: str | None = None
    forced_polling: bool = False

    @property
    def depth(self) -> int:
        return len(self.queue)

    def offer(self, event: PublicStreamEvent) -> OfferResult:
        if self.isolated:
            self.dropped += 1
            return OfferResult(
                accepted=False,
                action="rejected_isolated",
                queue_depth=self.depth,
                isolated=True,
            )

        # Coalesce consecutive heartbeats to relieve pressure.
        if (
            event.kind == "heartbeat"
            and self.queue
            and self.queue[-1].kind == "heartbeat"
        ):
            self.queue[-1] = event
            self.coalesced += 1
            return OfferResult(accepted=True, action="coalesced", queue_depth=self.depth)

        if self.depth >= self.max_depth:
            self.backpressure_ticks += 1
            # Drop oldest non-control event if possible; else drop incoming.
            dropped_oldest = False
            for idx, pending in enumerate(self.queue):
                if pending.kind not in {"resume_ack", "gap_notice", "stream_end"}:
                    del self.queue[idx]
                    self.dropped += 1
                    dropped_oldest = True
                    break
            if not dropped_oldest:
                self.dropped += 1
                if self.backpressure_ticks >= self.isolate_after_ticks:
                    self.isolate("sustained_backpressure_drop")
                return OfferResult(
                    accepted=False,
                    action="dropped",
                    queue_depth=self.depth,
                    isolated=self.isolated,
                )
            self.queue.append(event)
            self.enqueued += 1
            if self.backpressure_ticks >= self.isolate_after_ticks:
                self.isolate("sustained_backpressure")
            return OfferResult(
                accepted=True,
                action="dropped",  # dropped oldest to make room
                queue_depth=self.depth,
                isolated=self.isolated,
            )

        self.queue.append(event)
        self.enqueued += 1
        if self.depth <= self.low_watermark and self.backpressure_ticks > 0:
            self.backpressure_ticks = max(0, self.backpressure_ticks - 1)
        return OfferResult(accepted=True, action="enqueued", queue_depth=self.depth)

    def drain(self, limit: int = 50) -> list[PublicStreamEvent]:
        out: list[PublicStreamEvent] = []
        while self.queue and len(out) < max(1, int(limit)):
            out.append(self.queue.popleft())
            self.delivered += 1
        if self.depth <= self.low_watermark:
            self.backpressure_ticks = 0
        return out

    def isolate(self, reason: str) -> None:
        if self.isolated:
            return
        self.isolated = True
        self.isolation_reason = reason
        self.forced_polling = True
        self.queue.clear()

    def snapshot(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "queue_depth": self.depth,
            "max_depth": self.max_depth,
            "enqueued": self.enqueued,
            "delivered": self.delivered,
            "dropped": self.dropped,
            "coalesced": self.coalesced,
            "backpressure_ticks": self.backpressure_ticks,
            "isolated": self.isolated,
            "isolation_reason": self.isolation_reason,
            "forced_polling": self.forced_polling,
        }


@dataclass
class FanoutStats:
    clients_registered: int = 0
    clients_isolated: int = 0
    events_fanned_out: int = 0
    offers_dropped: int = 0
    offers_coalesced: int = 0
    fast_clients_unblocked: int = 0


class BackpressureFanout:
    """Fan-out with per-client queues so slow clients cannot stall others."""

    def __init__(
        self,
        *,
        max_depth: int = BACKPRESSURE_HIGH_WATERMARK,
        isolate_after_ticks: int = SLOW_CLIENT_ISOLATE_AFTER_TICKS,
    ) -> None:
        self.max_depth = int(max_depth)
        self.isolate_after_ticks = int(isolate_after_ticks)
        self._clients: dict[str, ClientDeliveryWindow] = {}
        self.stats = FanoutStats()

    def register(self, client_id: str) -> ClientDeliveryWindow:
        if client_id in self._clients:
            return self._clients[client_id]
        window = ClientDeliveryWindow(
            client_id=client_id,
            max_depth=self.max_depth,
            isolate_after_ticks=self.isolate_after_ticks,
        )
        self._clients[client_id] = window
        self.stats.clients_registered += 1
        return window

    def unregister(self, client_id: str) -> None:
        self._clients.pop(client_id, None)

    def get(self, client_id: str) -> ClientDeliveryWindow | None:
        return self._clients.get(client_id)

    def publish(self, event: PublicStreamEvent) -> dict[str, Any]:
        """Offer event to every client window independently."""
        self.stats.events_fanned_out += 1
        results: dict[str, str] = {}
        active_fast = 0
        for cid, window in list(self._clients.items()):
            was_isolated = window.isolated
            offer = window.offer(event)
            results[cid] = offer.action
            if offer.action == "dropped":
                self.stats.offers_dropped += 1
            elif offer.action == "coalesced":
                self.stats.offers_coalesced += 1
            if window.isolated and not was_isolated:
                self.stats.clients_isolated += 1
            if not window.isolated:
                active_fast += 1
        self.stats.fast_clients_unblocked = active_fast
        return {
            "event_seq": event.seq,
            "client_actions": results,
            "active_clients": active_fast,
            "isolated_clients": sum(1 for w in self._clients.values() if w.isolated),
        }

    def drain(self, client_id: str, limit: int = 50) -> list[PublicStreamEvent]:
        window = self._clients.get(client_id)
        if window is None or window.isolated:
            return []
        return window.drain(limit=limit)

    def snapshot(self) -> dict[str, Any]:
        return {
            "stats": {
                "clients_registered": self.stats.clients_registered,
                "clients_isolated": self.stats.clients_isolated,
                "events_fanned_out": self.stats.events_fanned_out,
                "offers_dropped": self.stats.offers_dropped,
                "offers_coalesced": self.stats.offers_coalesced,
                "fast_clients_unblocked": self.stats.fast_clients_unblocked,
            },
            "clients": {cid: w.snapshot() for cid, w in self._clients.items()},
        }
