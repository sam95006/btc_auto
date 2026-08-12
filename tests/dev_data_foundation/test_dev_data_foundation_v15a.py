"""Tests for V15-A PIT development data foundation."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_dev_data_foundation.constants import (
    FORBIDDEN_STATUS_GLOB,
    HARD_BAN_FLAGS,
    PARTITION_CATEGORIES,
)
from backend.nexus_dev_data_foundation.hashing import sha_obj
from backend.nexus_dev_data_foundation.inventory import inventory_in_repo_sources
from backend.nexus_dev_data_foundation.partitions import (
    build_time_partitions,
    classify_timestamp,
    verify_no_dev_oos_overlap,
)
from backend.nexus_dev_data_foundation.pit import (
    filter_records_for_development,
    prove_oos_excluded,
    reject_invented_history,
    reject_oos_load,
    reject_today_for_past,
)
from backend.nexus_dev_data_foundation.records import DevDataRecordError, build_record, verify_record

REPO = Path(__file__).resolve().parents[2]


def test_partitions_cover_required_categories() -> None:
    parts = build_time_partitions()
    cats = {p["category"] for p in parts["partitions"]}
    assert cats == set(PARTITION_CATEGORIES)
    assert parts["oos_consumed"] is False
    assert verify_no_dev_oos_overlap(parts)["ok"] is True


def test_dev_does_not_overlap_oos() -> None:
    parts = build_time_partitions()
    by = {p["category"]: p for p in parts["partitions"]}
    assert by["DEVELOPMENT"]["end_ms"] < by["OOS_RESERVED"]["start_ms"]
    assert by["VALIDATION_PLANNING"]["end_ms"] < by["OOS_RESERVED"]["start_ms"]
    assert by["OOS_RESERVED"]["end_ms"] < by["OOS_UNTOUCHED"]["start_ms"]


def test_classify_oos_reserved() -> None:
    parts = build_time_partitions()
    oos = next(p for p in parts["partitions"] if p["category"] == "OOS_RESERVED")
    assert classify_timestamp(oos["start_ms"], parts) == "OOS_RESERVED"


def test_oos_load_blocked() -> None:
    assert reject_oos_load("OOS_RESERVED")["blocked"] is True
    assert reject_oos_load("OOS_UNTOUCHED")["blocked"] is True
    assert reject_oos_load("CONSUMED_FORBIDDEN")["blocked"] is True
    assert reject_oos_load("DEVELOPMENT")["blocked"] is False


def test_invented_history_blocked() -> None:
    r = reject_invented_history(claimed_available=True, source_present=False)
    assert r["ok"] is False
    assert r["status"] == "INVENTED_HISTORY_BLOCKED"


def test_today_for_past_blocked() -> None:
    r = reject_today_for_past(snapshot_availability_ms=1_740_787_200_000, as_of_ms=1_717_200_000_000)
    assert r["ok"] is False


def test_build_and_verify_record() -> None:
    rec = build_record(
        source_id="t1",
        source_kind="sanitized_pit_fixture",
        source_path="x.json",
        source_timestamp="2024-06-01T00:00:00Z",
        availability_ms=1_717_200_000_000,
        content_checksum=sha_obj({"a": 1}),
        availability_state="AVAILABLE",
        partition_id="DEV_EXPLORATION_PRIMARY",
        partition_category="DEVELOPMENT",
    )
    assert rec["oos_consumed"] is False
    assert rec["invented_history"] is False
    for k, v in HARD_BAN_FLAGS.items():
        assert rec[k] is v
    assert verify_record(rec)["ok"] is True


def test_oos_record_requires_catalog_flag() -> None:
    with pytest.raises(ValueError, match="oos_or_consumed_forbidden"):
        build_record(
            source_id="oos",
            source_kind="partition_seal",
            source_path=None,
            source_timestamp=None,
            availability_ms=1_785_663_000_100,
            content_checksum="x",
            availability_state="RESERVED_UNTOUCHED",
            partition_id="SEPTEMBER_H3_OOS_RESERVED",
            partition_category="OOS_RESERVED",
            allow_oos_catalog_only=False,
        )


def test_oos_catalog_record_not_dev_loadable() -> None:
    rec = build_record(
        source_id="oos_seal",
        source_kind="partition_seal",
        source_path=None,
        source_timestamp=None,
        availability_ms=1_785_663_000_100,
        content_checksum="x",
        availability_state="RESERVED_UNTOUCHED",
        partition_id="SEPTEMBER_H3_OOS_RESERVED",
        partition_category="OOS_RESERVED",
        allow_oos_catalog_only=True,
        payload_summary={"loaded_for_development": False},
    )
    assert verify_record(rec)["ok"] is True
    loaded = filter_records_for_development([rec])
    assert loaded == []


def test_inventory_no_invented_history() -> None:
    inv = inventory_in_repo_sources(REPO)
    assert inv["invented_history_count"] == 0
    assert inv["oos_consumed"] is False
    assert inv["record_count"] > 0
    for r in inv["records"]:
        assert r["invented_history"] is False
        assert r["oos_consumed"] is False
        assert verify_record(r)["ok"] is True


def test_oos_excluded_from_inventory_dev_load() -> None:
    inv = inventory_in_repo_sources(REPO)
    proof = prove_oos_excluded(inv["records"])
    assert proof["oos_excluded"] is True
    loaded = filter_records_for_development(inv["records"])
    for r in loaded:
        assert r["partition_category"] not in {"OOS_RESERVED", "OOS_UNTOUCHED", "CONSUMED_FORBIDDEN"}


def test_record_hash_tamper_detected() -> None:
    rec = build_record(
        source_id="t2",
        source_kind="test",
        source_path=None,
        source_timestamp=None,
        availability_ms=1_739_007_000_000,
        content_checksum="abc",
        availability_state="AVAILABLE",
        partition_id="DEV_EXPLORATION_PRIMARY",
        partition_category="DEVELOPMENT",
    )
    rec["content_checksum"] = "tampered"
    assert verify_record(rec)["ok"] is False


def test_invalid_availability_state() -> None:
    with pytest.raises(DevDataRecordError, match="invalid_availability_state"):
        build_record(
            source_id="bad",
            source_kind="test",
            source_path=None,
            source_timestamp=None,
            availability_ms=None,
            content_checksum="x",
            availability_state="FAKE",
            partition_id=None,
            partition_category="DEVELOPMENT",
        )


def test_no_forbidden_status_glob_in_owned_artifacts() -> None:
    art = REPO / "artifacts/readiness/immutable/v15_dev_data_foundation"
    if art.is_dir():
        banned = list(art.glob(FORBIDDEN_STATUS_GLOB))
        assert banned == []


def test_pit_universe_fixtures_present() -> None:
    for name in ("era_2024_06_01.json", "era_2024_12_01.json", "era_2025_03_01.json", "index.json"):
        assert (REPO / "backend/nexus_market_discovery/fixtures" / name).is_file()


def test_sanitized_fixture_not_banned_by_consumed_holdout_calendar() -> None:
    """era_2024_12_01 sits inside consumed-holdout calendar but is a PIT fixture."""
    inv = inventory_in_repo_sources(REPO)
    era = next(r for r in inv["records"] if r["source_id"] == "pit_universe_era_2024_12_01")
    assert era["partition_category"] == "DEVELOPMENT"
    assert era["availability_state"] == "AVAILABLE"
    loaded_ids = {r["source_id"] for r in filter_records_for_development(inv["records"])}
    assert "pit_universe_era_2024_12_01" in loaded_ids


def test_all_partition_categories_catalogued() -> None:
    inv = inventory_in_repo_sources(REPO)
    cats = {r["partition_category"] for r in inv["records"]}
    for required in PARTITION_CATEGORIES:
        assert required in cats
    # Consumed holdout marker remains forbidden and non-loadable
    consumed = [r for r in inv["records"] if r["source_id"] == "consumed_failed_oos_holdout"]
    assert consumed
    assert consumed[0]["partition_category"] == "CONSUMED_FORBIDDEN"
