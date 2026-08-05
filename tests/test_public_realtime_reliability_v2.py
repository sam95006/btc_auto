"""PUB2-E realtime reliability + backpressure tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_realtime_transport.backpressure import BackpressureFanout
from backend.nexus_public_realtime_transport.constants import (
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    PROOF_FEATURES,
    SCHEMA_VERSION,
)
from backend.nexus_public_realtime_transport.event_model import build_event
from backend.nexus_public_realtime_transport.hard_bans import HardBanViolation, run_hard_ban_pass
from backend.nexus_public_realtime_transport.public_filter import (
    filter_public_event,
    public_only_batch_filter,
)
from backend.nexus_public_realtime_transport.stream_hub import PublicStreamHub

ROOT = Path(__file__).resolve().parents[1]


def test_lane_constants():
    assert LANE == "PUB2-E"
    assert BRANCH == "feature/public-v2-realtime-reliability"
    assert BASE_COMMIT.startswith("5e93f677")
    assert SCHEMA_VERSION == "public_realtime_reliability_v2"
    assert "backpressure" in PROOF_FEATURES
    assert "slow_client_isolation" in PROOF_FEATURES
    assert "no_PR26_merge" in HARD_BANS


def test_public_only_filter_refuses_private():
    ok = filter_public_event(
        kind="decision_update",
        topic="public.decision.feed",
        payload={"n": 1},
    )
    assert ok["admitted"] is True
    with pytest.raises(HardBanViolation):
        filter_public_event(kind="decision_update", topic="private.event_stream", payload={})
    batch = public_only_batch_filter(
        [
            {"kind": "decision_update", "topic": "public.decision.feed", "payload": {}},
            {"kind": "decision_update", "topic": "execution.fills", "payload": {}},
        ]
    )
    assert batch["admitted_count"] == 1
    assert batch["refused_count"] == 1
    assert batch["private_leaked"] is False


def test_backpressure_coalesce_and_drop():
    fan = BackpressureFanout(max_depth=3, isolate_after_ticks=2)
    fan.register("c1")
    for i in range(5):
        evt = build_event(
            seq=i + 1,
            kind="heartbeat",
            topic="public.decision.feed",
            payload={"i": i},
            event_id=f"hb:{i}",
        )
        fan.publish(evt)
    w = fan.get("c1")
    assert w is not None
    assert w.depth <= 3
    assert w.coalesced >= 1


def test_slow_client_isolation_does_not_block_fast():
    hub = PublicStreamHub(backpressure_depth=4, isolate_after_ticks=2)
    proof = hub.prove_slow_client_isolation(burst=40, slow_drain_every=0, fast_drain_every=1)
    assert proof["slow_isolated"] is True
    assert proof["fast_isolated"] is False
    assert proof["fast_sequence_continuous"] is True
    assert proof["fast_delivered"] > 0
    assert proof["ok"] is True


def test_resume_sequence_continuity():
    hub = PublicStreamHub()
    for i in range(10):
        hub.publish(kind="decision_update", payload={"i": i})
    mid = hub.resume_token(4)
    resumed = hub.poll(resume_token=mid)
    seqs = [e["seq"] for e in resumed["events"]]
    assert seqs == list(range(5, 11))
    assert all(seqs[i] + 1 == seqs[i + 1] for i in range(len(seqs) - 1))


def test_hub_meta_features():
    hub = PublicStreamHub()
    meta = hub.meta()
    assert meta["lane"] == "PUB2-E"
    assert meta["backpressure"] is True
    assert meta["slow_client_isolation"] is True
    assert meta["private_event_stream"] is False
    for feat in PROOF_FEATURES:
        assert feat in meta["features"]


def test_hard_ban_pass_clean():
    report = run_hard_ban_pass(ROOT)
    assert report["ok"] is True
    assert report["critical_count"] == 0
