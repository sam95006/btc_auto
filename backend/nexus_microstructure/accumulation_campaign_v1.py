"""Bounded microstructure accumulation campaign registry and controller."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


DEFAULT_CAMPAIGN = {
    "duration_hours": 24,
    "symbol_count": 25,
    "hard_storage_cap_bytes": 1073741824,
    "soft_storage_cap_bytes": 805306368,
    "minimum_free_disk_bytes": 5368709120,
    "families": ["AGGRESSIVE_TRADE_FLOW", "LIQUIDATION_EVENTS"],
    "capture_mode": "BYBIT_PUBLIC_READONLY",
    "checkpoint_interval_minutes": 5,
    "health_interval_seconds": 60,
}


class AccumulationCampaignRegistry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {
            "schema": "microstructure_accumulation_campaign_v1",
            "campaigns": {},
            "updated_at": _utc(),
        }
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.data["updated_at"] = _utc()
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")

    def start_campaign(self, campaign_id: str, **cfg: Any) -> dict[str, Any]:
        conf = {**DEFAULT_CAMPAIGN, **cfg}
        camp = {
            "campaign_id": campaign_id,
            "session_ids": [],
            "started_at": _utc(),
            "last_updated_at": _utc(),
            "config": conf,
            "valid_capture_seconds": 0,
            "connection_gap_seconds": 0,
            "complete_UTC_hours": 0,
            "partial_UTC_hours": 0,
            "symbol_coverage": [],
            "trade_event_count": 0,
            "liquidation_event_count": 0,
            "partition_count": 0,
            "compressed_bytes": 0,
            "integrity_failures": 0,
            "clock_quality": "UNKNOWN",
            "memory_quality": "UNKNOWN",
            "storage_quality": "UNKNOWN",
            "status": "PLANNED",
        }
        self.data.setdefault("campaigns", {})[campaign_id] = camp
        self.save()
        return camp

    def update_session(self, campaign_id: str, session: dict[str, Any]) -> dict[str, Any]:
        camp = self.data["campaigns"][campaign_id]
        sid = session.get("capture_session_id") or session.get("session_id")
        if sid and sid not in camp["session_ids"]:
            camp["session_ids"].append(sid)
        camp["last_updated_at"] = _utc()
        camp["trade_event_count"] += int(session.get("trade_event_count") or session.get("aggressive_trade_event_count") or 0)
        camp["liquidation_event_count"] += int(session.get("liquidation_event_count") or 0)
        camp["partition_count"] += int(session.get("partition_count") or 0)
        camp["compressed_bytes"] += int(session.get("compressed_bytes") or 0)
        camp["valid_capture_seconds"] += int(session.get("valid_capture_seconds") or 0)
        camp["connection_gap_seconds"] += int(session.get("connection_gap_seconds") or 0)
        if session.get("symbols"):
            camp["symbol_coverage"] = sorted(set(camp["symbol_coverage"]) | set(session["symbols"]))
        for k in ("clock_quality", "memory_quality", "storage_quality", "status"):
            if session.get(k):
                camp[k] = session[k]
        # Never equate calendar elapsed with valid capture.
        camp["valid_capture_hours"] = camp["valid_capture_seconds"] / 3600.0
        self.save()
        return camp


def plan_bounded_campaign(root: Path) -> dict[str, Any]:
    """Create campaign registry entry. Actual 24h capture starts only when explicitly enabled."""
    reg_path = root / ".nexus_runtime/microstructure/campaigns/registry.json"
    reg = AccumulationCampaignRegistry(reg_path)
    campaign_id = os.getenv("NEXUS_MS_CAMPAIGN_ID", f"ms_accum_{int(time.time())}")
    camp = reg.start_campaign(campaign_id)
    enable = os.getenv("NEXUS_MS_START_24H_ACCUMULATION", "0") == "1"
    status = {
        "schema": "microstructure_accumulation_campaign_v1_status",
        "campaign_id": campaign_id,
        "planned_duration_hours": camp["config"]["duration_hours"],
        "valid_capture_hours": 0.0,
        "connection_gap_seconds": 0,
        "complete_UTC_hours": 0,
        "partial_UTC_hours": 0,
        "trade_event_count": 0,
        "liquidation_event_count": 0,
        "compressed_bytes": 0,
        "storage_cap_respected": True,
        "memory_status": "NOT_STARTED",
        "clock_status": "NOT_STARTED",
        "checksum_status": "NOT_STARTED",
        "accumulation_started": enable,
        "note": "24h capture starts only when NEXUS_MS_START_24H_ACCUMULATION=1 after durability ready",
        "created_at": _utc(),
    }
    return status
