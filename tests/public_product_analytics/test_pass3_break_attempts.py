"""PUB2-I Pass 3: independent break attempts on honesty and catalog boundaries."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_product_analytics.hard_bans import HardBanViolation
from backend.nexus_public_product_analytics.metrics import (
    aggregate_metrics,
    assert_no_fabricated_snapshot,
)
from backend.nexus_public_product_analytics.store import LocalAnalyticsStore
from backend.nexus_public_product_analytics.three_pass import pass3_break_attempts, run_three_passes
from backend.nexus_public_product_analytics.tracker import ProductAnalyticsTracker

ROOT = Path(__file__).resolve().parents[2]


def test_forged_snapshot_caught():
    forged = {
        "north_star": {"status": "NO_OBSERVATIONS", "value": 0.91, "count": 0},
        "metrics": {
            "weekly_active_use": {
                "status": "NO_OBSERVATIONS",
                "value": 999,
                "count": 0,
            }
        },
    }
    with pytest.raises(HardBanViolation):
        assert_no_fabricated_snapshot(forged)


def test_unknown_event_refused():
    tracker = ProductAnalyticsTracker()
    tracker.grant_consent("member_z")
    with pytest.raises(HardBanViolation):
        tracker.track("private_execution_fill", raw_subject_id="member_z", props={})


def test_observed_after_real_consented_events():
    store = LocalAnalyticsStore()
    tracker = ProductAnalyticsTracker(store=store)
    tracker.grant_consent("member_real")
    tracker.track(
        "decision_first_opened",
        raw_subject_id="member_real",
        props={"decision_id_hash": "d1", "surface": "web"},
    )
    tracker.track(
        "counter_evidence_engagement",
        raw_subject_id="member_real",
        props={"decision_id_hash": "d1", "engagement_kind": "expand"},
    )
    snap = aggregate_metrics(store)
    assert_no_fabricated_snapshot(snap)
    assert snap["metrics"]["first_decision_opened"]["status"] == "OBSERVED"
    assert snap["metrics"]["first_decision_opened"]["count"] == 1
    assert snap["north_star"]["value"] is None  # still not fabricated


def test_pass3_and_full_three_passes():
    p3 = pass3_break_attempts(ROOT)
    assert p3["ok"] is True
    assert p3["survivor_count"] == 0
    full = run_three_passes(ROOT)
    assert full["ok"] is True
    assert full["status_json_emitted"] is False
    assert full["fabricated_metrics"] is False
