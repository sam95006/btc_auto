"""Client session protocol: reconnect, backoff, polling fallback, OOO/dup handling."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from backend.nexus_public_realtime_transport.backoff import BackoffState
from backend.nexus_public_realtime_transport.event_model import PublicStreamEvent, build_event
from backend.nexus_public_realtime_transport.sequence_buffer import SequenceBuffer
from backend.nexus_public_realtime_transport.staleness import classify_staleness


@dataclass
class ClientSessionStats:
    delivered: int = 0
    duplicates_suppressed: int = 0
    out_of_order_buffered: int = 0
    reconnects: int = 0
    polling_fallbacks: int = 0
    heartbeats: int = 0


@dataclass
class PublicRealtimeClientSession:
    """Transport-agnostic client session for public streams."""

    stream_id: str = "public.decision.feed"
    prefer_transport: str = "sse"  # sse | websocket | polling
    buffer: SequenceBuffer = field(default_factory=SequenceBuffer)
    backoff: BackoffState = field(default_factory=BackoffState)
    stats: ClientSessionStats = field(default_factory=ClientSessionStats)
    resume_token: str | None = None
    last_event_ts_ms: int | None = None
    active_transport: str = "sse"
    _handlers: list[Callable[[PublicStreamEvent], None]] = field(default_factory=list)

    def on_event(self, handler: Callable[[PublicStreamEvent], None]) -> None:
        self._handlers.append(handler)

    def ingest(self, event: PublicStreamEvent) -> list[PublicStreamEvent]:
        if event.kind == "heartbeat":
            self.stats.heartbeats += 1
            self.last_event_ts_ms = event.ts_ms
            return []
        if event.kind == "resume_ack":
            return []
        result = self.buffer.apply(event)
        if result.reason == "duplicate_event_id" or result.reason == "duplicate_or_stale_seq":
            self.stats.duplicates_suppressed += result.duplicates_suppressed
            return []
        if result.reason == "buffered_out_of_order":
            self.stats.out_of_order_buffered += 1
            return []
        delivered = result.delivered
        for evt in delivered:
            self.stats.delivered += 1
            self.last_event_ts_ms = evt.ts_ms
            for handler in self._handlers:
                handler(evt)
        return delivered

    def ingest_dict(self, raw: dict[str, Any]) -> list[PublicStreamEvent]:
        evt = build_event(
            seq=int(raw["seq"]),
            kind=str(raw["kind"]),
            topic=str(raw.get("topic") or self.stream_id),
            payload=dict(raw.get("payload") or {}),
            ts_ms=int(raw.get("ts_ms") or 0) or None,
            event_id=str(raw.get("event_id") or f"{raw.get('topic')}:{raw['seq']}"),
        )
        if raw.get("resume_token"):
            self.resume_token = str(raw["resume_token"])
        return self.ingest(evt)

    def note_disconnect(self) -> float:
        self.stats.reconnects += 1
        return self.backoff.next_delay()

    def note_connected(self) -> None:
        self.backoff.reset()

    def fallback_to_polling(self) -> str:
        self.stats.polling_fallbacks += 1
        self.active_transport = "polling"
        return self.active_transport

    def choose_transport(self, *, sse_available: bool, ws_available: bool) -> str:
        if self.prefer_transport == "polling":
            self.active_transport = "polling"
            return self.active_transport
        if self.prefer_transport == "websocket" and ws_available:
            self.active_transport = "websocket"
            return self.active_transport
        if self.prefer_transport == "sse" and sse_available:
            self.active_transport = "sse"
            return self.active_transport
        if sse_available:
            self.active_transport = "sse"
            return self.active_transport
        if ws_available:
            self.active_transport = "websocket"
            return self.active_transport
        return self.fallback_to_polling()

    def staleness(self) -> dict[str, Any]:
        return classify_staleness(last_event_ts_ms=self.last_event_ts_ms)

    def flush_gaps(self) -> list[PublicStreamEvent]:
        result = self.buffer.flush_with_gap_notice()
        for evt in result.delivered:
            self.stats.delivered += 1
            for handler in self._handlers:
                handler(evt)
        return result.delivered

    def snapshot(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "active_transport": self.active_transport,
            "resume_token_present": self.resume_token is not None,
            "buffer": self.buffer.snapshot(),
            "stats": {
                "delivered": self.stats.delivered,
                "duplicates_suppressed": self.stats.duplicates_suppressed,
                "out_of_order_buffered": self.stats.out_of_order_buffered,
                "reconnects": self.stats.reconnects,
                "polling_fallbacks": self.stats.polling_fallbacks,
                "heartbeats": self.stats.heartbeats,
            },
            "staleness": self.staleness(),
            "backoff_attempt": self.backoff.attempt,
        }


def replay_into_session(
    session: PublicRealtimeClientSession,
    events: Iterable[PublicStreamEvent | dict[str, Any]],
) -> dict[str, Any]:
    for item in events:
        if isinstance(item, PublicStreamEvent):
            session.ingest(item)
        else:
            session.ingest_dict(item)
    return session.snapshot()
