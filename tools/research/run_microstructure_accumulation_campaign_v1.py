#!/usr/bin/env python3
"""Start/resume bounded microstructure accumulation campaign (public readonly)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"

    from backend.nexus_microstructure.accumulation_campaign_v1 import AccumulationCampaignRegistry, DEFAULT_CAMPAIGN
    from backend.nexus_microstructure.collector_v12 import run_bounded_capture_v12

    reg = AccumulationCampaignRegistry(ROOT / ".nexus_runtime/microstructure/campaigns/registry.json")
    campaign_id = os.getenv("NEXUS_MS_CAMPAIGN_ID", "ms_accum_v7_bounded_24h")
    if campaign_id not in (reg.data.get("campaigns") or {}):
        reg.start_campaign(campaign_id)
    camp = reg.data["campaigns"][campaign_id]
    cfg = {**DEFAULT_CAMPAIGN, **(camp.get("config") or {})}

    # Segmented capture so laptop sleep can resume same campaign.
    segment_hours = float(os.getenv("NEXUS_MS_SEGMENT_HOURS", "24"))
    duration_minutes = segment_hours * 60.0
    resume = bool(camp.get("session_ids"))
    print(
        json.dumps(
            {
                "campaign_id": campaign_id,
                "duration_minutes": duration_minutes,
                "symbol_count": cfg["symbol_count"],
                "hard_storage_cap_bytes": cfg["hard_storage_cap_bytes"],
                "resume": resume,
            }
        ),
        flush=True,
    )
    t0 = time.time()
    result = run_bounded_capture_v12(
        root=ROOT,
        duration_minutes=duration_minutes,
        symbol_count=int(cfg["symbol_count"]),
        hard_storage_cap_bytes=int(cfg["hard_storage_cap_bytes"]),
        soft_storage_cap_bytes=int(cfg["soft_storage_cap_bytes"]),
        run_label="ACCUM24",
        accumulation_run_id=campaign_id,
        resume=resume,
    )
    elapsed = time.time() - t0
    valid = int(elapsed) if (result.get("shutdown") or {}).get("capture_session_stopped_cleanly") else 0
    gap = 0
    if not (result.get("shutdown") or {}).get("capture_session_stopped_cleanly"):
        gap = int(elapsed)
    updated = reg.update_session(
        campaign_id,
        {
            "capture_session_id": result.get("capture_session_id"),
            "aggressive_trade_event_count": result.get("aggressive_trade_event_count"),
            "liquidation_event_count": result.get("liquidation_event_count"),
            "partition_count": result.get("partition_count"),
            "compressed_bytes": (result.get("budget") or {}).get("current_compressed_partition_bytes") or 0,
            "valid_capture_seconds": valid,
            "connection_gap_seconds": gap,
            "symbols": result.get("symbols") or [],
            "clock_quality": "PASS" if (result.get("clock") or {}) else "UNKNOWN",
            "memory_quality": (result.get("memory") or {}).get("memory_growth_status"),
            "storage_quality": (result.get("budget") or {}).get("mode"),
            "status": "RUNNING" if valid and elapsed < duration_minutes * 60 else "SEGMENT_COMPLETE",
        },
    )
    out = ROOT / "artifacts/readiness/immutable/microstructure_accumulation_campaign_v1/campaign_status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **updated,
        "planned_duration_hours": cfg["duration_hours"],
        "storage_cap_respected": (result.get("budget") or {}).get("mode") != "STORAGE_BUDGET_BLOCKED"
        or (result.get("shutdown") or {}).get("capture_session_stopped_cleanly"),
        "checksum_status": "PASS"
        if (result.get("shutdown") or {}).get("checksum_replay_verified")
        else "FAIL",
        "capture_stopped_cleanly": (result.get("shutdown") or {}).get("capture_session_stopped_cleanly"),
        "event_study_readiness_status": "NOT_READY",
        "new_strategy_generated_count": 0,
        "profitability_claim_count": 0,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"campaign_id": campaign_id, "events": result.get("event_count"), "clean": payload["capture_stopped_cleanly"]}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
