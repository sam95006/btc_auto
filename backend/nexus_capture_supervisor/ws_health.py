"""WebSocket / connection-gap health inferred from read-only campaign surfaces."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import (
    CHECKPOINT_STALE_SECONDS,
    WS_GAP_CRITICAL_SECONDS,
    WS_GAP_WARN_SECONDS,
)
from backend.nexus_capture_supervisor.util import finding, parse_iso_utc, read_json, utc_now, utc_stamp


def observe_ws_health(
    *,
    runtime_root: Path,
    campaign_id: str,
    checkpoint_path: Path,
    health: dict[str, Any] | None = None,
    process_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer WS health without attaching to the live socket.

    Signals (explicit, no silent invent):
    - health integrity_status / data growth
    - checkpoint mtime freshness + trade_count
    - process liveness coupling
    """
    runtime_root = Path(runtime_root)
    health = health if health is not None else read_json(runtime_root / f"{campaign_id}_health.json")
    ck = read_json(Path(checkpoint_path))
    findings: list[dict[str, Any]] = []

    integrity = health.get("integrity_status") if health.get("status") == "OK" else None
    data_bytes = int(health.get("data_bytes") or 0) if health.get("status") == "OK" else 0
    data_files = int(health.get("data_file_count") or 0) if health.get("status") == "OK" else 0

    ck_mtime_age: float | None = None
    if Path(checkpoint_path).is_file():
        ck_mtime_age = utc_now().timestamp() - Path(checkpoint_path).stat().st_mtime

    trade_count = int(ck.get("trade_count") or 0) if ck.get("status") == "OK" else None
    liq_count = int(ck.get("liq_count") or 0) if ck.get("status") == "OK" else None

    gap_proxy_s: float | None = None
    if ck_mtime_age is not None:
        gap_proxy_s = float(ck_mtime_age)

    ws_status = "UNKNOWN"
    if process_report and process_report.get("status") == "DOWN":
        ws_status = "DOWN"
        findings.append(
            finding(
                code="WS_IMPLIED_DOWN_PROCESS",
                severity="CRITICAL",
                summary="WS treated DOWN because capture process is not alive",
                evidence={"process_status": process_report.get("status")},
            )
        )
    elif integrity == "LIVE_WRITING" and data_bytes > 0:
        if gap_proxy_s is not None and gap_proxy_s > WS_GAP_CRITICAL_SECONDS:
            ws_status = "GAP_CRITICAL"
            findings.append(
                finding(
                    code="WS_CHECKPOINT_STALE_CRITICAL",
                    severity="CRITICAL",
                    summary="Checkpoint mtime implies extended connection gap",
                    evidence={
                        "checkpoint_age_seconds": gap_proxy_s,
                        "threshold_seconds": WS_GAP_CRITICAL_SECONDS,
                    },
                    recommendation="Coordinator: inspect WS thread; recommend graceful restart if gap persists",
                )
            )
        elif gap_proxy_s is not None and gap_proxy_s > WS_GAP_WARN_SECONDS:
            ws_status = "GAP_WARN"
            findings.append(
                finding(
                    code="WS_CHECKPOINT_STALE_WARN",
                    severity="HIGH",
                    summary="Checkpoint mtime exceeds warn threshold",
                    evidence={
                        "checkpoint_age_seconds": gap_proxy_s,
                        "threshold_seconds": WS_GAP_WARN_SECONDS,
                    },
                )
            )
        elif ck_mtime_age is not None and ck_mtime_age > CHECKPOINT_STALE_SECONDS:
            ws_status = "DEGRADED"
            findings.append(
                finding(
                    code="WS_CHECKPOINT_SOFT_STALE",
                    severity="MEDIUM",
                    summary="Checkpoint older than soft stale threshold while health claims LIVE_WRITING",
                    evidence={"checkpoint_age_seconds": ck_mtime_age},
                )
            )
        else:
            ws_status = "HEALTHY"
    elif health.get("status") == "OK" and integrity and integrity != "LIVE_WRITING":
        ws_status = "DEGRADED"
        findings.append(
            finding(
                code="WS_INTEGRITY_NOT_LIVE_WRITING",
                severity="HIGH",
                summary=f"Health integrity_status={integrity}",
                evidence={"integrity_status": integrity},
            )
        )
    else:
        ws_status = "UNKNOWN"
        findings.append(
            finding(
                code="WS_SIGNAL_INSUFFICIENT",
                severity="MEDIUM",
                summary="Insufficient read-only signals to classify WS health",
                evidence={
                    "health_status": health.get("status"),
                    "checkpoint_status": ck.get("status"),
                },
            )
        )

    return {
        "schema": "v14_a_ws_health",
        "observed_at": utc_stamp(),
        "campaign_id": campaign_id,
        "status": ws_status,
        "integrity_status": integrity,
        "data_bytes": data_bytes,
        "data_file_count": data_files,
        "checkpoint_status": ck.get("status"),
        "checkpoint_age_seconds": ck_mtime_age,
        "gap_proxy_seconds": gap_proxy_s,
        "trade_count": trade_count,
        "liq_count": liq_count,
        "thresholds": {
            "ws_gap_warn_seconds": WS_GAP_WARN_SECONDS,
            "ws_gap_critical_seconds": WS_GAP_CRITICAL_SECONDS,
            "checkpoint_stale_seconds": CHECKPOINT_STALE_SECONDS,
        },
        "findings": findings,
        "note": "Read-only inference; supervisor does not attach to Bybit WS",
        "exchange_write_attempt_count": 0,
    }
