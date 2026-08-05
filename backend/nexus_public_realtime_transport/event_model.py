"""Public-safe realtime event model with sequence and resume tokens."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_public_realtime_transport.constants import (
    ALLOWED_EVENT_KINDS,
    RESUME_TOKEN_TTL_SECONDS,
    SCHEMA_VERSION,
)
from backend.nexus_public_realtime_transport.hard_bans import refuse_private_topic
from backend.nexus_public_realtime_transport.sanitize import assert_no_forbidden_keys

_RESUME_SECRET = b"nexus-pub-f-local-staging-resume-v1"


@dataclass(frozen=True)
class PublicStreamEvent:
    seq: int
    event_id: str
    kind: str
    topic: str
    ts_ms: int
    payload: dict[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA_VERSION
    public_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        body = asdict(self)
        assert_no_forbidden_keys(body)
        return body


def mint_resume_token(*, stream_id: str, last_seq: int, now: float | None = None) -> str:
    """Opaque resume token: stream_id|seq|exp|mac (LOCAL/STAGING only)."""
    now_f = time.time() if now is None else float(now)
    exp = int(now_f + RESUME_TOKEN_TTL_SECONDS)
    body = f"{stream_id}|{int(last_seq)}|{exp}"
    mac = hmac.new(_RESUME_SECRET, body.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"{body}|{mac}"


def parse_resume_token(token: str, *, now: float | None = None) -> dict[str, Any]:
    parts = str(token).split("|")
    if len(parts) != 4:
        raise ValueError("invalid_resume_token")
    stream_id, seq_s, exp_s, mac = parts
    body = f"{stream_id}|{seq_s}|{exp_s}"
    expect = hmac.new(_RESUME_SECRET, body.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(expect, mac):
        raise ValueError("resume_token_mac_mismatch")
    now_f = time.time() if now is None else float(now)
    if int(exp_s) < int(now_f):
        raise ValueError("resume_token_expired")
    return {"stream_id": stream_id, "last_seq": int(seq_s), "exp": int(exp_s)}


def build_event(
    *,
    seq: int,
    kind: str,
    topic: str,
    payload: dict[str, Any] | None = None,
    ts_ms: int | None = None,
    event_id: str | None = None,
) -> PublicStreamEvent:
    refuse_private_topic(topic)
    kind_n = str(kind).strip().lower()
    if kind_n not in ALLOWED_EVENT_KINDS:
        raise ValueError(f"disallowed_event_kind:{kind}")
    payload = dict(payload or {})
    assert_no_forbidden_keys(payload)
    ts = int(time.time() * 1000) if ts_ms is None else int(ts_ms)
    eid = event_id or f"{topic}:{seq}:{ts}"
    return PublicStreamEvent(
        seq=int(seq),
        event_id=eid,
        kind=kind_n,
        topic=str(topic),
        ts_ms=ts,
        payload=payload,
    )


def encode_sse(event: PublicStreamEvent, *, resume_token: str | None = None) -> str:
    data = event.to_dict()
    if resume_token is not None:
        data["resume_token"] = resume_token
    # id: enables EventSource Last-Event-ID style resume
    return f"id: {event.seq}\nevent: {event.kind}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def encode_ws_frame(event: PublicStreamEvent, *, resume_token: str | None = None) -> str:
    data = event.to_dict()
    if resume_token is not None:
        data["resume_token"] = resume_token
    return json.dumps({"type": "event", **data}, separators=(",", ":"))
