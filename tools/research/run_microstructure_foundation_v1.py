#!/usr/bin/env python3
"""Microstructure Data Foundation V1 — bounded Bybit public capture smoke.

No strategies, backtests, WF/OOS/Demo. Raw partitions stay under .nexus_runtime/.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE = ROOT / "artifacts/readiness/immutable/microstructure_data_foundation_v1"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"

    from backend.nexus_microstructure import data_contracts
    from backend.nexus_microstructure.collector import run_bounded_capture
    from backend.nexus_microstructure.derived_bars import validate_derived_bars

    duration = float(os.getenv("NEXUS_MS_SMOKE_MINUTES", "15"))
    symbols = int(os.getenv("NEXUS_MS_SMOKE_SYMBOLS", "5"))
    print(f"microstructure smoke: {duration} min, {symbols} symbols", flush=True)
    summary = run_bounded_capture(
        root=ROOT,
        duration_minutes=duration,
        smoke_symbol_count=symbols,
    )
    trade_events = []
    # Use in-memory records via re-open not needed — writers closed; validate from partition reports only
    # Rebuild derived bars from writer records is unavailable after close; use empty-safe path from summary counts
    # Prefer reading closed gzip for validation sample
    from backend.nexus_microstructure.storage import PartitionWriter
    import gzip

    trade_path = Path(summary["trade_partition"]["path"])
    liq_path = Path(summary["liquidation_partition"]["path"])
    if trade_path.is_file():
        with gzip.open(trade_path, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    trade_events.append(json.loads(line))
    liq_events = []
    if liq_path.is_file():
        with gzip.open(liq_path, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    liq_events.append(json.loads(line))

    derived = validate_derived_bars(
        trade_events=trade_events,
        liq_events=liq_events,
        trade_checksum=str(summary["trade_partition"]["checksum"]),
        liq_checksum=str(summary["liquidation_partition"]["checksum"]),
    )

    integrity = {
        "schema": "microstructure_integrity_report",
        "duplicate_count": summary["duplicate_count"],
        "out_of_order_count": summary["out_of_order_count"],
        "parse_error_count": summary["parse_error_count"],
        "gap_suspected_count": summary["gap_suspected_count"],
        "reconnect_count": summary["reconnect_count"],
        "checksum_reproducible": bool(summary["trade_partition"].get("checksum_reproducible"))
        and bool(summary["liquidation_partition"].get("checksum_reproducible")),
        "heartbeat_ok": summary.get("heartbeat_ok"),
        "zero_liquidation_ok_if_quiet": True,
        "aggressive_trade_expected_on_active_symbols": summary["aggressive_trade_event_count"] > 0,
    }

    storage_estimate = {
        "schema": "storage_estimate",
        "events_per_second": summary["events_per_second"],
        "compressed_bytes_per_event": summary["compressed_bytes_per_event"],
        "estimated_daily_storage": summary["estimated_daily_storage"],
        "estimated_30_day_storage": summary["estimated_30_day_storage"],
        "estimated_365_day_storage": summary["estimated_365_day_storage"],
        "storage_bytes_written": summary["storage_bytes_written"],
        "storage_cap_bytes": summary["storage_cap_bytes"],
        "raw_partitions_committed": False,
    }

    recommendation = "NEXUS_MICROSTRUCTURE_FOUNDATION_READY_FOR_DATA_ACCUMULATION"
    if not summary["capture_session_started"] or not summary["capture_session_stopped_cleanly"]:
        recommendation = "NEXUS_MICROSTRUCTURE_CAPTURE_INTEGRITY_FAILED"
    elif summary.get("storage_cap_hit"):
        recommendation = "NEXUS_MICROSTRUCTURE_STORAGE_BUDGET_BLOCKED"
    elif summary["aggressive_trade_event_count"] == 0 and summary["parse_error_count"] == 0:
        # connection may be ok but no trades — treat as provider/source issue only if no heartbeat
        if not summary.get("heartbeat_ok"):
            recommendation = "NEXUS_MICROSTRUCTURE_PROVIDER_SOURCE_INVALID"
        else:
            recommendation = "NEXUS_MICROSTRUCTURE_CAPTURE_INTEGRITY_FAILED"
    elif not integrity["checksum_reproducible"]:
        recommendation = "NEXUS_MICROSTRUCTURE_IMPLEMENTATION_INVALID"

    status = {
        "schema": "microstructure_foundation_status",
        "created_at": _utc(),
        "recommendation": recommendation,
        "selected_data_families": summary["selected_data_families"],
        "exchange": summary["exchange"],
        "capture_mode": summary["capture_mode"],
        "smoke_duration_minutes": summary["smoke_duration_minutes"],
        "smoke_symbol_count": summary["smoke_symbol_count"],
        "aggressive_trade_event_count": summary["aggressive_trade_event_count"],
        "liquidation_event_count": summary["liquidation_event_count"],
        "new_strategy_generated_count": 0,
        "backtest_executed": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
        "MICROSTRUCTURE_EVENT_STUDY_V1_executed": False,
    }

    IMMUTABLE.mkdir(parents=True, exist_ok=True)
    _write(IMMUTABLE / "data_contracts.json", data_contracts())
    _write(
        IMMUTABLE / "capture_configuration.json",
        {
            "exchange": "BYBIT",
            "ws": summary["ws_endpoint"],
            "duration_minutes": duration,
            "smoke_symbol_count": symbols,
            "storage_root": ".nexus_runtime/microstructure/",
            "storage_cap_bytes": summary["storage_cap_bytes"],
            "symbols": summary["symbols"],
            "universe_snapshot": summary["universe_snapshot"],
        },
    )
    _write(IMMUTABLE / "capture_session_summary.json", summary)
    _write(IMMUTABLE / "integrity_report.json", integrity)
    _write(IMMUTABLE / "storage_estimate.json", storage_estimate)
    _write(IMMUTABLE / "derived_bar_validation.json", derived)
    _write(IMMUTABLE / "microstructure_foundation_status.json", status)
    print(json.dumps(status, indent=2), flush=True)
    return 0 if recommendation == "NEXUS_MICROSTRUCTURE_FOUNDATION_READY_FOR_DATA_ACCUMULATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
