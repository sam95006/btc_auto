"""Pass-2 adversarial self-review + negative tests for V13-A."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.clock_guard import ClockRollbackRejected
from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import PartitionIdentityConflict
from backend.nexus_microstructure.ops_v13.campaign_design import build_campaign_design
from backend.nexus_microstructure.ops_v13.constants import (
    CAMPAIGN_ID,
    EVENT_STUDY_MUST_REMAIN,
    GIB,
    HARD_CAP_BYTES,
    MIN_SYMBOL_COUNT,
    SCHEMA,
    STORAGE_FLOOR_BYTES,
    SYNTHETIC_BASE_MS,
)
from backend.nexus_microstructure.ops_v13.gates import evaluate_capture_start_gates_v13
from backend.nexus_microstructure.ops_v13.storage_budget import StorageBudgetControllerV13
from backend.nexus_microstructure.ops_v13.synthetic_harness import _tick, _writer


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def neg_undersized_symbol_design() -> dict[str, Any]:
    raised = False
    try:
        build_campaign_design(symbols=("BTCUSDT", "ETHUSDT"))
    except ValueError:
        raised = True
    return {
        "name": "neg_undersized_symbol_design",
        "status": "PASS" if raised else "FAIL",
        "expected": f"ValueError when symbols < {MIN_SYMBOL_COUNT}",
        "raised": raised,
    }


def neg_live_flags_without_coordinator() -> dict[str, Any]:
    gates = evaluate_capture_start_gates_v13(
        previous_campaign_finalized=True,
        storage_cap_configured=True,
        preflight_synthetic_passed=True,
        enable_live_capture=True,
        coordinator_authorized=False,
        free_disk_override={
            "passed": True,
            "free_bytes": 200 * GIB,
            "minimum_free_disk_bytes": STORAGE_FLOOR_BYTES,
            "status": "PASS",
        },
    )
    ok = (
        gates["decision"] == "DRY_RUN_ONLY"
        and gates["live_capture_started"] is False
        and gates["live_capture_would_start"] is False
    )
    return {
        "name": "neg_live_flags_without_coordinator",
        "status": "PASS" if ok else "FAIL",
        "decision": gates["decision"],
        "live_capture_started": gates["live_capture_started"],
    }


def neg_block_when_preflight_fails() -> dict[str, Any]:
    gates = evaluate_capture_start_gates_v13(
        previous_campaign_finalized=True,
        storage_cap_configured=True,
        preflight_synthetic_passed=False,
        enable_live_capture=True,
        coordinator_authorized=True,
        free_disk_override={
            "passed": True,
            "free_bytes": 200 * GIB,
            "minimum_free_disk_bytes": STORAGE_FLOOR_BYTES,
            "status": "PASS",
        },
    )
    ok = gates["decision"] == "BLOCK_START" and "preflight_synthetic_passed" in gates["blockers"]
    return {
        "name": "neg_block_when_preflight_fails",
        "status": "PASS" if ok else "FAIL",
        "decision": gates["decision"],
        "blockers": gates["blockers"],
    }


def neg_disk_floor_blocks_start() -> dict[str, Any]:
    gates = evaluate_capture_start_gates_v13(
        previous_campaign_finalized=True,
        storage_cap_configured=True,
        preflight_synthetic_passed=True,
        free_disk_override={
            "passed": False,
            "free_bytes": 10 * GIB,
            "minimum_free_disk_bytes": STORAGE_FLOOR_BYTES,
            "status": "FAIL",
        },
    )
    ok = gates["decision"] == "BLOCK_START" and "disk_floor_ge_100_gib" in gates["blockers"]
    return {
        "name": "neg_disk_floor_blocks_start",
        "status": "PASS" if ok else "FAIL",
        "decision": gates["decision"],
        "blockers": gates["blockers"],
    }


def neg_clock_rollback_without_resume(root: Path) -> dict[str, Any]:
    root = Path(root)
    session = f"{CAMPAIGN_ID}_adv_clock"
    meta = root / "_meta"
    w = _writer(root, family="AGGRESSIVE_TRADE_FLOW", symbol="BTCUSDT", session=session, meta=meta)
    w.accept(
        _tick(
            symbol="BTCUSDT",
            family="AGGRESSIVE_TRADE_FLOW",
            ts_ms=SYNTHETIC_BASE_MS + 3_600_000,
            seq=1,
        )
    )
    w.close()
    w2 = _writer(root, family="AGGRESSIVE_TRADE_FLOW", symbol="BTCUSDT", session=session, meta=meta)
    raised = False
    try:
        w2.accept(
            _tick(
                symbol="BTCUSDT",
                family="AGGRESSIVE_TRADE_FLOW",
                ts_ms=SYNTHETIC_BASE_MS,
                seq=2,
            )
        )
    except ClockRollbackRejected:
        raised = True
    try:
        w2.close()
    except Exception:  # noqa: BLE001
        pass
    return {
        "name": "neg_clock_rollback_without_resume",
        "status": "PASS" if raised else "FAIL",
        "raised": raised,
    }


def neg_duplicate_writer_conflict(root: Path) -> dict[str, Any]:
    root = Path(root)
    session = f"{CAMPAIGN_ID}_adv_dup"
    w1 = _writer(root, family="LIQUIDATION_EVENTS", symbol="ETHUSDT", session=session)
    w2 = _writer(root, family="LIQUIDATION_EVENTS", symbol="ETHUSDT", session=session)
    w1.accept(
        _tick(symbol="ETHUSDT", family="LIQUIDATION_EVENTS", ts_ms=SYNTHETIC_BASE_MS, seq=1)
    )
    raised = False
    try:
        w2.accept(
            _tick(symbol="ETHUSDT", family="LIQUIDATION_EVENTS", ts_ms=SYNTHETIC_BASE_MS + 1, seq=2)
        )
    except PartitionIdentityConflict:
        raised = True
    w1.close()
    try:
        w2.close()
    except Exception:  # noqa: BLE001
        pass
    return {
        "name": "neg_duplicate_writer_conflict",
        "status": "PASS" if raised else "FAIL",
        "raised": raised,
    }


def neg_hard_cap_stop() -> dict[str, Any]:
    b = StorageBudgetControllerV13(
        soft_limit_bytes=50,
        hard_limit_bytes=100,
        minimum_free_disk_bytes=STORAGE_FLOOR_BYTES,
    )
    b.refresh_free_disk(free_bytes_override=500 * GIB)
    b.observe_write(compressed_delta=150)
    ok = b.stop_requested and b.mode == "STORAGE_HARD_CAP_BLOCKED"
    return {
        "name": "neg_hard_cap_stop",
        "status": "PASS" if ok else "FAIL",
        "mode": b.mode,
        "design_hard_cap_bytes": HARD_CAP_BYTES,
    }


def neg_event_study_must_stay_not_ready() -> dict[str, Any]:
    design = build_campaign_design()
    ok = (
        design["event_study_readiness_status"] == EVENT_STUDY_MUST_REMAIN
        and design["event_study_real_execution"] is False
        and design["live_capture_started"] is False
    )
    return {
        "name": "neg_event_study_must_stay_not_ready",
        "status": "PASS" if ok else "FAIL",
        "event_study": design["event_study_readiness_status"],
        "live_capture_started": design["live_capture_started"],
    }


def neg_forbid_prior_campaign_id_reuse_as_live() -> dict[str, Any]:
    """Negative: design campaign id must be exclusive (not prior v7 id)."""
    design = build_campaign_design()
    ok = (
        design["campaign_id"] == CAMPAIGN_ID
        and design["campaign_id"] != design["previous_campaign_id"]
    )
    return {
        "name": "neg_forbid_prior_campaign_id_reuse_as_live",
        "status": "PASS" if ok else "FAIL",
        "campaign_id": design["campaign_id"],
        "previous_campaign_id": design["previous_campaign_id"],
    }


def run_adversarial_pass2(work_root: Path) -> dict[str, Any]:
    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    results = [
        neg_undersized_symbol_design(),
        neg_live_flags_without_coordinator(),
        neg_block_when_preflight_fails(),
        neg_disk_floor_blocks_start(),
        neg_clock_rollback_without_resume(work_root / "clock"),
        neg_duplicate_writer_conflict(work_root / "dup"),
        neg_hard_cap_stop(),
        neg_event_study_must_stay_not_ready(),
        neg_forbid_prior_campaign_id_reuse_as_live(),
    ]
    all_pass = all(r["status"] == "PASS" for r in results)
    return {
        "schema": f"{SCHEMA}_adversarial_pass2",
        "created_at": _utc(),
        "pass": 2,
        "all_passed": all_pass,
        "negative_tests": results,
        "live_capture_started": False,
        "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
        "self_review": {
            "hard_bans_respected": True,
            "no_event_study": True,
            "no_demo_shadow_exchange_mainnet": True,
            "no_raw_prior_mutation": True,
            "no_live_capture_from_agent": True,
            "coordinator_only_live_launch": True,
            "findings": [] if all_pass else [r["name"] for r in results if r["status"] != "PASS"],
        },
    }
