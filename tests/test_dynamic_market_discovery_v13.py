"""V13-D Dynamic Market Discovery tests — PIT integrity + eligibility."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.nexus_market_discovery import (
    DISCOVERY_SCHEMA,
    ERA_2024_06_01_MS,
    ERA_2024_12_01_MS,
    ERA_2025_03_01_MS,
    EVALUATION_DIMENSIONS,
    HARD_BANS,
    PitDiscoveryError,
    UNIVERSE_ID,
    assert_live_read_allowed,
    compare_eras,
    discover_universe,
    evaluate_instrument,
    materialize_fixtures,
    run_adversarial_suite,
    select_snapshot_for_as_of,
)


@pytest.fixture()
def fixtures_dir(tmp_path: Path) -> Path:
    root = tmp_path / "fixtures"
    materialize_fixtures(root)
    return root


def test_materialize_and_select_earlier_only(fixtures_dir: Path) -> None:
    snap = select_snapshot_for_as_of(ERA_2024_06_01_MS + 1000, fixtures_dir=fixtures_dir)
    assert snap["snapshot_id"] == "era_2024_06_01"
    assert snap["availability_ms"] <= ERA_2024_06_01_MS + 1000
    # Must not jump to a later era
    assert snap["availability_ms"] < ERA_2024_12_01_MS


def test_discover_eligible_rejected_structure(fixtures_dir: Path) -> None:
    result = discover_universe(
        ERA_2024_12_01_MS,
        fixtures_dir=fixtures_dir,
        retrieval_timestamp="2026-08-05T00:00:00Z",
    )
    assert result["schema"] == DISCOVERY_SCHEMA
    assert result["universe_id"] == UNIVERSE_ID
    assert result["point_in_time"] is True
    assert result["used_today_for_past"] is False
    assert result["exchange_write"] is False
    assert result["demo"] is False
    assert result["pr27_merged"] is False
    assert isinstance(result["eligible_universe"], list)
    assert isinstance(result["rejected_universe"], list)
    assert result["eligible_count"] == len(result["eligible_universe"])
    assert result["rejected_count"] == len(result["rejected_universe"])
    assert result["universe_checksum"]
    assert result["lineage"]["lineage_id"]
    assert result["lineage"]["availability_timestamp"]
    assert result["lineage"]["retrieval_timestamp"]
    assert set(EVALUATION_DIMENSIONS) <= set(result["evaluation_dimensions"])
    for ban in HARD_BANS:
        assert ban in result["hard_bans"]
    # Majors should pass
    assert "BTCUSDT" in result["eligible_universe"]
    assert "ETHUSDT" in result["eligible_universe"]
    # Thin / broken should reject
    assert "THINUSDT" in result["rejected_universe"]
    assert "BROKENUSDT" in result["rejected_universe"]


def test_never_use_today_for_past(fixtures_dir: Path) -> None:
    # Historical as_of with now_ms in a later era — discovery still uses earlier fixture
    result = discover_universe(
        ERA_2024_06_01_MS,
        fixtures_dir=fixtures_dir,
        now_ms=ERA_2025_03_01_MS,
        retrieval_timestamp="FIXED",
    )
    assert result["snapshot_id"] == "era_2024_06_01"
    assert result["availability_ms"] == ERA_2024_06_01_MS
    assert "LATEUSDT" not in result["eligible_universe"]
    assert "LATEUSDT" not in result["rejected_universe"]


def test_ghost_delisting_pit(fixtures_dir: Path) -> None:
    before = discover_universe(ERA_2024_06_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="T0")
    after = discover_universe(ERA_2024_12_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="T1")
    assert "GHOSTUSDT" in before["eligible_universe"]
    assert "GHOSTUSDT" not in after["eligible_universe"]
    ghost = next(r for r in after["rejected_details"] if r["symbol"] == "GHOSTUSDT")
    assert "DELISTED" in ghost["rejection_reasons"]


def test_future_observation_rejected() -> None:
    row = {
        "symbol": "X",
        "status": "Trading",
        "contract_type": "LinearPerpetual",
        "quote_coin": "USDT",
        "settle_coin": "USDT",
        "listing_ms": ERA_2024_06_01_MS,
        "observation_ms": ERA_2025_03_01_MS,
        "liquidity_score": 1.0,
        "turnover_usdt": 1e9,
        "volume_usdt": 1e9,
        "spread_bps": 1.0,
        "depth_usdt": 1e6,
        "open_interest_usdt": 1e6,
        "funding_available": True,
        "data_completeness": 1.0,
        "staleness_ms": 0,
        "symbol_mapping": "m",
        "tick_size": 0.1,
        "qty_step": 0.1,
        "minimum_notional": 5.0,
    }
    ev = evaluate_instrument(row, as_of_ms=ERA_2024_12_01_MS)
    assert ev.eligible is False
    assert "FUTURE_OBSERVATION_LEAK" in ev.rejection_reasons


def test_no_fixture_before_era_fails_closed(fixtures_dir: Path) -> None:
    with pytest.raises(PitDiscoveryError, match="no_historical_snapshot"):
        discover_universe(ERA_2024_06_01_MS - 10_000_000_000, fixtures_dir=fixtures_dir)


def test_era_comparison_checksums_differ(fixtures_dir: Path) -> None:
    cmp = compare_eras(
        ERA_2024_06_01_MS,
        ERA_2025_03_01_MS,
        fixtures_dir=fixtures_dir,
        retrieval_timestamp="FIXED",
    )
    assert cmp["checksums_differ"] is True
    assert "GHOSTUSDT" in cmp["disappeared"]


def test_deterministic_replay(fixtures_dir: Path) -> None:
    a = discover_universe(ERA_2024_12_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="FIXED")
    b = discover_universe(ERA_2024_12_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="FIXED")
    assert a["universe_checksum"] == b["universe_checksum"]
    assert a["result_checksum"] == b["result_checksum"]
    assert a["lineage"]["lineage_id"] == b["lineage"]["lineage_id"]


def test_all_dimensions_evaluated(fixtures_dir: Path) -> None:
    result = discover_universe(ERA_2024_12_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="T")
    sample = (result["eligible_details"] or result["rejected_details"])[0]
    for dim in EVALUATION_DIMENSIONS:
        assert dim in sample["dimension_results"]


def test_adversarial_suite_all_pass(fixtures_dir: Path) -> None:
    report = run_adversarial_suite(fixtures_dir)
    assert report["all_pass"] is True, json.dumps(report, indent=2)


def test_hard_ban_flags_in_lineage(fixtures_dir: Path) -> None:
    result = discover_universe(ERA_2024_12_01_MS, fixtures_dir=fixtures_dir, retrieval_timestamp="T")
    lin = result["lineage"]
    assert lin["exchange_write"] is False
    assert lin["demo"] is False
    assert lin["pr27_merged"] is False
    assert lin["pit_guarantees"]["never_uses_today_for_past"] is True


def test_live_public_metadata_forbidden_for_historical_as_of() -> None:
    with pytest.raises(PitDiscoveryError, match="live_public_metadata_forbidden"):
        assert_live_read_allowed(as_of_ms=ERA_2024_06_01_MS, now_ms=ERA_2025_03_01_MS)
