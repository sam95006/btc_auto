"""Process liveness observation for the live capture campaign (read-only)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import PROCESS_STALE_SECONDS
from backend.nexus_capture_supervisor.util import finding, parse_iso_utc, read_json, utc_now, utc_stamp


def _pid_alive(pid: int | None) -> dict[str, Any]:
    if pid is None or int(pid) <= 0:
        return {"pid": pid, "alive": False, "reason": "pid_missing_or_invalid"}
    pid_i = int(pid)
    try:
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            SYNCHRONIZE = 0x00100000
            handle = kernel32.OpenProcess(SYNCHRONIZE, 0, pid_i)
            if handle:
                kernel32.CloseHandle(handle)
                return {"pid": pid_i, "alive": True, "reason": "open_process_ok"}
            err = kernel32.GetLastError()
            return {"pid": pid_i, "alive": False, "reason": f"open_process_failed:{err}"}
        # POSIX: signal 0 probe
        os.kill(pid_i, 0)
        return {"pid": pid_i, "alive": True, "reason": "signal0_ok"}
    except OSError as exc:
        return {"pid": pid_i, "alive": False, "reason": f"{type(exc).__name__}:{exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"pid": pid_i, "alive": False, "reason": f"{type(exc).__name__}:{exc}"}


def observe_process_liveness(
    *,
    runtime_root: Path,
    campaign_id: str,
    launch: dict[str, Any] | None = None,
    health: dict[str, Any] | None = None,
    stale_seconds: int = PROCESS_STALE_SECONDS,
) -> dict[str, Any]:
    runtime_root = Path(runtime_root)
    launch = launch if launch is not None else read_json(runtime_root / f"{campaign_id}_launch.json")
    health = health if health is not None else read_json(runtime_root / f"{campaign_id}_health.json")

    capture_pid = launch.get("capture_PID") if launch.get("status") == "OK" else None
    worker_pid = None
    if launch.get("status") == "OK":
        worker_pid = launch.get("capture_worker_PID")
    if health.get("status") == "OK":
        capture_pid = health.get("capture_PID", capture_pid)
        worker_pid = health.get("capture_worker_PID", worker_pid)

    parent = _pid_alive(capture_pid)
    worker = _pid_alive(worker_pid)

    health_age_s: float | None = None
    health_stale = False
    checked_at = health.get("checked_at") if health.get("status") == "OK" else None
    checked_dt = parse_iso_utc(checked_at)
    if checked_dt is not None:
        health_age_s = (utc_now() - checked_dt).total_seconds()
        health_stale = health_age_s > float(stale_seconds)

    findings: list[dict[str, Any]] = []
    if not parent["alive"]:
        findings.append(
            finding(
                code="PROCESS_PARENT_DEAD",
                severity="CRITICAL",
                summary="Capture parent PID is not alive",
                evidence=parent,
                recommendation="Coordinator: investigate crash; prefer graceful restart only after open-tail fence",
            )
        )
    if worker_pid and not worker["alive"]:
        findings.append(
            finding(
                code="PROCESS_WORKER_DEAD",
                severity="CRITICAL",
                summary="Capture worker PID is not alive",
                evidence=worker,
                recommendation="Coordinator: safe-stop + graceful restart; do not dual-start writers",
            )
        )
    if health.get("status") != "OK":
        findings.append(
            finding(
                code="HEALTH_FILE_MISSING",
                severity="HIGH",
                summary="Campaign health JSON missing or unreadable",
                evidence={"health_status": health.get("status"), "path": health.get("path")},
                recommendation="Ensure coordinator health sampler is running (read-only)",
            )
        )
    elif health_stale:
        findings.append(
            finding(
                code="HEALTH_STALE",
                severity="HIGH",
                summary=f"Health file older than {stale_seconds}s",
                evidence={"checked_at": checked_at, "age_seconds": health_age_s},
                recommendation="Refresh health sampler; treat WS health as degraded until fresh",
            )
        )

    both_alive = bool(parent["alive"] and (worker_pid is None or worker["alive"]))
    status = "LIVE" if both_alive and not health_stale else ("DEGRADED" if both_alive else "DOWN")

    return {
        "schema": "v14_a_process_liveness",
        "observed_at": utc_stamp(),
        "campaign_id": campaign_id,
        "status": status,
        "parent": parent,
        "worker": worker,
        "health_status": health.get("status"),
        "health_age_seconds": health_age_s,
        "health_stale": health_stale,
        "live_capture_started": bool(launch.get("live_capture_started"))
        if launch.get("status") == "OK"
        else None,
        "findings": findings,
        "mute_collector": True,
        "exchange_write_attempt_count": 0,
    }
