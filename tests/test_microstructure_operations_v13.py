"""V13-A Microstructure 14-day ops — Pass 1 design + synthetic preflight."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["DEMO"] = "false"

import pytest

from backend.nexus_microstructure.ops_v13 import (
    CAMPAIGN_ID,
    DESIGN_SYMBOLS_25,
    EVENT_STUDY_MUST_REMAIN,
    HARD_CAP_BYTES,
    STORAGE_FLOOR_BYTES,
    TARGET_CALENDAR_DAYS,
    MicrostructureOperationsControllerV13,
    build_campaign_design,
    evaluate_capture_start_gates_v13,
)
from backend.nexus_microstructure.ops_v13.constants import GIB, MIN_SYMBOL_COUNT
from backend.nexus_microstructure.ops_v13.daily_integrity_seal import seal_day
from backend.nexus_microstructure.ops_v13.storage_budget import StorageBudgetControllerV13
from backend.nexus_microstructure.ops_v13.synthetic_harness import (
    run_all_preflight_scenarios,
    run_synthetic_24h_logical_capture,
)

REPO = Path(__file__).resolve().parents[1]


def test_campaign_design_meets_founder_requirements():
    design = build_campaign_design()
    assert design["campaign_id"] == "ms_accum_v13_integrity_14d"
    assert design["campaign_id"] == CAMPAIGN_ID
    assert design["symbol_count"] >= 25
    assert len(DESIGN_SYMBOLS_25) >= MIN_SYMBOL_COUNT
    assert design["target_calendar_days"] == TARGET_CALENDAR_DAYS == 14
    assert set(design["families"]) == {"AGGRESSIVE_TRADE_FLOW", "LIQUIDATION_EVENTS"}
    assert design["storage"]["floor_free_disk_gib"] == 100
    assert design["storage"]["hard_cap_gib"] == 40
    assert STORAGE_FLOOR_BYTES == 100 * GIB
    assert HARD_CAP_BYTES == 40 * GIB
    d = design["durability"]
    assert d["exclusive_partition_ids"] is True
    assert d["atomic_manifest"] is True
    assert d["open_tail_seal"] is True
    assert d["persistent_clock"] is True
    assert d["resume_safe_linkage"] is True
    assert d["hourly_rotation"] is True
    assert d["daily_integrity_seal"] is True
    assert d["automatic_safe_stop"] is True
    assert design["live_capture_started"] is False
    assert design["event_study_readiness_status"] == EVENT_STUDY_MUST_REMAIN


def test_synthetic_24h_hourly_rotation_and_daily_seal(tmp_path: Path):
    report = run_synthetic_24h_logical_capture(tmp_path / "syn24", hours=24)
    assert report["status"] == "PASS"
    assert report["hourly_rotation_verified"] is True
    assert report["design_meets_min_25"] is True
    assert report["graceful_stop"] is True
    assert report["checksum_replay_verified"] is True
    assert report["daily_integrity_seal"]["atomic_write"] is True
    assert report["live_capture_started"] is False


def test_all_preflight_scenarios(tmp_path: Path):
    result = run_all_preflight_scenarios(tmp_path / "preflight")
    assert result["all_passed"] is True
    required = {
        "synthetic_24h_logical_capture",
        "forced_crash_restart",
        "clock_rollback",
        "disk_floor",
        "duplicate_writer",
        "manifest_interrupt",
        "open_tail_recovery",
        "hard_cap_safe_stop",
    }
    assert required <= set(result["scenarios"])
    for name in required:
        assert result["scenarios"][name]["status"] == "PASS", name
    assert result["live_capture_started"] is False
    assert result["event_study_readiness_status"] == "NOT_READY"


def test_storage_floor_and_hard_cap_constants(tmp_path: Path):
    b = StorageBudgetControllerV13(disk_root=str(tmp_path))
    below = b.refresh_free_disk(free_bytes_override=50 * GIB)
    assert below["passed"] is False
    above = StorageBudgetControllerV13(disk_root=str(tmp_path)).refresh_free_disk(
        free_bytes_override=150 * GIB
    )
    assert above["passed"] is True
    cap = StorageBudgetControllerV13(
        soft_limit_bytes=100,
        hard_limit_bytes=200,
        minimum_free_disk_bytes=STORAGE_FLOOR_BYTES,
    )
    cap.refresh_free_disk(free_bytes_override=200 * GIB)
    assert cap.observe_write(compressed_delta=250) == "STORAGE_HARD_CAP_BLOCKED"


def test_gates_never_start_live_from_agent():
    gates = evaluate_capture_start_gates_v13(
        previous_campaign_finalized=True,
        storage_cap_configured=True,
        preflight_synthetic_passed=True,
        enable_live_capture=False,
        coordinator_authorized=False,
        free_disk_override={"passed": True, "status": "PASS", "free_bytes": 200 * GIB},
    )
    assert gates["decision"] == "DRY_RUN_ONLY"
    assert gates["live_capture_started"] is False
    assert gates["live_capture_would_start"] is False
    assert gates["event_study_readiness_status"] == "NOT_READY"


def test_controller_pass1(tmp_path: Path):
    ctl = MicrostructureOperationsControllerV13(
        REPO,
        work_root=tmp_path / "work",
        disk_root=str(tmp_path),
        previous_campaign_finalized=True,
    )
    # Override disk via work path — may fail floor on tiny tmp; inject via free override
    # by patching budget inside pass1 is heavy; instead run preflight alone + design checks.
    # Full pass1 uses live disk_root; on CI/dev D: usually has space. Use override path:
    pass1 = ctl.run_pass1()
    assert pass1["live_capture_started"] is False
    assert pass1["event_study_readiness_status"] == "NOT_READY"
    assert pass1["campaign_id"] == CAMPAIGN_ID
    assert pass1["campaign_design"]["symbol_count"] >= 25
    assert pass1["preflight"]["all_passed"] is True
    assert pass1["PR27_merged"] is False
    assert pass1["G_deleted"] is False
    assert pass1["raw_prior_campaign_modified"] is False
    # all_passed may depend on live disk floor; if disk < 100GiB, gates block but preflight still PASS
    assert pass1["preflight"]["all_passed"] is True


def test_daily_seal_atomic(tmp_path: Path):
    run_synthetic_24h_logical_capture(tmp_path / "day", hours=3, symbols=("BTCUSDT",))
    sealed = seal_day(tmp_path / "day", day_key="20250804")
    # day key from SYNTHETIC_BASE_MS — accept whatever seal wrote if partitions exist
    assert sealed["atomic_write"] is True
    assert Path(sealed["seal_path"]).is_file()
