"""V17 deep PIT / survivorship / collision — property & mutation tests."""
from __future__ import annotations

import os

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_deep_pit_survivorship.property_attacks import (  # noqa: E402
    inject_mutated_revision_axes,
    run_mutation_as_known_at_campaign,
    run_property_as_known_at_campaign,
)
from backend.nexus_pit_revision_v17.fixtures import DAY, T0  # noqa: E402


def test_property_as_known_at_zero_survivors():
    report = run_property_as_known_at_campaign()
    assert report["pass"] is True
    assert report["survivor_count"] == 0
    assert report["case_count"] >= 64


def test_property_boundary_cases_included():
    report = run_property_as_known_at_campaign()
    # Boundary cases are prefixed; random cases also present.
    sample_ids = [c["case_id"] for c in report["cases_sample"]]
    assert any(cid.startswith("boundary:") or cid.startswith("rand:") for cid in sample_ids)


def test_mutation_as_known_at_zero_survivors():
    report = run_mutation_as_known_at_campaign()
    assert report["pass"] is True
    assert report["survivor_count"] == 0
    assert report["attack_count"] >= 48
    assert report["blocked_count"] == report["attack_count"]


def test_axis_mutation_past_aka_blocked():
    result = inject_mutated_revision_axes(as_known_at=T0 + 3 * DAY)
    assert result["blocked"] is True
    assert result["survivor"] is False
    assert result["survivors"] == []


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_property_at_r2_boundary_offsets(offset: int):
    from backend.nexus_pit_revision_v17.fixtures import build_revision_catalog
    from backend.nexus_pit_revision_v17.store import PitRevisionStore, research_query

    store = PitRevisionStore()
    store.ingest_many(build_revision_catalog())
    aka = T0 + 5 * DAY + offset
    result = research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=aka)
    if offset < 0:
        assert result.revision_id == "OBS_BTC_CLOSE_R1"
    else:
        assert result.revision_id == "OBS_BTC_CLOSE_R2"
    if result.selected_revision:
        times = result.selected_revision["times"]
        assert times["revision_time"] <= aka
        assert times["available_time"] <= aka
        assert times["ingest_time"] <= aka
