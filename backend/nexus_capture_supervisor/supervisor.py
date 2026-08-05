"""Orchestrate read-only live capture integrity observation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.campaign_paths import resolve_campaign_paths
from backend.nexus_capture_supervisor.clock_heartbeat import observe_clock_heartbeat
from backend.nexus_capture_supervisor.constants import (
    CAMPAIGN_ID,
    DEFAULT_DISK_ROOT,
    DEFAULT_RUNTIME,
    EVENT_STUDY_MUST_REMAIN,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OPS_ROLE,
    SCHEMA,
    STORAGE_VELOCITY_SAMPLE_SECONDS,
)
from backend.nexus_capture_supervisor.duplicate_writer import detect_duplicate_writers
from backend.nexus_capture_supervisor.manifest_sampling import sample_manifests_and_checksums
from backend.nexus_capture_supervisor.open_tail import account_open_tails
from backend.nexus_capture_supervisor.partition_accounting import account_partitions
from backend.nexus_capture_supervisor.process_liveness import observe_process_liveness
from backend.nexus_capture_supervisor.recommendations import build_recommendations
from backend.nexus_capture_supervisor.storage_projection import measure_storage_velocity, project_disk
from backend.nexus_capture_supervisor.util import read_json, utc_stamp
from backend.nexus_capture_supervisor.ws_health import observe_ws_health


class CaptureIntegritySupervisor:
    """Observe live campaign integrity; never mutate collector or execute stop/restart."""

    def __init__(
        self,
        *,
        runtime_root: Path | str = DEFAULT_RUNTIME,
        disk_root: str = DEFAULT_DISK_ROOT,
        campaign_id: str = CAMPAIGN_ID,
        capture_worktree: Path | str | None = None,
        velocity_sample_seconds: float = float(STORAGE_VELOCITY_SAMPLE_SECONDS),
    ) -> None:
        self.runtime_root = Path(runtime_root)
        self.disk_root = disk_root
        self.campaign_id = campaign_id
        self.capture_worktree = Path(capture_worktree) if capture_worktree else None
        self.velocity_sample_seconds = velocity_sample_seconds

    def observe(self, *, prior_storage_bytes: int | None = None, prior_storage_ts: float | None = None) -> dict[str, Any]:
        paths, path_meta = resolve_campaign_paths(
            runtime_root=self.runtime_root,
            capture_worktree=self.capture_worktree,
            campaign_id=self.campaign_id,
        )
        launch = read_json(paths.launch_json)
        health = read_json(self.runtime_root / f"{self.campaign_id}_health.json")

        process = observe_process_liveness(
            runtime_root=self.runtime_root,
            campaign_id=self.campaign_id,
            launch=launch,
            health=health,
        )
        ws = observe_ws_health(
            runtime_root=self.runtime_root,
            campaign_id=self.campaign_id,
            checkpoint_path=paths.checkpoint_path,
            health=health,
            process_report=process,
        )
        capture_start = launch.get("capture_start_UTC") if launch.get("status") == "OK" else None
        symbol_count = int(launch.get("symbol_count") or 25) if launch.get("status") == "OK" else 25
        partitions = account_partitions(
            partitions_root=paths.partitions_root,
            campaign_id=self.campaign_id,
            capture_start_utc=capture_start,
            expected_symbol_count=symbol_count,
        )
        clock = observe_clock_heartbeat(
            runtime_root=self.runtime_root,
            campaign_id=self.campaign_id,
            checkpoint_path=paths.checkpoint_path,
            partitions_root=paths.partitions_root,
            health=health,
            capture_start_utc=capture_start,
        )
        velocity = measure_storage_velocity(
            partitions_root=paths.partitions_root,
            sample_seconds=self.velocity_sample_seconds,
            prior_bytes=prior_storage_bytes,
            prior_ts=prior_storage_ts,
        )
        storage = project_disk(
            disk_root=self.disk_root,
            campaign_bytes=int(velocity.get("bytes") or 0),
            bytes_per_second=float(velocity.get("bytes_per_second") or 0.0),
        )
        storage["velocity"] = velocity
        manifests = sample_manifests_and_checksums(
            partitions_root=paths.partitions_root,
            campaign_id=self.campaign_id,
        )
        open_tail = account_open_tails(
            partitions_root=paths.partitions_root,
            campaign_id=self.campaign_id,
        )
        dup = detect_duplicate_writers(
            runtime_root=self.runtime_root,
            campaign_id=self.campaign_id,
            partitions_root=paths.partitions_root,
            launch=launch,
            health=health,
        )

        observation = {
            "schema": SCHEMA,
            "lane": LANE,
            "lane_name": LANE_NAME,
            "observed_at": utc_stamp(),
            "campaign_id": self.campaign_id,
            "ops_role": OPS_ROLE,
            "hard_bans": list(HARD_BANS),
            "paths": paths.as_dict(),
            "path_meta": path_meta,
            "process_liveness": process,
            "ws_health": ws,
            "partition_accounting": partitions,
            "clock_heartbeat": clock,
            "storage": storage,
            "manifest_sampling": manifests,
            "open_tail": open_tail,
            "duplicate_writer": dup,
            "event_study_readiness_status": EVENT_STUDY_MUST_REMAIN,
            "event_study_real_execution": False,
            "exchange_write_attempt_count": 0,
            "collector_modified": False,
            "live_stop_executed": False,
            "restart_executed": False,
        }
        observation["recommendations"] = build_recommendations(observation=observation)

        all_findings: list[dict[str, Any]] = []
        for key in (
            "process_liveness",
            "ws_health",
            "partition_accounting",
            "clock_heartbeat",
            "storage",
            "manifest_sampling",
            "open_tail",
            "duplicate_writer",
        ):
            all_findings.extend((observation.get(key) or {}).get("findings") or [])
        observation["findings"] = all_findings
        observation["critical_findings"] = [f for f in all_findings if f.get("severity") == "CRITICAL"]
        observation["high_findings"] = [f for f in all_findings if f.get("severity") == "HIGH"]
        observation["integrity_status"] = _roll_up_status(observation)
        return observation


def _roll_up_status(observation: dict[str, Any]) -> str:
    if observation.get("critical_findings"):
        return "CRITICAL"
    if observation.get("recommendations", {}).get("safe_stop_required"):
        return "SAFE_STOP_RECOMMENDED"
    if observation.get("high_findings"):
        return "DEGRADED"
    process = (observation.get("process_liveness") or {}).get("status")
    if process == "LIVE":
        return "LIVE_OK"
    return "UNKNOWN"
