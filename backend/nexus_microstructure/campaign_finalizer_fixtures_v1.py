"""Helpers to build synthetic microstructure partition fixtures for finalizer tests."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha_lines(lines: list[bytes]) -> str:
    h = hashlib.sha256()
    for line in lines:
        h.update(line)
    return h.hexdigest()


def write_partition(
    root: Path,
    *,
    exchange: str,
    family: str,
    symbol: str,
    utc_hour: str,
    partition_index: int,
    session_id: str,
    events: list[dict[str, Any]],
    previous_partition_id: str | None = None,
    truncate: bool = False,
    corrupt_checksum: bool = False,
) -> dict[str, Any]:
    """Write a gzip jsonl partition + manifest under root/exchange/family/symbol/."""
    d = root / exchange / family / symbol
    d.mkdir(parents=True, exist_ok=True)
    pid = f"{session_id}_{family}_{symbol}_{utc_hour}_{partition_index}"
    gz_path = d / f"{pid}.jsonl.gz"
    lines = [
        (json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8") for ev in events
    ]
    checksum = _sha_lines(lines)
    with gzip.open(gz_path, "wb") as fh:
        for line in lines:
            fh.write(line)
    if truncate:
        # Remove gzip footer / tail bytes to simulate truncated member.
        raw = gz_path.read_bytes()
        gz_path.write_bytes(raw[: max(10, len(raw) // 2)])
    first_ex = events[0].get("exchange_timestamp") if events else None
    last_ex = events[-1].get("exchange_timestamp") if events else None
    first_rx = events[0].get("receive_timestamp") if events else None
    last_rx = events[-1].get("receive_timestamp") if events else None
    rolling = ("deadbeef" * 8) if corrupt_checksum else checksum
    man = {
        "partition_id": pid,
        "exchange": exchange,
        "family": family,
        "symbol": symbol,
        "UTC_hour": utc_hour,
        "schema_version": "microstructure_data_foundation_v1_1",
        "record_count": len(events),
        "first_exchange_timestamp": first_ex,
        "last_exchange_timestamp": last_ex,
        "first_receive_timestamp": first_rx,
        "last_receive_timestamp": last_rx,
        "uncompressed_bytes": sum(len(x) for x in lines),
        "compressed_bytes": gz_path.stat().st_size,
        "rolling_checksum": rolling,
        "previous_partition_id": previous_partition_id,
        "capture_session_id": session_id,
        "path": str(gz_path),
    }
    man_path = d / f"{pid}.manifest.json"
    man_path.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    return man


def hour_base_ms(utc_hour: str) -> int:
    """Convert YYYYMMDD_HH to epoch ms at hour start (UTC)."""
    from datetime import datetime, timezone

    dt = datetime.strptime(utc_hour, "%Y%m%d_%H").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def make_trade_events(
    *,
    symbol: str,
    session_id: str,
    utc_hour: str,
    count: int,
    span_minutes: float = 59.5,
) -> list[dict[str, Any]]:
    base = hour_base_ms(utc_hour)
    span_ms = int(span_minutes * 60 * 1000)
    out = []
    for i in range(count):
        ts = base + (span_ms * i // max(1, count - 1) if count > 1 else 0)
        out.append(
            {
                "event_id": f"{symbol}-t-{utc_hour}-{i}",
                "exchange": "BYBIT",
                "symbol": symbol,
                "trade_id": f"t{i}",
                "exchange_timestamp": ts,
                "receive_timestamp": ts + 3,
                "side": "Buy",
                "price": 100.0 + i * 0.01,
                "quantity": 0.01,
                "notional": 1.0,
                "aggressor_side_source": "official",
                "sequence_or_dedup_key": f"{symbol}:{i}",
                "instrument_snapshot_id": "snap1",
                "capture_session_id": session_id,
            }
        )
    return out


def make_liq_events(
    *,
    symbol: str,
    session_id: str,
    utc_hour: str,
    count: int,
    span_minutes: float = 30.0,
) -> list[dict[str, Any]]:
    base = hour_base_ms(utc_hour)
    span_ms = int(span_minutes * 60 * 1000)
    out = []
    for i in range(count):
        ts = base + (span_ms * i // max(1, count - 1) if count > 1 else 0)
        out.append(
            {
                "event_id": f"{symbol}-l-{utc_hour}-{i}",
                "exchange": "BYBIT",
                "symbol": symbol,
                "exchange_timestamp": ts,
                "receive_timestamp": ts + 5,
                "liquidation_side": "Sell",
                "price": 99.0,
                "quantity": 0.1,
                "notional": 9.9,
                "event_source": "allLiquidation",
                "sequence_or_dedup_key": f"{symbol}:liq:{i}",
                "instrument_snapshot_id": "snap1",
                "capture_session_id": session_id,
            }
        )
    return out


def build_clean_campaign_fixture(dest: Path) -> Path:
    """Two symbols, linked partitions, complete hour + partial hour, clean quality."""
    dest = Path(dest)
    parts = dest / "partitions"
    session = "syn_sess_clean_001"
    # Hour A: complete span
    m0 = write_partition(
        parts,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        utc_hour="20260801_10",
        partition_index=0,
        session_id=session,
        events=make_trade_events(symbol="BTCUSDT", session_id=session, utc_hour="20260801_10", count=40),
        previous_partition_id=None,
    )
    m1 = write_partition(
        parts,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        utc_hour="20260801_11",
        partition_index=1,
        session_id=session,
        events=make_trade_events(
            symbol="BTCUSDT",
            session_id=session,
            utc_hour="20260801_11",
            count=20,
            span_minutes=20.0,  # partial hour
        ),
        previous_partition_id=m0["partition_id"],
    )
    write_partition(
        parts,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="ETHUSDT",
        utc_hour="20260801_10",
        partition_index=0,
        session_id=session,
        events=make_trade_events(symbol="ETHUSDT", session_id=session, utc_hour="20260801_10", count=30),
        previous_partition_id=None,
    )
    write_partition(
        parts,
        exchange="BYBIT",
        family="LIQUIDATION_EVENTS",
        symbol="BTCUSDT",
        utc_hour="20260801_10",
        partition_index=0,
        session_id=session,
        events=make_liq_events(symbol="BTCUSDT", session_id=session, utc_hour="20260801_10", count=8),
        previous_partition_id=None,
    )
    meta = {
        "campaign_id": "ms_syn_finalizer_clean_v1",
        "accumulation_run_id": "accum_syn_clean",
        "valid_capture_seconds": 4200,
        "connection_gap_seconds": 120,
        "wall_elapsed_seconds": 4500,
        "calendar_days": 0.2,
        "complete_UTC_day_coverage": False,
        "Founder_authorization": False,
        "symbol_coverage": ["BTCUSDT", "ETHUSDT"],
        "trade_event_count": 90,
        "liquidation_event_count": 8,
        "config": {
            "soft_storage_cap_bytes": 805306368,
            "hard_storage_cap_bytes": 1073741824,
            "duration_hours": 24,
            "symbol_count": 25,
        },
        "clock": {
            "server_clock_sample_count": 12,
            "local_minus_server_clock_offset_ms_p95": 18.5,
        },
        "heartbeat": {
            "heartbeat_status": "HEARTBEAT_VERIFIED",
            "heartbeat_send_count": 40,
            "heartbeat_ack_count": 40,
            "heartbeat_timeout_count": 0,
        },
        "memory": {
            "memory_growth_status": "STABLE",
            "process_RSS_peak_bytes": 120_000_000,
            "RSS_growth_per_million_events": 0.0,
        },
        "budget": {"status": "NORMAL"},
        "gap_events": [{"at": "2026-08-01T10:30:00Z", "gap_seconds": 120, "reason": "ws_reconnect"}],
        "resume": {
            "resumable": True,
            "last_checkpoint_at": "2026-08-01T11:05:00Z",
            "last_partition_id": m1["partition_id"],
            "checkpoint_path": "synthetic://checkpoint.json",
            "accumulation_run_id": "accum_syn_clean",
            "capture_session_ids": [session],
            "resume_token": "syn-resume-clean",
            "clean_shutdown": True,
        },
        "session_ids": [session],
    }
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "campaign_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return dest


def build_degraded_campaign_fixture(dest: Path) -> Path:
    """Includes truncated tail, checksum mismatch, and linkage break."""
    dest = Path(dest)
    parts = dest / "partitions"
    session = "syn_sess_degraded_001"
    m0 = write_partition(
        parts,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        utc_hour="20260802_08",
        partition_index=0,
        session_id=session,
        events=make_trade_events(symbol="BTCUSDT", session_id=session, utc_hour="20260802_08", count=15, span_minutes=40),
        previous_partition_id=None,
    )
    write_partition(
        parts,
        exchange="BYBIT",
        family="AGGRESSIVE_TRADE_FLOW",
        symbol="BTCUSDT",
        utc_hour="20260802_09",
        partition_index=1,
        session_id=session,
        events=make_trade_events(symbol="BTCUSDT", session_id=session, utc_hour="20260802_09", count=10, span_minutes=15),
        previous_partition_id="WRONG_PREV_ID",  # linkage break
        truncate=True,
    )
    write_partition(
        parts,
        exchange="BYBIT",
        family="LIQUIDATION_EVENTS",
        symbol="BTCUSDT",
        utc_hour="20260802_08",
        partition_index=0,
        session_id=session,
        events=make_liq_events(symbol="BTCUSDT", session_id=session, utc_hour="20260802_08", count=3),
        previous_partition_id=None,
        corrupt_checksum=True,
    )
    meta = {
        "campaign_id": "ms_syn_finalizer_degraded_v1",
        "valid_capture_seconds": 900,
        "connection_gap_seconds": 600,
        "wall_elapsed_seconds": 2000,
        "calendar_days": 0.05,
        "complete_UTC_day_coverage": False,
        "Founder_authorization": False,
        "symbol_coverage": ["BTCUSDT"],
        "config": {
            "soft_storage_cap_bytes": 1000,
            "hard_storage_cap_bytes": 5000,
        },
        "clock": {
            "server_clock_sample_count": 2,
            "local_minus_server_clock_offset_ms_p95": 400.0,
        },
        "heartbeat": {
            "heartbeat_status": "HEARTBEAT_ACK_PARSING_FAILED",
            "heartbeat_send_count": 5,
            "heartbeat_ack_count": 0,
            "heartbeat_timeout_count": 3,
        },
        "memory": {
            "memory_growth_status": "LINEAR_GROWTH_DETECTED",
            "process_RSS_peak_bytes": 900_000_000,
        },
        "budget": {"status": "STORAGE_BUDGET_BLOCKED"},
        "resume": {
            "resumable": True,
            "last_partition_id": m0["partition_id"],
            "clean_shutdown": False,
            "capture_session_ids": [session],
        },
    }
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "campaign_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return dest
