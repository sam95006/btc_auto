"""Bounded resume controller — checkpoint metadata only; no live capture start."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_microstructure.ops_v10.constants import SCHEMA


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BoundedResumeController:
    """Build and validate bounded-resume checkpoints for a campaign segment."""

    def __init__(self, *, campaign_id: str) -> None:
        self.campaign_id = campaign_id
        self.checkpoint: dict[str, Any] | None = None

    def create_checkpoint(
        self,
        *,
        last_partition_id: str | None,
        capture_session_ids: list[str] | None = None,
        valid_capture_seconds: int = 0,
        connection_gap_seconds: int = 0,
        clean_shutdown: bool = True,
        resumable: bool = True,
    ) -> dict[str, Any]:
        self.checkpoint = {
            "schema": f"{SCHEMA}_bounded_resume_checkpoint",
            "campaign_id": self.campaign_id,
            "resumable": bool(resumable and clean_shutdown),
            "last_checkpoint_at": _utc(),
            "last_partition_id": last_partition_id,
            "capture_session_ids": list(capture_session_ids or []),
            "valid_capture_seconds": int(valid_capture_seconds),
            "connection_gap_seconds": int(connection_gap_seconds),
            "clean_shutdown": clean_shutdown,
            "bounded": True,
            "live_capture_started": False,
            "note": "Resume metadata only; does not start capture",
        }
        return self.checkpoint

    def from_finalizer_resume_metadata(self, meta: dict[str, Any]) -> dict[str, Any]:
        """Import resume fields from a finalizer artifact without mutating live state."""
        return self.create_checkpoint(
            last_partition_id=meta.get("last_partition_id"),
            capture_session_ids=list(meta.get("capture_session_ids") or []),
            valid_capture_seconds=int(meta.get("valid_capture_seconds") or 0),
            connection_gap_seconds=int(meta.get("connection_gap_seconds") or 0),
            clean_shutdown=bool(meta.get("clean_shutdown")),
            # Real ms_accum_v7 finalize reported resumable=false — honor that.
            resumable=bool(meta.get("resumable", False)),
        )

    def allow_bounded_resume(self) -> dict[str, Any]:
        cp = self.checkpoint or {}
        allowed = bool(cp.get("resumable")) and bool(cp.get("clean_shutdown"))
        return {
            "schema": f"{SCHEMA}_bounded_resume_decision",
            "campaign_id": self.campaign_id,
            "allow_bounded_resume": allowed,
            "checkpoint": cp,
            "live_capture_started": False,
            "reason": "checkpoint_resumable" if allowed else "resume_blocked_or_missing",
        }
