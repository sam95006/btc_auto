"""Campaign registry V10 — tracks planned / running / finalized campaigns."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.ops_v10.constants import SCHEMA
from backend.nexus_microstructure.storage_budget_v10 import (
    DEFAULT_HARD_CAP_BYTES,
    DEFAULT_MINIMUM_FREE_DISK_BYTES,
    DEFAULT_SOFT_CAP_BYTES,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


DEFAULT_CONFIG: dict[str, Any] = {
    "duration_hours": 24,
    "symbol_count": 25,
    "soft_storage_cap_bytes": DEFAULT_SOFT_CAP_BYTES,
    "hard_storage_cap_bytes": DEFAULT_HARD_CAP_BYTES,
    "minimum_free_disk_bytes": DEFAULT_MINIMUM_FREE_DISK_BYTES,
    "families": ["AGGRESSIVE_TRADE_FLOW", "LIQUIDATION_EVENTS"],
    "capture_mode": "BYBIT_PUBLIC_READONLY",
    "exchange_write": False,
    "event_study_allowed": False,
    "strategy_generation_allowed": False,
}


class CampaignRegistryV10:
    """Persistent registry for microstructure campaigns (ops lane)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {
            "schema": f"{SCHEMA}_campaign_registry",
            "campaigns": {},
            "updated_at": _utc(),
        }
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.data["updated_at"] = _utc()
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")

    def get(self, campaign_id: str) -> dict[str, Any] | None:
        return (self.data.get("campaigns") or {}).get(campaign_id)

    def list_campaigns(self) -> dict[str, Any]:
        return dict(self.data.get("campaigns") or {})

    def register_campaign(self, campaign_id: str, **cfg: Any) -> dict[str, Any]:
        conf = {**DEFAULT_CONFIG, **cfg}
        camp = {
            "campaign_id": campaign_id,
            "status": "PLANNED",
            "finalized": False,
            "session_ids": [],
            "started_at": None,
            "finalized_at": None,
            "last_updated_at": _utc(),
            "config": conf,
            "storage_cap_configured": bool(
                conf.get("soft_storage_cap_bytes") and conf.get("hard_storage_cap_bytes")
            ),
            "resume_checkpoint": None,
            "safe_stop": None,
            "integrity_score": None,
            "event_study_readiness_status": "NOT_READY",
            "live_capture_started": False,
            "new_strategy_generated_count": 0,
            "exchange_write_attempt_count": 0,
        }
        self.data.setdefault("campaigns", {})[campaign_id] = camp
        self.save()
        return camp

    def mark_running(self, campaign_id: str, *, session_id: str | None = None) -> dict[str, Any]:
        camp = self.data["campaigns"][campaign_id]
        camp["status"] = "RUNNING"
        camp["started_at"] = camp.get("started_at") or _utc()
        camp["last_updated_at"] = _utc()
        if session_id and session_id not in camp["session_ids"]:
            camp["session_ids"].append(session_id)
        self.save()
        return camp

    def mark_finalized(
        self,
        campaign_id: str,
        *,
        finalizer_status: str,
        integrity_status: str,
        artifact_dir: str | None = None,
    ) -> dict[str, Any]:
        camp = self.data["campaigns"][campaign_id]
        camp["status"] = "FINALIZED"
        camp["finalized"] = True
        camp["finalized_at"] = _utc()
        camp["last_updated_at"] = _utc()
        camp["finalizer_status"] = finalizer_status
        camp["integrity_status"] = integrity_status
        camp["finalizer_artifact_dir"] = artifact_dir
        camp["event_study_readiness_status"] = "NOT_READY"
        self.save()
        return camp

    def mark_safe_stopped(self, campaign_id: str, reason: str) -> dict[str, Any]:
        camp = self.data["campaigns"][campaign_id]
        camp["status"] = "SAFE_STOPPED"
        camp["safe_stop"] = {"reason": reason, "at": _utc()}
        camp["last_updated_at"] = _utc()
        camp["live_capture_started"] = False
        self.save()
        return camp

    def set_resume_checkpoint(self, campaign_id: str, checkpoint: dict[str, Any]) -> dict[str, Any]:
        camp = self.data["campaigns"][campaign_id]
        camp["resume_checkpoint"] = checkpoint
        camp["last_updated_at"] = _utc()
        self.save()
        return camp

    def previous_campaign_finalized(self, campaign_id: str) -> bool:
        camp = self.get(campaign_id)
        if not camp:
            return False
        return bool(camp.get("finalized")) and camp.get("status") == "FINALIZED"

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": f"{SCHEMA}_campaign_registry",
            "campaign_count": len(self.data.get("campaigns") or {}),
            "campaigns": self.list_campaigns(),
            "updated_at": self.data.get("updated_at"),
            "event_study_readiness_status": "NOT_READY",
            "event_study_real_execution": False,
            "new_strategy_generated_count": 0,
        }
