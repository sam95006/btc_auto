"""V17-B Bronze Immutable Raw Data Lake — unit and adversarial tests."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_bronze_immutable_raw_lake.campaign import run_campaign  # noqa: E402
from backend.nexus_bronze_immutable_raw_lake.constants import (  # noqa: E402
    ARTIFACT_REL,
    BRONZE_REQUIRED_FIELDS,
    HARD_BANS,
    OWNED_PATHS,
    SCHEMA,
)
from backend.nexus_bronze_immutable_raw_lake.fixtures import (  # noqa: E402
    all_bounded_ingest_batches,
    sample_inventory,
)
from backend.nexus_bronze_immutable_raw_lake.hard_bans import (  # noqa: E402
    HardBanViolation,
    assert_no_acceleration_report_edit,
    refuse_15y_history_claim,
    refuse_exchange_write,
)
from backend.nexus_bronze_immutable_raw_lake.lake import BronzeLake, DiskBudgetExceeded  # noqa: E402
from backend.nexus_bronze_immutable_raw_lake.records import (  # noqa: E402
    attempt_ai_mutate_payload,
    build_bronze_record,
    verify_bronze_record,
)

ROOT = Path(__file__).resolve().parents[2]


def test_required_fields_and_owned_paths():
    assert len(BRONZE_REQUIRED_FIELDS) == 11
    assert "content_hash" in BRONZE_REQUIRED_FIELDS
    assert "license_reference" in BRONZE_REQUIRED_FIELDS
    assert any("nexus_bronze_immutable_raw_lake" in p for p in OWNED_PATHS)
    assert "no_historical_rewrite" in HARD_BANS
    assert "no_ai_mutate_raw_payload" in HARD_BANS
    assert "no_claim_15y_history_downloaded" in HARD_BANS
    assert SCHEMA.startswith("v17_b_")


def test_build_and_verify_record():
    batch = all_bounded_ingest_batches()[0]
    rec = build_bronze_record(
        exchange_timestamp=batch["exchange_timestamp"],
        received_timestamp=batch["received_timestamp"],
        source_id=batch["source_id"],
        symbol_original=batch["symbol_original"],
        payload=batch["payload"],
        classification=batch["classification"],
        license_reference=batch["license_reference"],
    )
    for f in BRONZE_REQUIRED_FIELDS:
        assert f in rec
    verify_bronze_record(rec)
    assert rec["ai_mutable"] is False
    assert rec["lineage"]["guarantees"]["raw_payload_ai_immutable"] is True


def test_utc_only_rejects_offset():
    with pytest.raises(HardBanViolation):
        build_bronze_record(
            exchange_timestamp="2024-01-01T00:00:00+00:00",
            received_timestamp="2024-01-01T00:00:01Z",
            source_id="x",
            symbol_original="BTCUSDT",
            payload={"a": 1},
            classification="FIXTURE",
            license_reference="t",
        )


def test_duplicate_detection_and_resume(tmp_path: Path):
    lake = BronzeLake(tmp_path / "lake")
    batches = all_bounded_ingest_batches()
    r1 = lake.ingest(
        exchange_timestamp=batches[0]["exchange_timestamp"],
        received_timestamp=batches[0]["received_timestamp"],
        source_id=batches[0]["source_id"],
        symbol_original=batches[0]["symbol_original"],
        payload=batches[0]["payload"],
        classification=batches[0]["classification"],
        license_reference=batches[0]["license_reference"],
        source_offset=0,
    )
    assert r1["status"] == "INGESTED"
    r2 = lake.ingest(
        exchange_timestamp=batches[0]["exchange_timestamp"],
        received_timestamp=batches[0]["received_timestamp"],
        source_id=batches[0]["source_id"],
        symbol_original=batches[0]["symbol_original"],
        payload=batches[0]["payload"],
        classification=batches[0]["classification"],
        license_reference=batches[0]["license_reference"],
        source_offset=0,
    )
    assert r2["status"] == "DUPLICATE"
    assert lake.resume_offset() == 1
    # Partial resume: continue from offset 1
    start = lake.resume_offset()
    for i, batch in enumerate(batches[start:], start=start):
        lake.ingest(
            exchange_timestamp=batch["exchange_timestamp"],
            received_timestamp=batch["received_timestamp"],
            source_id=batch["source_id"],
            symbol_original=batch["symbol_original"],
            payload=batch["payload"],
            classification=batch["classification"],
            license_reference=batch["license_reference"],
            source_offset=i,
        )
    assert lake.resume_offset() == len(batches)


def test_no_historical_rewrite(tmp_path: Path):
    lake = BronzeLake(tmp_path / "lake")
    with pytest.raises(HardBanViolation, match="no_historical_rewrite"):
        lake.rewrite_record("abc", {"x": 1})


def test_ai_cannot_mutate_payload():
    batch = all_bounded_ingest_batches()[0]
    rec = build_bronze_record(
        exchange_timestamp=batch["exchange_timestamp"],
        received_timestamp=batch["received_timestamp"],
        source_id=batch["source_id"],
        symbol_original=batch["symbol_original"],
        payload=batch["payload"],
        classification=batch["classification"],
        license_reference=batch["license_reference"],
    )
    with pytest.raises(HardBanViolation, match="no_ai_mutate_raw_payload"):
        attempt_ai_mutate_payload(rec, {"open": "0"})


def test_corrupt_quarantine(tmp_path: Path):
    lake = BronzeLake(tmp_path / "lake")
    h = "d" * 64
    (lake.records_dir / f"{h}.json").write_text(
        json.dumps(
            {
                "schema": "v17_b_bronze_record_v1",
                "schema_version": "1.0.0",
                "exchange_timestamp": "2024-01-01T00:00:00Z",
                "received_timestamp": "2024-01-01T00:00:01Z",
                "ingested_timestamp": "2024-01-01T00:00:02Z",
                "source_id": "corrupt",
                "symbol_original": "BTCUSDT",
                "payload": {"open": "1"},
                "content_hash": "e" * 64,
                "partition_hash": "f" * 64,
                "compression": "none",
                "license_reference": "t",
                "ai_mutable": False,
            }
        ),
        encoding="utf-8",
    )
    result = lake.verify_stored(h)
    assert result["status"] == "QUARANTINED"
    assert (lake.quarantine_dir / f"{h}.json").exists()


def test_bounded_disk(tmp_path: Path):
    lake = BronzeLake(tmp_path / "lake", max_disk_bytes=180)
    with pytest.raises(DiskBudgetExceeded):
        lake.ingest(
            exchange_timestamp="2024-01-01T00:00:00Z",
            received_timestamp="2024-01-01T00:00:01Z",
            source_id="disk",
            symbol_original="BTCUSDT",
            payload={"pad": "y" * 400},
            classification="FIXTURE",
            license_reference="t",
        )


def test_fixture_inventory_not_15y():
    inv = sample_inventory()
    assert inv["claims_15y_history_downloaded"] is False
    assert inv["total_bounded_samples"] <= 10
    assert "FIXTURE" in inv["classification_set"]
    with pytest.raises(HardBanViolation):
        refuse_15y_history_claim()
    with pytest.raises(HardBanViolation):
        refuse_exchange_write()
    assert_no_acceleration_report_edit(list(OWNED_PATHS))


def test_campaign_pass(tmp_path: Path):
    # Isolate campaign writes to tmp so sealed repo artifacts stay immutable.
    report = run_campaign(tmp_path)
    assert report["status"] == "PASS"
    assert report["claims_15y_history_downloaded"] is False
    assert report["real_or_fixture"] == "FIXTURE"
    assert report["data_classification"] == "FIXTURE_AND_BOUNDED_OFFICIAL_SAMPLE_ONLY"
    art = tmp_path / ARTIFACT_REL
    assert (art / "campaign_report.json").exists()
    assert (art / "bronze_manifest.json").exists()
    assert not list(art.glob("*_status.json"))
    # Sealed in-repo campaign artifacts from the lane commit must remain present.
    sealed = ROOT / ARTIFACT_REL
    assert (sealed / "campaign_report.json").exists()
    assert (sealed / "bronze_manifest.json").exists()
