"""PUB2-I Pass 1: schema, consent gate, honest empty aggregations."""
from __future__ import annotations

from pathlib import Path

from backend.nexus_public_product_analytics.constants import METRIC_IDS, NORTH_STAR
from backend.nexus_public_product_analytics.metrics import aggregate_metrics, assert_no_fabricated_snapshot
from backend.nexus_public_product_analytics.schema import build_metric_schema, validate_schema_document
from backend.nexus_public_product_analytics.store import LocalAnalyticsStore
from backend.nexus_public_product_analytics.three_pass import pass1_implementation
from backend.nexus_public_product_analytics.tracker import ProductAnalyticsTracker

ROOT = Path(__file__).resolve().parents[2]


def test_metric_schema_lists_all_required_ids():
    schema = build_metric_schema()
    assert schema["north_star"]["name"] == NORTH_STAR
    assert schema["fabricated_results_forbidden"] is True
    assert schema["status_json_forbidden"] is True
    assert validate_schema_document(schema) == []
    ids = {m["metric_id"] for m in schema["metrics"]}
    assert set(METRIC_IDS) <= ids
    assert schema["north_star"]["current_observation"]["value"] is None
    assert schema["north_star"]["current_observation"]["count"] == 0


def test_consent_default_denies_tracking():
    tracker = ProductAnalyticsTracker()
    assert (
        tracker.track(
            "evidence_engagement",
            raw_subject_id="u1",
            props={"decision_id_hash": "abc", "engagement_kind": "open"},
        )
        is None
    )
    assert tracker.dropped_without_consent == 1
    assert tracker.recorded == 0


def test_empty_aggregation_is_honest():
    snap = aggregate_metrics(LocalAnalyticsStore())
    assert_no_fabricated_snapshot(snap)
    assert snap["north_star"]["status"] == "NO_OBSERVATIONS"
    assert snap["north_star"]["value"] is None
    for mid in METRIC_IDS:
        row = snap["metrics"][mid]
        assert row["status"] == "NO_OBSERVATIONS"
        assert row["count"] == 0
        assert row["value"] is None


def test_pass1_runner_ok():
    result = pass1_implementation(ROOT)
    assert result["ok"] is True
    assert result["north_star_status"] in {"NO_OBSERVATIONS", "OBSERVED", "UNAVAILABLE"}
