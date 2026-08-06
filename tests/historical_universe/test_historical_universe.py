"""Fixture + unit tests for V17-E historical universe."""
from __future__ import annotations

from backend.nexus_historical_universe.constants import (
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
)
from backend.nexus_historical_universe.events import (
    build_contract_spec_timeline,
    build_listing_delisting_events,
)
from backend.nexus_historical_universe.fixture_proofs import run_all_fixtures
from backend.nexus_historical_universe.universe import reconstruct_universe


def test_reconstruct_mid_2024_includes_ghost_excludes_late():
    uni = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    assert "GHOSTUSDT" in uni["historical_eligible_universe"]
    assert "LATEUSDT" in uni["contracts_not_yet_listed"]
    assert "LATEUSDT" not in uni["historical_eligible_universe"]
    assert "BTCUSDT" in uni["coins_existing"]
    assert "BTCUSDT" in uni["contracts_listed"]


def test_reconstruct_post_delist_excludes_ghost():
    uni = reconstruct_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
    assert "GHOSTUSDT" in uni["contracts_delisted"]
    assert "GHOSTUSDT" not in uni["historical_eligible_universe"]
    assert "GHOSTUSDT" in uni["historical_excluded_universe"]


def test_late_listed_in_2025():
    uni = reconstruct_universe(ERA_2025_03_01_MS, retrieval_timestamp="FIXED")
    assert "LATEUSDT" in uni["contracts_listed"]
    assert "LATEUSDT" in uni["historical_eligible_universe"]


def test_listing_delisting_events_built():
    events = build_listing_delisting_events()
    assert events["event_count"] >= 2
    assert any(e["event_type"] == "DELISTING" and e["symbol"] == "GHOSTUSDT" for e in events["events"])
    assert any(e["event_type"] == "LISTING" and e["symbol"] == "LATEUSDT" for e in events["events"])


def test_contract_spec_timeline_btc_drift():
    timeline = build_contract_spec_timeline()
    btc = [e for e in timeline["timeline"] if e["symbol"] == "BTCUSDT"]
    assert len(btc) >= 2
    mid = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    post = reconstruct_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
    mid_btc = next(d for d in mid["instrument_details"] if d["symbol"] == "BTCUSDT")
    post_btc = next(d for d in post["instrument_details"] if d["symbol"] == "BTCUSDT")
    assert mid_btc["contract_spec"]["tick_size"] == 0.1
    assert post_btc["contract_spec"]["tick_size"] == 0.5


def test_pit_liquidity_not_today():
    uni = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    thin = next(d for d in uni["instrument_details"] if d["symbol"] == "THINUSDT")
    assert thin["liquidity_observation_ms"] <= ERA_2024_06_01_MS
    assert thin["liquidity"]["liquidity_score"] == 0.01
    assert not thin["eligible"]


def test_all_fixture_proofs_pass():
    results = run_all_fixtures()
    assert len(results) == 5
    assert all(r["passed"] for r in results)


def test_universe_checksum_stable():
    a = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    b = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    assert a["universe_checksum"] == b["universe_checksum"]
    c = reconstruct_universe(ERA_2024_12_01_MS, retrieval_timestamp="FIXED")
    assert a["universe_checksum"] != c["universe_checksum"]


def test_per_timestamp_fields_present():
    uni = reconstruct_universe(ERA_2024_06_01_MS, retrieval_timestamp="FIXED")
    for key in (
        "coins_existing",
        "contracts_listed",
        "contracts_not_yet_listed",
        "contracts_delisted",
        "historical_eligible_universe",
        "historical_excluded_universe",
        "listing_delisting_events_as_of",
        "contract_spec_timeline_as_of",
    ):
        assert key in uni
    detail = uni["instrument_details"][0]
    for key in (
        "coin_exists",
        "listing_state",
        "tradable_state",
        "contract_spec",
        "liquidity",
        "data_completeness",
    ):
        assert key in detail
