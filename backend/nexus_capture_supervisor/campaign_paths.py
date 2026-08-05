"""Resolve campaign observation paths without mutating collector state."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import (
    CAMPAIGN_ID,
    DEFAULT_RUNTIME,
)


@dataclass(frozen=True)
class CampaignPaths:
    """Explicit path map for one live campaign observation target."""

    campaign_id: str
    runtime_root: Path
    capture_worktree: Path
    partitions_root: Path
    registry_path: Path
    checkpoint_path: Path
    launch_json: Path
    stdout_log: Path
    stderr_log: Path

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "runtime_root": str(self.runtime_root),
            "capture_worktree": str(self.capture_worktree),
            "partitions_root": str(self.partitions_root),
            "registry_path": str(self.registry_path),
            "checkpoint_path": str(self.checkpoint_path),
            "launch_json": str(self.launch_json),
            "stdout_log": str(self.stdout_log),
            "stderr_log": str(self.stderr_log),
        }


def load_launch_metadata(runtime_root: Path, campaign_id: str = CAMPAIGN_ID) -> dict[str, Any]:
    path = Path(runtime_root) / f"{campaign_id}_launch.json"
    if not path.is_file():
        return {
            "status": "MISSING",
            "path": str(path),
            "reason": "launch_json_absent",
            "silent_fallback": False,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "UNREADABLE",
            "path": str(path),
            "reason": f"{type(exc).__name__}:{exc}",
            "silent_fallback": False,
        }
    data["_path"] = str(path)
    data["status"] = "OK"
    return data


def resolve_campaign_paths(
    *,
    runtime_root: Path | str | None = None,
    capture_worktree: Path | str | None = None,
    campaign_id: str = CAMPAIGN_ID,
) -> tuple[CampaignPaths, dict[str, Any]]:
    """Resolve paths from launch metadata; never invent missing roots."""
    runtime = Path(runtime_root or DEFAULT_RUNTIME)
    launch = load_launch_metadata(runtime, campaign_id)
    notes: list[str] = []

    wt: Path | None = None
    if capture_worktree is not None:
        wt = Path(capture_worktree)
    elif launch.get("status") == "OK" and launch.get("worktree"):
        wt = Path(str(launch["worktree"]))
    else:
        notes.append("capture_worktree_unresolved")

    if wt is None:
        # Explicit sentinel — callers must treat partitions as unavailable.
        wt = runtime / "_UNRESOLVED_CAPTURE_WORKTREE"
        notes.append("using_unresolved_sentinel_path")

    partitions = wt / ".nexus_runtime" / "microstructure" / "v1_2"
    registry = wt / ".nexus_runtime" / "microstructure" / "campaigns" / "registry.json"
    checkpoint = partitions / f"{campaign_id}.checkpoint.json"

    paths = CampaignPaths(
        campaign_id=campaign_id,
        runtime_root=runtime,
        capture_worktree=wt,
        partitions_root=partitions,
        registry_path=registry,
        checkpoint_path=checkpoint,
        launch_json=runtime / f"{campaign_id}_launch.json",
        stdout_log=runtime / f"{campaign_id}_stdout.log",
        stderr_log=runtime / f"{campaign_id}_stderr.log",
    )
    meta = {
        "launch_status": launch.get("status"),
        "launch_pid": launch.get("capture_PID"),
        "live_capture_started": bool(launch.get("live_capture_started"))
        if launch.get("status") == "OK"
        else None,
        "notes": notes,
        "silent_fallback": False,
        "launch": {k: v for k, v in launch.items() if not str(k).startswith("_") or k == "_path"},
    }
    return paths, meta
