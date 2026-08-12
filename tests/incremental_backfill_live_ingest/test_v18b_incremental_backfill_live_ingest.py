"""V18-B Incremental Backfill + Live Ingest — focused tests."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_incremental_backfill_live_ingest.campaign import run_campaign  # noqa: E402
from backend.nexus_incremental_backfill_live_ingest.constants import (  # noqa: E402
    ACCEPTANCE_ZERO_COUNTERS,
    ARTIFACT_REL,
    CAPABILITIES,
    DATA_CLASS_FIXTURE,
    DATA_CLASS_LIVE_READ_ONLY,
    DATA_CLASS_OFFICIAL_HISTORICAL_SAMPLE,
    DATA_CLASS_STALE,
    HARD_BANS,
    OWNED_PATHS,
    PRIORITY_SYMBOLS,
    SCHEMA,
)
from backend.nexus_incremental_backfill_live_ingest.disk_quota import DiskQuotaExceeded  # noqa: E402
from backend.nexus_incremental_backfill_live_ingest.hard_bans import (  # noqa: E402
    HardBanViolation,
    refuse_banned_claim,
    refuse_exchange_write,
)
from backend.nexus_incremental_backfill_live_ingest.pipeline import IngestPipeline  # noqa: E402
from backend.nexus_incremental_backfill_live_ingest.samples import (  # noqa: E402
    official_historical_sample_batches,
    sample_inventory,
)

ROOT = Path(__file__).resolve().parents[2]


def test_constants_and_owned_paths():
    assert SCHEMA.startswith("v18_b_")
    assert len(PRIORITY_SYMBOLS) == 4
    assert "BTCUSDT" in PRIORITY_SYMBOLS
    assert "incremental_backfill" in CAPABILITIES
    assert "license_binding" in CAPABILITIES
    assert any("nexus_incremental_backfill_live_ingest" in p for p in OWNED_PATHS)
    assert "no_silent_gap_fill" in HARD_BANS
    assert "no_claim_15y_complete" in HARD_BANS
    assert len(ACCEPTANCE_ZERO_COUNTERS) == 5


def test_inventory_non_claims():
    inv = sample_inventory()
    assert inv["claims_15y_complete"] is False
    assert inv["claims_all_exchange_history"] is False
    assert inv["claims_full_training_set"] is False
    assert inv["claims_strategy_validation_pass"] is False
    assert inv["hard_max_symbols"] is False
    assert inv["dynamic_universe_later"] is True
    assert inv["allowed_backfill_windows_days"] == [7, 30, 90]


def test_backfill_windows():
    for w in (7, 30, 90):
        batches = official_historical_sample_batches(window_days=w)
        assert len(batches) == 4
        assert all(b["data_class"] == DATA_CLASS_OFFICIAL_HISTORICAL_SAMPLE for b in batches)
    with pytest.raises(ValueError):
        official_historical_sample_batches(window_days=15)


def test_incremental_backfill_and_live_append(tmp_path: Path):
    pipe = IngestPipeline(tmp_path / "lake")
    bf = pipe.incremental_backfill(window_days=7, resume=False)
    assert bf["processed"] >= 8  # 4 fixture + 4 official
    assert pipe.counters.ingested_count >= 8
    # Resume should be no-op for same backfill sequence
    bf2 = pipe.incremental_backfill(window_days=7, resume=True)
    assert bf2["processed"] == 0
    live = pipe.live_append(resume=True)
    assert live["processed"] == 4
    assert pipe.counters.live_append_count == 4
    assert pipe.counters.acceptance_zeros_ok()
    snap = pipe.snapshot()
    assert snap["acceptance_zeros"] == {k: 0 for k in ACCEPTANCE_ZERO_COUNTERS}
    assert DATA_CLASS_FIXTURE in pipe.counters.classification_counts
    assert DATA_CLASS_OFFICIAL_HISTORICAL_SAMPLE in pipe.counters.classification_counts
    assert DATA_CLASS_LIVE_READ_ONLY in pipe.counters.classification_counts


def test_dedupe_resolved(tmp_path: Path):
    pipe = IngestPipeline(tmp_path / "lake")
    batch = {
        "exchange_timestamp": "2024-02-01T00:00:00Z",
        "received_timestamp": "2024-02-01T00:00:01Z",
        "source_id": "binance_spot_klines_1m",
        "symbol_original": "BTCUSDT",
        "data_class": DATA_CLASS_FIXTURE,
        "license_reference": "v18b_licensed_official_or_fixture_sample_not_redistributed_bulk",
        "payload": {"open": "1", "note": "dedupe"},
    }
    r1 = pipe.ingest_one(batch, source_offset=0, mode="backfill")
    r2 = pipe.ingest_one(batch, source_offset=1, mode="backfill")
    assert r1["status"] == "INGESTED"
    assert r2["status"] == "DUPLICATE"
    assert r2["duplicate_resolved"] is True
    assert pipe.counters.duplicate_unresolved_count == 0


def test_future_timestamp_refused(tmp_path: Path):
    pipe = IngestPipeline(tmp_path / "lake")
    now_ms = int(datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp() * 1000)
    with pytest.raises(HardBanViolation):
        pipe.ingest_one(
            {
                "exchange_timestamp": "2099-06-01T00:00:00Z",
                "received_timestamp": "2099-06-01T00:00:01Z",
                "source_id": "binance_spot_klines_1m",
                "symbol_original": "BTCUSDT",
                "data_class": DATA_CLASS_FIXTURE,
                "license_reference": "v18b_licensed_official_or_fixture_sample_not_redistributed_bulk",
                "payload": {"open": "9"},
            },
            source_offset=0,
            mode="backfill",
            now_ms=now_ms,
        )
    # Counter increments before raise
    assert pipe.counters.future_timestamp_accept_count == 1


def test_unlicensed_ingest_refused(tmp_path: Path):
    pipe = IngestPipeline(tmp_path / "lake")
    with pytest.raises(HardBanViolation):
        pipe.ingest_one(
            {
                "exchange_timestamp": "2024-02-01T00:00:00Z",
                "received_timestamp": "2024-02-01T00:00:01Z",
                "source_id": "no_such_licensed_source",
                "symbol_original": "BTCUSDT",
                "data_class": DATA_CLASS_FIXTURE,
                "license_reference": "x",
                "payload": {"open": "9"},
            },
            source_offset=0,
            mode="backfill",
        )
    assert pipe.counters.unlicensed_ingest_count == 1


def test_raw_rewrite_and_silent_gap_fill_banned(tmp_path: Path):
    pipe = IngestPipeline(tmp_path / "lake")
    with pytest.raises(HardBanViolation):
        pipe.attempt_raw_rewrite("abc", {"x": 1})
    assert pipe.counters.raw_rewrite_count == 1
    with pytest.raises(HardBanViolation):
        pipe.attempt_silent_gap_fill(gap_start="a", gap_end="b")
    assert pipe.counters.silent_gap_fill_count == 1


def test_quarantine_rate_limit_retention_disk(tmp_path: Path):
    pipe = IngestPipeline(tmp_path / "lake")
    q = pipe.quarantine_corrupt(content_hash="b" * 64, reason="test", blob=b"corrupt")
    assert q["status"] == "QUARANTINED"
    assert pipe.counters.quarantined_count == 1

    rl = pipe.pause_on_rate_limit(http_status=429)
    assert rl["paused"] is True
    assert pipe.counters.rate_limit_pause_count == 1
    pipe.rate_limit.resume()

    pipe.incremental_backfill(window_days=7, resume=False)
    pruned = pipe.apply_retention()
    assert pruned["raw_rewritten"] is False

    tiny = IngestPipeline(tmp_path / "tiny", max_disk_bytes=250)
    with pytest.raises((DiskQuotaExceeded, Exception)):
        tiny.ingest_one(
            {
                "exchange_timestamp": "2024-02-01T00:00:00Z",
                "received_timestamp": "2024-02-01T00:00:01Z",
                "source_id": "binance_spot_klines_1m",
                "symbol_original": "BTCUSDT",
                "data_class": DATA_CLASS_FIXTURE,
                "license_reference": "v18b_licensed_official_or_fixture_sample_not_redistributed_bulk",
                "payload": {"pad": "z" * 4000},
            },
            source_offset=0,
            mode="backfill",
        )


def test_non_ingest_classes_and_silver_pit(tmp_path: Path):
    pipe = IngestPipeline(tmp_path / "lake")
    r = pipe.classify_non_ingest(DATA_CLASS_STALE)
    assert r["ingested"] is False
    pipe.incremental_backfill(window_days=7, resume=False)
    for sym in PRIORITY_SYMBOLS:
        silver = pipe.bridge.to_silver(sym)
        assert silver["exchange_symbol"] == sym
        assert silver["canonical_instrument_id"]
    assert len(pipe.pit._by_id) > 0  # noqa: SLF001


def test_banned_claims_and_exchange_write():
    with pytest.raises(HardBanViolation):
        refuse_banned_claim("15y_complete")
    with pytest.raises(HardBanViolation):
        refuse_banned_claim("strategy_validation_PASS")
    with pytest.raises(HardBanViolation):
        refuse_exchange_write()


def test_campaign_pass(tmp_path: Path):
    # Run campaign under repo root so artifacts land in owned path; also allow tmp by copying structure
    report = run_campaign(ROOT, head="TEST")
    assert report["status"] == "PASS"
    assert report["acceptance_zeros"] == {k: 0 for k in ACCEPTANCE_ZERO_COUNTERS}
    assert report["exchange_write"] is False
    assert report["demo"] is False
    assert report["claims_15y_complete"] is False
    art = ROOT / ARTIFACT_REL / "campaign_report.json"
    assert art.exists()
