"""Duplicate writer detection (read-only)."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.process_liveness import _pid_alive
from backend.nexus_capture_supervisor.util import finding, read_json, utc_stamp


def detect_duplicate_writers(
    *,
    runtime_root: Path,
    campaign_id: str,
    partitions_root: Path,
    launch: dict[str, Any] | None = None,
    health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_root = Path(runtime_root)
    launch = launch if launch is not None else read_json(runtime_root / f"{campaign_id}_launch.json")
    health = health if health is not None else read_json(runtime_root / f"{campaign_id}_health.json")
    findings: list[dict[str, Any]] = []

    parent_pid = launch.get("capture_PID") if launch.get("status") == "OK" else None
    worker_pid = launch.get("capture_worker_PID") if launch.get("status") == "OK" else None
    if health.get("status") == "OK":
        parent_pid = health.get("capture_PID", parent_pid)
        worker_pid = health.get("capture_worker_PID", worker_pid)

    # Session id multiplicity from partition filenames.
    sessions: dict[str, int] = defaultdict(int)
    partition_ids: dict[str, list[str]] = defaultdict(list)
    root = Path(partitions_root)
    if root.is_dir():
        for gz in root.rglob("*.jsonl.gz"):
            name = gz.name.replace(".jsonl.gz", "")
            # session is prefix before family token typically ms12_...
            parts = name.split("_")
            # Heuristic: session id is everything before FAMILY
            session = None
            for i, p in enumerate(parts):
                if p in {"AGGRESSIVE", "LIQUIDATION"} or p.endswith("EVENTS") or p == "TRADE":
                    break
            # Better: known pattern ms12_ACCUM24_<n>_FAMILY_...
            if "LIQUIDATION_EVENTS" in name:
                session = name.split("_LIQUIDATION_EVENTS_")[0]
            elif "AGGRESSIVE_TRADE_FLOW" in name:
                session = name.split("_AGGRESSIVE_TRADE_FLOW_")[0]
            if session:
                sessions[session] += 1
            # partition identity = full stem
            partition_ids[name].append(str(gz))

    dup_paths = {pid: paths for pid, paths in partition_ids.items() if len(paths) > 1}
    if dup_paths:
        findings.append(
            finding(
                code="DUPLICATE_PARTITION_PATHS",
                severity="CRITICAL",
                summary="Identical partition_id maps to multiple paths",
                evidence={"count": len(dup_paths), "examples": list(dup_paths.items())[:5]},
                recommendation="Coordinator: safe-stop immediately; exclusive ID invariant broken",
            )
        )

    multi_session = len(sessions) > 1
    if multi_session:
        findings.append(
            finding(
                code="MULTIPLE_CAPTURE_SESSIONS",
                severity="HIGH",
                summary="Multiple capture_session_id values observed under one campaign tree",
                evidence={"sessions": dict(sessions)},
                recommendation="Verify intentional resume boundary; reject concurrent dual writers",
            )
        )

    # Extra python processes claiming same launch logs — soft signal only via PID mismatch health vs launch
    pid_mismatch = False
    if (
        launch.get("status") == "OK"
        and health.get("status") == "OK"
        and launch.get("capture_PID") is not None
        and health.get("capture_PID") is not None
        and int(launch["capture_PID"]) != int(health["capture_PID"])
    ):
        pid_mismatch = True
        findings.append(
            finding(
                code="LAUNCH_HEALTH_PID_MISMATCH",
                severity="CRITICAL",
                summary="Launch capture_PID disagrees with health capture_PID",
                evidence={
                    "launch_pid": launch.get("capture_PID"),
                    "health_pid": health.get("capture_PID"),
                },
                recommendation="Possible duplicate/replaced writer — Coordinator investigate before restart",
            )
        )

    parent = _pid_alive(parent_pid)
    worker = _pid_alive(worker_pid)

    status = "OK"
    if any(f["severity"] == "CRITICAL" for f in findings):
        status = "DUPLICATE_SUSPECTED"
    elif findings:
        status = "WARN"

    return {
        "schema": "v14_a_duplicate_writer_detection",
        "observed_at": utc_stamp(),
        "campaign_id": campaign_id,
        "status": status,
        "parent": parent,
        "worker": worker,
        "session_counts": dict(sessions),
        "session_count": len(sessions),
        "duplicate_partition_id_count": len(dup_paths),
        "launch_health_pid_mismatch": pid_mismatch,
        "findings": findings,
        "policy": {
            "exclusive_partition_ids": True,
            "allow_concurrent_writers": False,
        },
        "silent_fallback": False,
        "exchange_write_attempt_count": 0,
    }
