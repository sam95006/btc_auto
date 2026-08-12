"""Clock / heartbeat quality observation from read-only surfaces."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import (
    CLOCK_ROLLBACK_TOLERANCE_MS,
    CLOCK_SKEW_CRITICAL_MS,
    CLOCK_SKEW_WARN_MS,
    HEARTBEAT_STALE_SECONDS,
)
from backend.nexus_capture_supervisor.util import finding, parse_iso_utc, read_json, utc_now, utc_stamp


def observe_clock_heartbeat(
    *,
    runtime_root: Path,
    campaign_id: str,
    checkpoint_path: Path,
    partitions_root: Path,
    health: dict[str, Any] | None = None,
    capture_start_utc: str | None = None,
) -> dict[str, Any]:
    runtime_root = Path(runtime_root)
    health = health if health is not None else read_json(runtime_root / f"{campaign_id}_health.json")
    ck = read_json(Path(checkpoint_path))
    findings: list[dict[str, Any]] = []

    # Heartbeat proxy: health freshness + checkpoint growth.
    health_age: float | None = None
    checked = parse_iso_utc(health.get("checked_at") if health.get("status") == "OK" else None)
    if checked is not None:
        health_age = (utc_now() - checked).total_seconds()

    hb_status = "UNKNOWN"
    if health_age is None:
        hb_status = "UNKNOWN"
        findings.append(
            finding(
                code="HEARTBEAT_SIGNAL_MISSING",
                severity="MEDIUM",
                summary="No health checked_at — cannot score heartbeat proxy",
            )
        )
    elif health_age > HEARTBEAT_STALE_SECONDS:
        hb_status = "STALE"
        findings.append(
            finding(
                code="HEARTBEAT_PROXY_STALE",
                severity="HIGH",
                summary="Health sampler heartbeat proxy stale",
                evidence={"health_age_seconds": health_age, "threshold": HEARTBEAT_STALE_SECONDS},
            )
        )
    else:
        hb_status = "OK"

    # Clock quality: compare wall clock vs max partition hour and launch start.
    clock_status = "UNKNOWN"
    skew_ms: float | None = None
    start = parse_iso_utc(capture_start_utc)
    if start is not None:
        elapsed_s = (utc_now() - start).total_seconds()
        if elapsed_s < CLOCK_ROLLBACK_TOLERANCE_MS / 1000.0:
            # start in the future relative to now
            clock_status = "ROLLBACK_OR_FUTURE_START"
            findings.append(
                finding(
                    code="CLOCK_FUTURE_START",
                    severity="CRITICAL",
                    summary="capture_start_UTC is in the future relative to supervisor wall clock",
                    evidence={"capture_start_utc": capture_start_utc, "elapsed_seconds": elapsed_s},
                )
            )
        else:
            clock_status = "MONOTONIC_OK"

    # Detect hour-key vs wall-clock skew using newest partition mtime vs embedded hour.
    newest_mtime = None
    newest_hour = None
    root = Path(partitions_root)
    if root.is_dir():
        for gz in root.rglob("*.jsonl.gz"):
            m = gz.stat().st_mtime
            if newest_mtime is None or m > newest_mtime:
                newest_mtime = m
                name = gz.name.replace(".jsonl.gz", "")
                parts = name.split("_")
                if len(parts) >= 3:
                    newest_hour = f"{parts[-3]}_{parts[-2]}"

    if newest_hour and newest_mtime is not None:
        try:
            day, hh = newest_hour.split("_")
            hour_dt = datetime_from_hour(day, hh)
            wall = datetime_from_ts(newest_mtime)
            wall_hour = wall.strftime("%Y%m%d_%H")
            # Compare hour buckets — not hour-floor vs mtime (that always looks skewed mid-hour).
            hour_delta = int((wall.replace(minute=0, second=0, microsecond=0) - hour_dt).total_seconds() // 3600)
            skew_ms = abs(hour_delta) * 3_600_000.0
            if abs(hour_delta) >= 2:
                clock_status = "SKEW_CRITICAL"
                findings.append(
                    finding(
                        code="CLOCK_SKEW_CRITICAL",
                        severity="CRITICAL",
                        summary="Partition UTC hour bucket disagrees with file mtime by >=2 hours",
                        evidence={
                            "newest_hour": newest_hour,
                            "wall_hour": wall_hour,
                            "hour_delta": hour_delta,
                            "skew_ms": skew_ms,
                            "threshold_ms": CLOCK_SKEW_CRITICAL_MS,
                        },
                    )
                )
            elif abs(hour_delta) == 1:
                if clock_status == "MONOTONIC_OK":
                    clock_status = "SKEW_WARN"
                findings.append(
                    finding(
                        code="CLOCK_SKEW_WARN",
                        severity="HIGH",
                        summary="Partition UTC hour bucket off-by-one vs file mtime hour",
                        evidence={
                            "newest_hour": newest_hour,
                            "wall_hour": wall_hour,
                            "hour_delta": hour_delta,
                            "skew_ms": skew_ms,
                            "threshold_ms": CLOCK_SKEW_WARN_MS,
                        },
                    )
                )
            elif clock_status in {"UNKNOWN", "MONOTONIC_OK"}:
                clock_status = "OK"
        except ValueError:
            findings.append(
                finding(
                    code="CLOCK_HOUR_PARSE_FAIL",
                    severity="MEDIUM",
                    summary="Could not parse newest partition hour key",
                    evidence={"newest_hour": newest_hour},
                )
            )

    ck_trade = ck.get("trade_count") if ck.get("status") == "OK" else None

    return {
        "schema": "v14_a_clock_heartbeat",
        "observed_at": utc_stamp(),
        "campaign_id": campaign_id,
        "clock_status": clock_status,
        "heartbeat_status": hb_status,
        "health_age_seconds": health_age,
        "skew_ms": skew_ms,
        "newest_partition_hour": newest_hour,
        "checkpoint_trade_count": ck_trade,
        "registry_clock_quality": None,
        "thresholds": {
            "heartbeat_stale_seconds": HEARTBEAT_STALE_SECONDS,
            "clock_skew_warn_ms": CLOCK_SKEW_WARN_MS,
            "clock_skew_critical_ms": CLOCK_SKEW_CRITICAL_MS,
        },
        "findings": findings,
        "silent_fallback": False,
    }


def datetime_from_hour(day: str, hh: str):
    from datetime import datetime, timezone

    return datetime(int(day[0:4]), int(day[4:6]), int(day[6:8]), int(hh), tzinfo=timezone.utc)


def datetime_from_ts(ts: float):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc)
