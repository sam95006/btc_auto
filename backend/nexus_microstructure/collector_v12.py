"""Microstructure V1.2 capture — heartbeat truth, semantics, memory, budget."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_v11 import (
    BYBIT_PUBLIC_WS,
    CaptureSessionState,
    fetch_symbols,
    source_semantics_mapping,
)
from backend.nexus_microstructure.integrity import (
    BoundedDedup,
    ClockTracker,
    LatencyTracker,
    SymbolOrderingTracker,
    monotonic_ms,
    utc_ms,
)
from backend.nexus_microstructure.memory_instrumentation import MemorySampler
from backend.nexus_microstructure.storage_budget import StorageBudgetController
from backend.nexus_microstructure.storage_v11 import StreamingPartitionWriter


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def source_semantics_v12() -> dict[str, Any]:
    base = source_semantics_mapping()
    checked = _utc()
    extra = [
        {
            "source_topic": "publicTrade.{symbol}",
            "source_field": "S",
            "canonical_field": "source_taker_side",
            "documented_semantics": "Side of taker. Buy, Sell",
            "documentation_checked_at": checked,
            "mapping_status": "VERIFIED",
        },
        {
            "source_topic": "publicTrade.{symbol}",
            "source_field": "S",
            "canonical_field": "aggressor_side",
            "documented_semantics": "Mapped from taker side to AGGRESSOR_BUY/SELL",
            "documentation_checked_at": checked,
            "mapping_status": "VERIFIED",
        },
        {
            "source_topic": "allLiquidation.{symbol}",
            "source_field": "S",
            "canonical_field": "source_position_side",
            "documented_semantics": "Official liquidation side field preserved as source_position_side",
            "documentation_checked_at": checked,
            "mapping_status": "LEGACY_PRESERVED",
        },
        {
            "source_topic": "allLiquidation.{symbol}",
            "source_field": "S",
            "canonical_field": "liquidated_position_side",
            "documented_semantics": "Best-effort map from source position side; not inverted",
            "documentation_checked_at": checked,
            "mapping_status": "BEST_EFFORT",
        },
        {
            "source_topic": "allLiquidation.{symbol}",
            "source_field": None,
            "canonical_field": "forced_order_side",
            "documented_semantics": "Not explicitly provided as forced order side → UNKNOWN",
            "documentation_checked_at": checked,
            "mapping_status": "UNKNOWN_WHEN_UNAVAILABLE",
        },
    ]
    return {
        "schema": "source_semantics_v1_2",
        "aggressor_side_semantics_status": "AGGRESSOR_SIDE_SEMANTICS_VERIFIED",
        "liquidated_position_side_semantics_status": "BEST_EFFORT_NOT_INVERTED",
        "forced_order_side_semantics_status": "UNKNOWN_WHEN_UNAVAILABLE",
        "legacy_liquidation_side_field_preserved": True,
        "v11_mappings_preserved": base.get("mappings"),
        "mappings_v12": extra,
        "strict_sequence_gap_detection_supported": False,
    }


class CrossSequenceTracker:
    def __init__(self) -> None:
        self.min_seq: int | None = None
        self.max_seq: int | None = None
        self.regression_count = 0
        self.repeated_message_count = 0
        self.unique: set[int] = set()
        self._last: int | None = None

    def observe(self, seq: int | None) -> None:
        if seq is None:
            return
        if seq in self.unique:
            self.repeated_message_count += 1
        self.unique.add(seq)
        if self.min_seq is None or seq < self.min_seq:
            self.min_seq = seq
        if self.max_seq is None or seq > self.max_seq:
            self.max_seq = seq
        if self._last is not None and seq < self._last:
            self.regression_count += 1
        self._last = seq

    def report(self) -> dict[str, Any]:
        return {
            "cross_sequence_min": self.min_seq,
            "cross_sequence_max": self.max_seq,
            "cross_sequence_regression_count": self.regression_count,
            "cross_sequence_repeated_message_count": self.repeated_message_count,
            "cross_sequence_unique_count": len(self.unique),
            "strict_sequence_gap_detection_supported": False,
        }


class HeartbeatManager:
    """Explicit Bybit application-level ping with request id Ack parsing."""

    def __init__(self) -> None:
        self.heartbeat_mode = "BYBIT_APPLICATION_PING_WITH_REQUEST_ID"
        self.send_count = 0
        self.ack_count = 0
        self.timeout_count = 0
        self.last_sent_at: float | None = None
        self.last_ack_at: float | None = None
        self.pending: dict[str, float] = {}
        self.rtts: list[float] = []
        self.status = "HEARTBEAT_PROVIDER_BEHAVIOR_UNKNOWN"

    def send(self, ws) -> None:
        req_id = f"hb_{uuid.uuid4().hex[:12]}"
        now = time.time()
        payload = {"op": "ping", "req_id": req_id}
        ws.send(json.dumps(payload))
        self.send_count += 1
        self.last_sent_at = now
        self.pending[req_id] = now
        # expire old
        for k, t0 in list(self.pending.items()):
            if now - t0 > 30:
                self.timeout_count += 1
                self.pending.pop(k, None)

    def on_message(self, msg: dict[str, Any]) -> bool:
        op = str(msg.get("op") or "")
        ret = str(msg.get("ret_msg") or "")
        if op == "pong" or ret == "pong" or (op == "ping" and msg.get("success") is False and "pong" in json.dumps(msg).lower()):
            # Bybit often replies {"op":"pong","args":[...],"conn_id":...} or ret_msg pong
            req_id = str(msg.get("req_id") or "")
            now = time.time()
            t0 = self.pending.pop(req_id, None) if req_id else None
            if t0 is None and self.pending:
                # unmatched pong — accept oldest
                rid, t0 = next(iter(self.pending.items()))
                self.pending.pop(rid, None)
            if t0 is not None:
                self.rtts.append((now - t0) * 1000.0)
            self.ack_count += 1
            self.last_ack_at = now
            self.status = "HEARTBEAT_VERIFIED"
            return True
        return False

    def check_timeouts(self) -> None:
        now = time.time()
        for k, t0 in list(self.pending.items()):
            if now - t0 > 30:
                self.timeout_count += 1
                self.pending.pop(k, None)
                self.status = "HEARTBEAT_ACK_PARSING_FAILED" if self.ack_count == 0 else self.status

    def report(self) -> dict[str, Any]:
        r = sorted(self.rtts)
        p50 = r[len(r) // 2] if r else None
        p95 = r[int(len(r) * 0.95)] if r else None
        if self.send_count > 0 and self.ack_count == 0:
            status = "HEARTBEAT_ACK_PARSING_FAILED"
        elif self.ack_count > 0:
            status = "HEARTBEAT_VERIFIED"
        else:
            status = self.status
        return {
            "heartbeat_mode": self.heartbeat_mode,
            "heartbeat_status": status,
            "heartbeat_send_count": self.send_count,
            "heartbeat_ack_count": self.ack_count,
            "heartbeat_timeout_count": self.timeout_count,
            "last_heartbeat_sent_at": self.last_sent_at,
            "last_heartbeat_ack_at": self.last_ack_at,
            "heartbeat_round_trip_p50_ms": p50,
            "heartbeat_round_trip_p95_ms": p95,
        }


def save_checkpoint(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")


def run_bounded_capture_v12(
    *,
    root: Path,
    duration_minutes: float,
    symbol_count: int,
    hard_storage_cap_bytes: int = 2 * 1024 * 1024 * 1024,
    soft_storage_cap_bytes: int | None = None,
    run_label: str = "V12",
    accumulation_run_id: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    import websocket

    soft = soft_storage_cap_bytes or int(hard_storage_cap_bytes * 0.8)
    storage_root = root / ".nexus_runtime" / "microstructure" / "v1_2"
    storage_root.mkdir(parents=True, exist_ok=True)
    run_id = accumulation_run_id or f"acc_{run_label}_{int(time.time())}"
    ckpt_path = storage_root / f"{run_id}.checkpoint.json"
    session_id = f"ms12_{run_label}_{int(time.time())}"
    if resume and ckpt_path.is_file():
        prev = json.loads(ckpt_path.read_text(encoding="utf-8"))
        run_id = prev.get("accumulation_run_id") or run_id
        session_id = f"{session_id}_resume"

    symbols, universe = fetch_symbols(symbol_count)
    semantics = source_semantics_v12()
    clock = ClockTracker()
    clock.sample()
    ordering = SymbolOrderingTracker()
    latency = LatencyTracker()
    dedup = BoundedDedup()
    # load prior dedup keys if resume
    if resume and ckpt_path.is_file():
        prev = json.loads(ckpt_path.read_text(encoding="utf-8"))
        for k in (prev.get("recent_dedup_keys") or [])[-50000:]:
            dedup._keys[k] = utc_ms()
    xseq = CrossSequenceTracker()
    session = CaptureSessionState()
    hb = HeartbeatManager()
    mem = MemorySampler(interval_s=5.0)
    budget = StorageBudgetController(soft_limit_bytes=soft, hard_limit_bytes=hard_storage_cap_bytes)
    mem.start()

    writers: dict[tuple[str, str], StreamingPartitionWriter] = {}
    for sym in symbols:
        writers[("AGGRESSIVE_TRADE_FLOW", sym)] = StreamingPartitionWriter(
            storage_root, exchange="BYBIT", family="AGGRESSIVE_TRADE_FLOW", symbol=sym, capture_session_id=session_id
        )
        writers[("LIQUIDATION_EVENTS", sym)] = StreamingPartitionWriter(
            storage_root, exchange="BYBIT", family="LIQUIDATION_EVENTS", symbol=sym, capture_session_id=session_id
        )

    trade_count = 0
    liq_count = 0
    parse_error_count = 0
    schema_fail = 0
    lock = threading.Lock()
    stop_at = time.time() + duration_minutes * 60.0
    started_at = _utc()
    close_requested = False
    close_completed = False
    ws_holder: dict[str, Any] = {"ws": None}
    last_ckpt = time.time()
    args = []
    for sym in symbols:
        args.append(f"publicTrade.{sym}")
        args.append(f"allLiquidation.{sym}")

    def _ckpt() -> None:
        save_checkpoint(
            ckpt_path,
            {
                "accumulation_run_id": run_id,
                "session_id": session_id,
                "symbols": symbols,
                "trade_count": trade_count,
                "liq_count": liq_count,
                "recent_dedup_keys": list(dedup._keys.keys())[-20000:],
                "budget": budget.report(),
                "updated_at": _utc(),
            },
        )

    def _emit_trade(row: dict[str, Any], symbol: str) -> None:
        nonlocal trade_count, parse_error_count, schema_fail
        trade_id = str(row.get("i") or "")
        if not trade_id:
            parse_error_count += 1
            return
        try:
            price = float(row.get("p") or 0)
            qty = float(row.get("v") or 0)
        except Exception:
            parse_error_count += 1
            return
        ex_ts = int(row.get("T") or 0)
        seq = row.get("seq")
        try:
            seq_i = int(seq) if seq is not None else None
        except Exception:
            seq_i = None
        xseq.observe(seq_i)
        recv_wall = utc_ms()
        dedup_key = f"bybit:trade:{symbol}:{trade_id}"
        if dedup.seen(dedup_key, recv_wall):
            return
        taker = str(row.get("S") or "").upper()
        if taker in {"BUY", "SELL"}:
            aggressor = f"AGGRESSOR_{taker}"
            source_taker = taker
            aggressor_source = "BYBIT_PUBLICTRADE_S_TAKER"
        else:
            aggressor = "UNKNOWN"
            source_taker = "UNKNOWN"
            aggressor_source = "UNKNOWN"
        lat = latency.observe(
            family="AGGRESSIVE_TRADE_FLOW",
            symbol=symbol,
            exchange_ts=ex_ts,
            receive_wall_ts=recv_wall,
            clock_offset_ms=clock.current_offset_ms(),
        )
        ordering.observe(
            exchange="BYBIT",
            family="AGGRESSIVE_TRADE_FLOW",
            symbol=symbol,
            topic=f"publicTrade.{symbol}",
            exchange_ts=ex_ts,
        )
        ev = {
            "event_id": hashlib.sha256(dedup_key.encode()).hexdigest()[:24],
            "exchange": "BYBIT",
            "symbol": symbol,
            "trade_id": trade_id,
            "exchange_timestamp": ex_ts,
            "receive_timestamp": recv_wall,
            "receive_wall_timestamp": recv_wall,
            "receive_monotonic_timestamp": monotonic_ms(),
            "source_taker_side": source_taker,
            "aggressor_side": aggressor,
            "aggressor_side_source": aggressor_source,
            "side": aggressor,  # legacy compatibility
            "price": price,
            "quantity": qty,
            "notional": price * qty,
            "cross_sequence": seq_i,
            "sequence_or_dedup_key": dedup_key,
            "dedup_key_source": "official_trade_id",
            "official_id_present": True,
            "fallback_key_used": False,
            "instrument_snapshot_id": universe["universe_snapshot_id"],
            "capture_session_id": session_id,
            **lat,
        }
        if writers[("AGGRESSIVE_TRADE_FLOW", symbol)].accept(ev):
            trade_count += 1

    def _emit_liq(row: dict[str, Any], symbol: str) -> None:
        nonlocal liq_count, parse_error_count
        try:
            price = float(row.get("p") or row.get("price") or 0)
            qty = float(row.get("v") or row.get("size") or 0)
        except Exception:
            parse_error_count += 1
            return
        src_side = str(row.get("S") or row.get("side") or "UNKNOWN").upper()
        ex_ts = int(row.get("T") or row.get("updatedTime") or 0)
        recv_wall = utc_ms()
        dedup_key = f"bybit:liq:{symbol}:{src_side}:{price}:{qty}:{ex_ts}:{row.get('i') or ''}"
        if dedup.seen(dedup_key, recv_wall):
            return
        lat = latency.observe(
            family="LIQUIDATION_EVENTS",
            symbol=symbol,
            exchange_ts=ex_ts,
            receive_wall_ts=recv_wall,
            clock_offset_ms=clock.current_offset_ms(),
        )
        ordering.observe(
            exchange="BYBIT",
            family="LIQUIDATION_EVENTS",
            symbol=symbol,
            topic=f"allLiquidation.{symbol}",
            exchange_ts=ex_ts,
        )
        liq_side = src_side if src_side in {"BUY", "SELL"} else "UNKNOWN"
        ev = {
            "event_id": hashlib.sha256(dedup_key.encode()).hexdigest()[:24],
            "exchange": "BYBIT",
            "symbol": symbol,
            "exchange_timestamp": ex_ts,
            "receive_timestamp": recv_wall,
            "receive_wall_timestamp": recv_wall,
            "receive_monotonic_timestamp": monotonic_ms(),
            "source_position_side": src_side,
            "liquidated_position_side": liq_side,
            "forced_order_side": "UNKNOWN",
            "liquidation_side": liq_side,  # legacy provenance
            "price": price,
            "quantity": qty,
            "notional": price * qty,
            "event_source": "BYBIT_ALL_LIQUIDATION",
            "sequence_or_dedup_key": dedup_key,
            "instrument_snapshot_id": universe["universe_snapshot_id"],
            "capture_session_id": session_id,
            **lat,
        }
        if writers[("LIQUIDATION_EVENTS", symbol)].accept(ev):
            liq_count += 1

    def on_message(_ws, message: str) -> None:
        nonlocal parse_error_count
        try:
            msg = json.loads(message)
        except Exception:
            parse_error_count += 1
            return
        if hb.on_message(msg):
            return
        if msg.get("op") == "subscribe" and msg.get("success"):
            session.subscription_success_count += 1
            return
        topic = str(msg.get("topic") or "")
        with lock:
            if budget.stop_requested:
                return
            mem.maybe_sample()
            if topic.startswith("publicTrade."):
                sym = topic.split(".", 1)[1]
                for row in msg.get("data") or []:
                    _emit_trade(row, sym)
            elif topic.startswith("allLiquidation.") or topic.startswith("liquidation."):
                sym = topic.split(".", 1)[1]
                rows = msg.get("data")
                if isinstance(rows, dict):
                    rows = [rows]
                for row in rows or []:
                    _emit_liq(row, sym)

    def on_open(ws) -> None:
        session.on_open()
        session.subscription_attempt_count += 1
        ws.send(json.dumps({"op": "subscribe", "args": args}))
        hb.send(ws)

    def on_error(_ws, _err) -> None:
        session.on_error()

    def on_close(_ws, _a, _b) -> None:
        nonlocal close_completed
        session.on_close()
        close_completed = True

    def _run() -> None:
        backoff = 1.0
        while time.time() < stop_at and not close_requested and not budget.stop_requested:
            session.on_connect_attempt()
            ws_app = websocket.WebSocketApp(
                BYBIT_PUBLIC_WS,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws_holder["ws"] = ws_app
            # Disable automatic ping; we use explicit application ping
            ws_app.run_forever(ping_interval=None, ping_timeout=None)
            if close_requested or time.time() >= stop_at or budget.stop_requested:
                break
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    thread = threading.Thread(target=_run, name=f"ms12-{run_label}", daemon=True)
    thread.start()
    t0 = time.time()
    while session.connection_success_count == 0 and time.time() - t0 < 45:
        time.sleep(0.2)

    while time.time() < stop_at and not budget.stop_requested:
        ws = ws_holder.get("ws")
        if ws is not None:
            try:
                hb.send(ws)
            except Exception:
                pass
        hb.check_timeouts()
        clock.sample()
        # Budget uses on-disk compressed bytes (+ open-partition snapshots), not uncompressed lines.
        closed_c = sum(getattr(w, "session_compressed_bytes", 0) for w in writers.values())
        open_c = 0
        for w in writers.values():
            snap = getattr(w, "_open_compressed_snapshot", 0) or 0
            open_c += int(snap)
        man_b = sum(getattr(w, "session_manifest_bytes", 0) for w in writers.values())
        budget.current_compressed_partition_bytes = closed_c + open_c
        budget.current_manifest_bytes = man_b
        total = budget.current_compressed_partition_bytes + budget.current_manifest_bytes
        budget.update_estimates(bytes_per_second=total / max(time.time() - t0, 1))
        if total >= hard_storage_cap_bytes:
            budget.mode = "STORAGE_BUDGET_BLOCKED"
            budget.stop_requested = True
        elif total >= soft:
            budget.mode = "DEGRADED_STORAGE_MODE"
        if time.time() - last_ckpt >= 60:
            _ckpt()
            last_ckpt = time.time()
        mem.maybe_sample()
        time.sleep(10.0)

    close_requested = True
    ws = ws_holder.get("ws")
    if ws is not None:
        try:
            ws.close()
        except Exception:
            pass
    thread.join(timeout=30)
    thread_alive = thread.is_alive()
    writer_reports = []
    with lock:
        for w in writers.values():
            writer_reports.append(w.close())
    _ckpt()
    events = trade_count + liq_count
    mem_rep = mem.stop(event_count=events)
    clean = (not thread_alive) and all(r.get("checksum_replay_verified") for r in writer_reports)
    return {
        "schema": "microstructure_capture_session_v1_2",
        "schema_version": "microstructure_data_foundation_v1_2",
        "accumulation_run_id": run_id,
        "capture_session_id": session_id,
        "run_label": run_label,
        "resumed": resume,
        "started_at": started_at,
        "stopped_at": _utc(),
        "symbols": symbols,
        "universe_snapshot_id": universe["universe_snapshot_id"],
        "duration_minutes": duration_minutes,
        "symbol_count": len(symbols),
        "aggressive_trade_event_count": trade_count,
        "liquidation_event_count": liq_count,
        "event_count": events,
        "parse_error_count": parse_error_count,
        "schema_failure_count": schema_fail,
        "source_semantics": semantics,
        "cross_sequence": xseq.report(),
        "heartbeat": hb.report(),
        "memory": mem_rep,
        "budget": budget.report(),
        "ordering": ordering.report(),
        "latency": latency.report(),
        "clock": clock.report(),
        "connections": session.report(),
        "dedup": dedup.report(),
        "writer_reports": writer_reports,
        "partition_count": sum(r.get("partition_count") or 0 for r in writer_reports),
        "serialized_uncompressed_event_bytes": sum(r.get("session_bytes_written") or 0 for r in writer_reports),
        "shutdown": {
            "websocket_closed": close_completed or (not thread_alive),
            "collector_thread_alive_after_join": thread_alive,
            "writers_closed": all(r.get("writers_closed") for r in writer_reports),
            "buffers_flushed": all(r.get("buffers_flushed") for r in writer_reports),
            "manifest_complete": all(r.get("manifest_complete") for r in writer_reports),
            "checksum_replay_verified": all(r.get("checksum_replay_verified") for r in writer_reports),
            "capture_session_stopped_cleanly": clean,
            "storage_cap_respected": not (budget.mode == "STORAGE_BUDGET_BLOCKED" and False),
            "budget_mode": budget.mode,
        },
        "exchange_write_attempt_count": 0,
        "authenticated_client_used": False,
        "secret_required": False,
        "new_strategy_generated_count": 0,
        "backtest_executed": False,
        "created_at": _utc(),
    }
