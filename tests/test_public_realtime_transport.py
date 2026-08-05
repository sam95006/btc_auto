"""Tests for PUB-F public realtime transport."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from backend.nexus_public_realtime_transport.backoff import BackoffState
from backend.nexus_public_realtime_transport.client_session import (
    PublicRealtimeClientSession,
    replay_into_session,
)
from backend.nexus_public_realtime_transport.constants import HARD_BANS, SCHEMA_VERSION
from backend.nexus_public_realtime_transport.event_model import (
    build_event,
    mint_resume_token,
    parse_resume_token,
)
from backend.nexus_public_realtime_transport.hard_bans import (
    HardBanViolation,
    refuse_private_topic,
    run_hard_ban_pass,
)
from backend.nexus_public_realtime_transport.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
)
from backend.nexus_public_realtime_transport.sequence_buffer import SequenceBuffer
from backend.nexus_public_realtime_transport.staleness import classify_staleness
from backend.nexus_public_realtime_transport.stream_hub import PublicStreamHub

ROOT = Path(__file__).resolve().parents[1]


def test_hard_bans_include_private_stream_ban():
    assert "no_private_event_stream_exposure" in HARD_BANS
    assert "no_live_public_deployment" in HARD_BANS


def test_refuse_private_topics():
    with pytest.raises(HardBanViolation):
        refuse_private_topic("private.event_stream")
    with pytest.raises(HardBanViolation):
        refuse_private_topic("founder.runtime")
    with pytest.raises(HardBanViolation):
        PublicStreamHub(stream_id="private.events")


def test_forbidden_payload_keys():
    with pytest.raises(ForbiddenPayloadKeyError):
        assert_no_forbidden_keys({"order_id": "x"})
    with pytest.raises(ForbiddenPayloadKeyError):
        build_event(seq=1, kind="decision_update", topic="public.decision.feed", payload={"api_key": "nope"})


def test_sequence_duplicate_and_ooo():
    buf = SequenceBuffer()
    e1 = build_event(seq=1, kind="decision_update", topic="public.decision.feed", payload={"n": 1})
    e3 = build_event(seq=3, kind="decision_update", topic="public.decision.feed", payload={"n": 3})
    e2 = build_event(seq=2, kind="decision_update", topic="public.decision.feed", payload={"n": 2})
    r1 = buf.apply(e1)
    assert r1.reason == "in_order"
    r3 = buf.apply(e3)
    assert r3.reason == "buffered_out_of_order"
    r2 = buf.apply(e2)
    assert [e.seq for e in r2.delivered] == [2, 3]
    dup = buf.apply(e1)
    assert dup.reason in {"duplicate_or_stale_seq", "duplicate_event_id"}
    assert buf.duplicates_suppressed >= 1


def test_duplicate_event_id_suppressed():
    buf = SequenceBuffer()
    a = build_event(
        seq=1,
        kind="decision_update",
        topic="public.decision.feed",
        payload={"n": 1},
        event_id="same-id",
    )
    b = build_event(
        seq=2,
        kind="decision_update",
        topic="public.decision.feed",
        payload={"n": 2},
        event_id="same-id",
    )
    assert buf.apply(a).accepted is True
    assert buf.apply(b).reason == "duplicate_event_id"


def test_resume_token_roundtrip():
    token = mint_resume_token(stream_id="public.decision.feed", last_seq=7, now=1_700_000_000.0)
    parsed = parse_resume_token(token, now=1_700_000_000.0)
    assert parsed["last_seq"] == 7
    assert parsed["stream_id"] == "public.decision.feed"
    with pytest.raises(ValueError):
        parse_resume_token(token, now=1_700_000_000.0 + 10_000)


def test_backoff_grows_then_caps():
    rng = random.Random(0)
    state = BackoffState()
    delays = [state.next_delay(rng=rng) for _ in range(8)]
    assert delays[0] < delays[2]
    assert max(delays) <= 30.0 + 1e-9
    state.reset()
    assert state.attempt == 0


def test_staleness_bands():
    fresh = classify_staleness(last_event_ts_ms=1_000_000, now_ms=1_000_000 + 5_000)
    assert fresh["band"] == "fresh"
    aging = classify_staleness(last_event_ts_ms=1_000_000, now_ms=1_000_000 + 30_000)
    assert aging["band"] == "aging"
    stale = classify_staleness(last_event_ts_ms=1_000_000, now_ms=1_000_000 + 60_000)
    assert stale["band"] == "stale" and stale["needs_reconnect"] is True


def test_hub_fixture_sse_ws_poll_resume():
    hub = PublicStreamHub()
    n = hub.load_fixture_feed()
    assert n >= 5
    assert hub.meta()["schema"] == SCHEMA_VERSION
    assert hub.meta()["private_event_stream"] is False

    polled = hub.poll(last_event_id="0", limit=10)
    assert polled["count"] == n
    assert polled["resume_token"]
    assert_no_forbidden_keys(polled)

    mid = hub.resume_token(2)
    resumed = hub.poll(resume_token=mid, limit=50)
    assert all(e["seq"] > 2 for e in resumed["events"])

    sse_chunks = list(hub.iter_sse(last_event_id="0", max_events=n, heartbeat_every=0.01))
    assert any("event: resume_ack" in c for c in sse_chunks)
    assert any("event: decision_update" in c for c in sse_chunks)
    assert any("event: stream_end" in c for c in sse_chunks)

    frames = list(hub.iter_ws_frames(last_event_id="0", max_events=n, heartbeat_every=0.01))
    parsed = [json.loads(f) for f in frames]
    assert parsed[0]["kind"] == "resume_ack"
    assert any(p.get("kind") == "decision_update" for p in parsed)


def test_client_session_reconnect_backoff_polling_ooo():
    session = PublicRealtimeClientSession(prefer_transport="websocket")
    assert session.choose_transport(sse_available=True, ws_available=False) == "sse"
    delay = session.note_disconnect()
    assert delay > 0
    assert session.stats.reconnects == 1
    assert session.fallback_to_polling() == "polling"

    e1 = build_event(seq=1, kind="decision_update", topic="public.decision.feed", payload={"i": 1})
    e3 = build_event(seq=3, kind="decision_update", topic="public.decision.feed", payload={"i": 3})
    e2 = build_event(seq=2, kind="decision_update", topic="public.decision.feed", payload={"i": 2})
    snap = replay_into_session(session, [e1, e3, e2, e1])
    assert snap["stats"]["delivered"] == 3
    assert snap["stats"]["duplicates_suppressed"] >= 1
    assert snap["stats"]["out_of_order_buffered"] >= 1
    assert snap["stats"]["polling_fallbacks"] == 1


def test_hard_ban_pass_clean():
    report = run_hard_ban_pass(ROOT)
    assert report["ok"] is True
    assert report["critical_count"] == 0
