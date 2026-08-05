"""14-day microstructure campaign design (ops-only; does not launch collector)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_microstructure.ops_v13.constants import (
    CAMPAIGN_ID,
    DAILY_INTEGRITY_SEAL,
    DESIGN_SYMBOLS_25,
    EVENT_STUDY_MUST_REMAIN,
    FAMILIES,
    HARD_CAP_BYTES,
    HOURLY_ROTATION,
    MIN_SYMBOL_COUNT,
    PREVIOUS_CAMPAIGN_ID,
    SCHEMA,
    SOFT_CAP_BYTES,
    STORAGE_FLOOR_BYTES,
    TARGET_CALENDAR_DAYS,
    GIB,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_campaign_design(*, symbols: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Authoritative design document for ms_accum_v13_integrity_14d."""
    syms = tuple(symbols or DESIGN_SYMBOLS_25)
    if len(syms) < MIN_SYMBOL_COUNT:
        raise ValueError(f"design requires >= {MIN_SYMBOL_COUNT} symbols, got {len(syms)}")
    return {
        "schema": f"{SCHEMA}_campaign_design",
        "created_at": _utc(),
        "campaign_id": CAMPAIGN_ID,
        "previous_campaign_id": PREVIOUS_CAMPAIGN_ID,
        "target_calendar_days": TARGET_CALENDAR_DAYS,
        "symbol_count": len(syms),
        "symbols": list(syms),
        "families": list(FAMILIES),
        "exchange_design": "BYBIT_PUBLIC_READONLY",
        "storage": {
            "floor_free_disk_bytes": STORAGE_FLOOR_BYTES,
            "floor_free_disk_gib": STORAGE_FLOOR_BYTES // GIB,
            "hard_cap_bytes": HARD_CAP_BYTES,
            "hard_cap_gib": HARD_CAP_BYTES // GIB,
            "soft_cap_bytes": SOFT_CAP_BYTES,
            "soft_cap_gib": round(SOFT_CAP_BYTES / GIB, 3),
        },
        "durability": {
            "exclusive_partition_ids": True,
            "atomic_manifest": True,
            "open_tail_seal": True,
            "persistent_clock": True,
            "resume_safe_linkage": True,
            "hourly_rotation": HOURLY_ROTATION,
            "daily_integrity_seal": DAILY_INTEGRITY_SEAL,
            "automatic_safe_stop": True,
        },
        "writer_stack": "collector_cutover_v2.DurablePartitionWriterV2",
        "live_capture_started": False,
        "live_capture_authorized_by_this_lane": False,
        "coordinator_only_live_launch": True,
        "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
        "event_study_real_execution": False,
        "raw_prior_campaign_modified": False,
        "demo_shadow_exchange_mainnet_banned": True,
        "hard_bans": [
            "no_event_study",
            "no_demo_shadow_exchange_mainnet",
            "no_PR27_merge",
            "no_G_deletion",
            "no_raw_prior_campaign_modification",
            "no_live_capture_from_this_agent",
        ],
        "preflight_required_before_live": [
            "synthetic_24h_logical_capture",
            "forced_crash_restart",
            "clock_rollback",
            "disk_floor",
            "duplicate_writer",
            "manifest_interrupt",
            "open_tail_recovery",
        ],
        "note": (
            "Design + synthetic ops only. Local Coordinator alone may launch the real "
            "collector after gates PASS; this lane must keep live_capture_started=false."
        ),
    }
