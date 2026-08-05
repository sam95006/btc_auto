"""In-memory public stream hub — SSE / WS / polling over the same buffer."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Generator, Iterator

from backend.nexus_public_realtime_transport.backpressure import BackpressureFanout
from backend.nexus_public_realtime_transport.constants import (
    ALLOWED_EVENT_KINDS,
    BACKPRESSURE_HIGH_WATERMARK,
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    HEARTBEAT_INTERVAL_SECONDS,
    LANE,
    LANE_NAME,
    PACKAGE,
    POLL_INTERVAL_SECONDS,
    PROOF_FEATURES,
    SCHEMA_VERSION,
    SEQUENCE_BUFFER_CAPACITY,
    SLOW_CLIENT_ISOLATE_AFTER_TICKS,
)
from backend.nexus_public_realtime_transport.event_model import (
    PublicStreamEvent,
    build_event,
    encode_sse,
    encode_ws_frame,
    mint_resume_token,
    parse_resume_token,
)
from backend.nexus_public_realtime_transport.hard_bans import refuse_private_topic
from backend.nexus_public_realtime_transport.public_filter import filter_public_event
from backend.nexus_public_realtime_transport.sanitize import assert_no_forbidden_keys
from backend.nexus_public_realtime_transport.staleness import classify_staleness

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "public_feed.json"


class PublicStreamHub:
    """LOCAL/STAGING public-safe event hub.

    Publishes only allow-listed kinds/topics. Private Founder streams are refused.
    Fan-out uses per-client backpressure windows so slow clients are isolated.
    """

    def __init__(
        self,
        *,
        stream_id: str = "public.decision.feed",
        capacity: int = SEQUENCE_BUFFER_CAPACITY,
        backpressure_depth: int = BACKPRESSURE_HIGH_WATERMARK,
        isolate_after_ticks: int = SLOW_CLIENT_ISOLATE_AFTER_TICKS,
    ) -> None:
        refuse_private_topic(stream_id)
        self.stream_id = stream_id
        self.capacity = int(capacity)
        self._lock = threading.RLock()
        self._seq = 0
        self._events: list[PublicStreamEvent] = []
        self._last_event_ts_ms: int | None = None
        self.fanout = BackpressureFanout(
            max_depth=backpressure_depth,
            isolate_after_ticks=isolate_after_ticks,
        )

    def meta(self) -> dict[str, Any]:
        return {
            "ok": True,
            "schema": SCHEMA_VERSION,
            "lane": LANE,
            "lane_name": LANE_NAME,
            "branch": BRANCH,
            "package": PACKAGE,
            "base_commit": BASE_COMMIT,
            "stream_id": self.stream_id,
            "read_only": True,
            "customer_trading": False,
            "exchange_api_used": False,
            "private_event_stream": False,
            "transports": ["sse", "websocket", "polling"],
            "allowed_event_kinds": sorted(ALLOWED_EVENT_KINDS),
            "hard_bans": list(HARD_BANS),
            "features": list(PROOF_FEATURES),
            "backpressure": True,
            "slow_client_isolation": True,
            "environment": "local_staging",
        }

    def register_client(self, client_id: str) -> dict[str, Any]:
        window = self.fanout.register(client_id)
        return window.snapshot()

    def unregister_client(self, client_id: str) -> None:
        self.fanout.unregister(client_id)

    def publish(self, *, kind: str, topic: str | None = None, payload: dict[str, Any] | None = None) -> PublicStreamEvent:
        topic_n = topic or self.stream_id
        filter_public_event(kind=kind, topic=topic_n, payload=payload)
        with self._lock:
            self._seq += 1
            evt = build_event(seq=self._seq, kind=kind, topic=topic_n, payload=payload)
            self._events.append(evt)
            if len(self._events) > self.capacity:
                self._events = self._events[-self.capacity :]
            self._last_event_ts_ms = evt.ts_ms
            self.fanout.publish(evt)
            return evt

    def load_fixture_feed(self, path: Path | None = None) -> int:
        data = json.loads((path or _FIXTURE).read_text(encoding="utf-8"))
        rows = data.get("events") or []
        count = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            self.publish(
                kind=str(row.get("kind") or "decision_update"),
                topic=str(row.get("topic") or self.stream_id),
                payload=dict(row.get("payload") or {}),
            )
            count += 1
        return count

    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def resume_token(self, last_seq: int | None = None) -> str:
        with self._lock:
            seq = self._seq if last_seq is None else int(last_seq)
            return mint_resume_token(stream_id=self.stream_id, last_seq=seq)

    def events_after(self, last_seq: int) -> list[PublicStreamEvent]:
        with self._lock:
            return [e for e in self._events if e.seq > int(last_seq)]

    def resolve_resume(self, resume_token: str | None, last_event_id: str | None = None) -> int:
        if resume_token:
            parsed = parse_resume_token(resume_token)
            if parsed["stream_id"] != self.stream_id:
                raise ValueError("resume_token_stream_mismatch")
            return int(parsed["last_seq"])
        if last_event_id is not None and str(last_event_id).strip().isdigit():
            return int(last_event_id)
        return 0

    def staleness(self) -> dict[str, Any]:
        with self._lock:
            return classify_staleness(last_event_ts_ms=self._last_event_ts_ms)

    def heartbeat_event(self) -> PublicStreamEvent:
        return self.publish(
            kind="heartbeat",
            payload={"alive": True, "last_seq": self.last_seq()},
        )

    def poll(
        self,
        *,
        resume_token: str | None = None,
        last_event_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Polling fallback — same public events, no private streams."""
        last_seq = self.resolve_resume(resume_token, last_event_id)
        rows = self.events_after(last_seq)[: max(1, min(200, int(limit)))]
        new_last = rows[-1].seq if rows else last_seq
        token = self.resume_token(new_last)
        body = {
            **self.meta(),
            "transport": "polling",
            "poll_interval_seconds": POLL_INTERVAL_SECONDS,
            "events": [e.to_dict() for e in rows],
            "count": len(rows),
            "resume_token": token,
            "last_seq": new_last,
            "staleness": self.staleness(),
        }
        assert_no_forbidden_keys(body)
        return body

    def iter_sse(
        self,
        *,
        resume_token: str | None = None,
        last_event_id: str | None = None,
        max_events: int = 50,
        include_heartbeats: bool = True,
        heartbeat_every: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> Generator[str, None, None]:
        last_seq = self.resolve_resume(resume_token, last_event_id)
        ack = build_event(
            seq=0,
            kind="resume_ack",
            topic=self.stream_id,
            payload={"resumed_from": last_seq, "stream_id": self.stream_id},
            event_id=f"resume_ack:{last_seq}",
        )
        # resume_ack uses seq 0 marker for control; do not advance hub seq
        yield encode_sse(ack, resume_token=self.resume_token(last_seq))

        sent = 0
        cursor = last_seq
        last_hb = time.monotonic()
        idle_heartbeats = 0
        max_idle_heartbeats = 3
        while sent < max_events:
            batch = self.events_after(cursor)
            if batch:
                idle_heartbeats = 0
                for evt in batch:
                    cursor = evt.seq
                    token = self.resume_token(cursor)
                    yield encode_sse(evt, resume_token=token)
                    sent += 1
                    if sent >= max_events:
                        break
                last_hb = time.monotonic()
                continue
            if include_heartbeats and (time.monotonic() - last_hb) >= min(heartbeat_every, 0.01):
                hb = build_event(
                    seq=cursor,
                    kind="heartbeat",
                    topic=self.stream_id,
                    payload={"alive": True, "cursor": cursor},
                    event_id=f"hb:{cursor}:{int(time.time()*1000)}",
                )
                yield encode_sse(hb, resume_token=self.resume_token(cursor))
                last_hb = time.monotonic()
                idle_heartbeats += 1
                if idle_heartbeats >= max_idle_heartbeats and sent == 0:
                    break
            else:
                time.sleep(0.01)
        end = build_event(
            seq=cursor,
            kind="stream_end",
            topic=self.stream_id,
            payload={"reason": "max_events", "last_seq": cursor},
            event_id=f"end:{cursor}",
        )
        yield encode_sse(end, resume_token=self.resume_token(cursor))

    def iter_ws_frames(
        self,
        *,
        resume_token: str | None = None,
        last_event_id: str | None = None,
        max_events: int = 50,
        include_heartbeats: bool = True,
        heartbeat_every: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> Iterator[str]:
        last_seq = self.resolve_resume(resume_token, last_event_id)
        ack = build_event(
            seq=0,
            kind="resume_ack",
            topic=self.stream_id,
            payload={"resumed_from": last_seq, "stream_id": self.stream_id},
            event_id=f"resume_ack:{last_seq}",
        )
        yield encode_ws_frame(ack, resume_token=self.resume_token(last_seq))

        sent = 0
        cursor = last_seq
        last_hb = time.monotonic()
        idle_heartbeats = 0
        max_idle_heartbeats = 3
        while sent < max_events:
            batch = self.events_after(cursor)
            if batch:
                idle_heartbeats = 0
                for evt in batch:
                    cursor = evt.seq
                    yield encode_ws_frame(evt, resume_token=self.resume_token(cursor))
                    sent += 1
                    if sent >= max_events:
                        break
                last_hb = time.monotonic()
                continue
            if include_heartbeats and (time.monotonic() - last_hb) >= min(heartbeat_every, 0.01):
                hb = build_event(
                    seq=cursor,
                    kind="heartbeat",
                    topic=self.stream_id,
                    payload={"alive": True, "cursor": cursor},
                    event_id=f"hb:{cursor}:{int(time.time()*1000)}",
                )
                yield encode_ws_frame(hb, resume_token=self.resume_token(cursor))
                last_hb = time.monotonic()
                idle_heartbeats += 1
                if idle_heartbeats >= max_idle_heartbeats and sent == 0:
                    break
            else:
                time.sleep(0.01)
        end = build_event(
            seq=cursor,
            kind="stream_end",
            topic=self.stream_id,
            payload={"reason": "max_events", "last_seq": cursor},
            event_id=f"end:{cursor}",
        )
        yield encode_ws_frame(end, resume_token=self.resume_token(cursor))

    def drain_client(self, client_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.fanout.drain(client_id, limit=limit)
        return [e.to_dict() for e in rows]

    def prove_slow_client_isolation(
        self,
        *,
        burst: int = 80,
        slow_drain_every: int = 0,
        fast_drain_every: int = 1,
    ) -> dict[str, Any]:
        """Publish a burst while draining a fast client and starving a slow one.

        Slow client must isolate under backpressure; fast client keeps sequence continuity.
        """
        self.register_client("fast")
        self.register_client("slow")
        fast_seqs: list[int] = []
        for i in range(int(burst)):
            self.publish(
                kind="decision_update",
                payload={"i": i, "proof": "slow_client_isolation"},
            )
            if fast_drain_every and (i + 1) % fast_drain_every == 0:
                for evt in self.fanout.drain("fast", limit=BACKPRESSURE_HIGH_WATERMARK):
                    fast_seqs.append(evt.seq)
            if slow_drain_every and (i + 1) % slow_drain_every == 0:
                self.fanout.drain("slow", limit=1)

        # Final drain of whatever remains for fast client
        for evt in self.fanout.drain("fast", limit=BACKPRESSURE_HIGH_WATERMARK * 4):
            fast_seqs.append(evt.seq)

        snap = self.fanout.snapshot()
        slow = snap["clients"]["slow"]
        fast = snap["clients"]["fast"]
        continuous = all(fast_seqs[i] + 1 == fast_seqs[i + 1] for i in range(len(fast_seqs) - 1)) if len(fast_seqs) > 1 else True
        return {
            "ok": bool(slow["isolated"] and fast["isolated"] is False and continuous and len(fast_seqs) > 0),
            "slow_isolated": slow["isolated"],
            "slow_isolation_reason": slow["isolation_reason"],
            "slow_forced_polling": slow["forced_polling"],
            "fast_isolated": fast["isolated"],
            "fast_delivered": fast["delivered"],
            "fast_seq_count": len(fast_seqs),
            "fast_sequence_continuous": continuous,
            "fanout": snap["stats"],
            "backpressure_drops": snap["stats"]["offers_dropped"],
        }
