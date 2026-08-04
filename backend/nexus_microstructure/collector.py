"""Bybit public-readonly WS collector for aggressive trades + liquidations."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.storage import PartitionWriter, utc_ms

BYBIT_PUBLIC_WS = "wss://stream.bybit.com/v5/public/linear"
BYBIT_TICKERS = "https://api.bybit.com/v5/market/tickers?category=linear"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_smoke_symbols(limit: int = 5) -> tuple[list[str], dict[str, Any]]:
    """Deterministic high-liquidity linear USDT perps; smoke cohort only."""
    with urllib.request.urlopen(BYBIT_TICKERS, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rows = payload.get("result", {}).get("list") or []
    candidates: list[tuple[float, str]] = []
    for row in rows:
        sym = str(row.get("symbol") or "")
        if not sym.endswith("USDT"):
            continue
        if any(x in sym for x in ("-", "_")):
            continue
        try:
            turnover = float(row.get("turnover24h") or 0)
        except Exception:
            turnover = 0.0
        candidates.append((turnover, sym))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    symbols = [s for _, s in candidates[:limit]]
    snap = {
        "universe_snapshot_id": hashlib.sha256(
            json.dumps([s for _, s in candidates[:200]], separators=(",", ":")).encode()
        ).hexdigest()[:16],
        "smoke_cohort_label": "CAPTURE_SMOKE_COHORT_NOT_PRODUCTION_UNIVERSE",
        "smoke_symbol_count": len(symbols),
        "production_ready_subscription_plan_min_symbols": 25,
        "symbols": symbols,
        "selection_basis": "deterministic_top_turnover24h_linear_usdt",
        "future_strategy_performance_not_used": True,
        "fetched_at": _utc(),
    }
    return symbols, snap


def _trade_events(msg: dict[str, Any], *, session_id: str, instrument_snapshot_id: str) -> list[dict[str, Any]]:
    # Bybit publicTrade push: topic publicTrade.SYMBOL, data list
    topic = str(msg.get("topic") or "")
    if not topic.startswith("publicTrade."):
        return []
    symbol = topic.split(".", 1)[1]
    out: list[dict[str, Any]] = []
    for row in msg.get("data") or []:
        trade_id = str(row.get("i") or row.get("execId") or "")
        side = str(row.get("S") or row.get("side") or "UNKNOWN").upper()
        # Bybit publicTrade S is aggressor side when present
        aggressor_source = "BYBIT_PUBLICTRADE_S" if row.get("S") else "UNKNOWN"
        aggressor = side if row.get("S") else "UNKNOWN"
        try:
            price = float(row.get("p") or 0)
            qty = float(row.get("v") or 0)
        except Exception:
            continue
        ex_ts = int(row.get("T") or 0)
        dedup = f"bybit:{symbol}:{trade_id}:{ex_ts}"
        out.append(
            {
                "event_id": hashlib.sha256(dedup.encode()).hexdigest()[:24],
                "exchange": "BYBIT",
                "symbol": symbol,
                "trade_id": trade_id or "UNKNOWN",
                "exchange_timestamp": ex_ts,
                "receive_timestamp": utc_ms(),
                "side": aggressor,
                "price": price,
                "quantity": qty,
                "notional": price * qty,
                "aggressor_side_source": aggressor_source if aggressor != "UNKNOWN" else "UNKNOWN",
                "sequence_or_dedup_key": dedup,
                "instrument_snapshot_id": instrument_snapshot_id,
                "capture_session_id": session_id,
            }
        )
    return out


def _liq_events(msg: dict[str, Any], *, session_id: str, instrument_snapshot_id: str) -> list[dict[str, Any]]:
    topic = str(msg.get("topic") or "")
    if not (topic.startswith("allLiquidation.") or topic.startswith("liquidation.")):
        return []
    symbol = topic.split(".", 1)[1]
    rows = msg.get("data")
    if isinstance(rows, dict):
        rows = [rows]
    out: list[dict[str, Any]] = []
    for row in rows or []:
        try:
            price = float(row.get("p") or row.get("price") or 0)
            qty = float(row.get("v") or row.get("size") or 0)
        except Exception:
            continue
        side = str(row.get("S") or row.get("side") or "UNKNOWN").upper()
        ex_ts = int(row.get("T") or row.get("updatedTime") or 0)
        dedup = f"bybit-liq:{symbol}:{side}:{price}:{qty}:{ex_ts}"
        out.append(
            {
                "event_id": hashlib.sha256(dedup.encode()).hexdigest()[:24],
                "exchange": "BYBIT",
                "symbol": symbol,
                "exchange_timestamp": ex_ts,
                "receive_timestamp": utc_ms(),
                "liquidation_side": side if side in {"BUY", "SELL"} else "UNKNOWN",
                "price": price,
                "quantity": qty,
                "notional": price * qty,
                "event_source": "BYBIT_ALL_LIQUIDATION" if topic.startswith("allLiquidation.") else "BYBIT_LIQUIDATION",
                "sequence_or_dedup_key": dedup,
                "instrument_snapshot_id": instrument_snapshot_id,
                "capture_session_id": session_id,
            }
        )
    return out


def run_bounded_capture(
    *,
    root: Path,
    duration_minutes: float = 15.0,
    smoke_symbol_count: int = 5,
    storage_cap_bytes: int = 5 * 1024 * 1024 * 1024,
) -> dict[str, Any]:
    import websocket  # websocket-client

    storage_root = root / ".nexus_runtime" / "microstructure"
    storage_root.mkdir(parents=True, exist_ok=True)
    session_id = f"ms_{int(time.time())}"
    symbols, universe = fetch_smoke_symbols(smoke_symbol_count)
    instrument_snapshot_id = universe["universe_snapshot_id"]
    trade_writer = PartitionWriter(
        storage_root, family="AGGRESSIVE_TRADE_FLOW", capture_session_id=session_id, storage_cap_bytes=storage_cap_bytes
    )
    liq_writer = PartitionWriter(
        storage_root, family="LIQUIDATION_EVENTS", capture_session_id=session_id, storage_cap_bytes=storage_cap_bytes
    )

    args = []
    for sym in symbols:
        args.append(f"publicTrade.{sym}")
        args.append(f"allLiquidation.{sym}")

    stop_at = time.time() + duration_minutes * 60.0
    started = False
    stopped_cleanly = False
    heartbeat_ok = False
    last_msg_at = time.time()
    lock = threading.Lock()
    state = {"exchange_write_attempt_count": 0, "secret_required": False}

    def on_message(_ws, message: str) -> None:
        nonlocal heartbeat_ok, last_msg_at
        last_msg_at = time.time()
        try:
            msg = json.loads(message)
        except Exception:
            with lock:
                trade_writer.parse_error_count += 1
            return
        if msg.get("op") == "ping" or msg.get("ret_msg") == "pong" or msg.get("op") == "pong":
            heartbeat_ok = True
            return
        if "success" in msg and msg.get("op") == "subscribe":
            heartbeat_ok = True
            return
        trades = _trade_events(msg, session_id=session_id, instrument_snapshot_id=instrument_snapshot_id)
        if trades:
            with lock:
                for ev in trades:
                    trade_writer.accept(ev)
            return
        for ev in _liq_events(msg, session_id=session_id, instrument_snapshot_id=instrument_snapshot_id):
            with lock:
                liq_writer.accept(ev)

    def on_open(ws) -> None:
        nonlocal started
        started = True
        ws.send(json.dumps({"op": "subscribe", "args": args}))

    def on_error(_ws, _err) -> None:
        with lock:
            trade_writer.reconnect_count += 1
            liq_writer.reconnect_count += 1

    def on_close(_ws, _a, _b) -> None:
        return

    ws_app = websocket.WebSocketApp(
        BYBIT_PUBLIC_WS,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    def _run() -> None:
        backoff = 1.0
        while time.time() < stop_at and not trade_writer.cap_hit and not liq_writer.cap_hit:
            ws_app.run_forever(ping_interval=20, ping_timeout=10)
            if time.time() >= stop_at:
                break
            with lock:
                trade_writer.reconnect_count += 1
                liq_writer.reconnect_count += 1
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    # Wait until start or timeout
    t0 = time.time()
    while not started and time.time() - t0 < 30:
        time.sleep(0.2)
    while time.time() < stop_at:
        if trade_writer.cap_hit or liq_writer.cap_hit:
            break
        # soft heartbeat via recent messages
        if time.time() - last_msg_at < 60:
            heartbeat_ok = True
        time.sleep(1.0)
    try:
        ws_app.close()
    except Exception:
        pass
    thread.join(timeout=10)
    stopped_cleanly = True

    trade_report = trade_writer.close()
    liq_report = liq_writer.close()
    duration_s = max(duration_minutes * 60.0, 1.0)
    trade_n = int(trade_report["record_count"])
    liq_n = int(liq_report["record_count"])
    bytes_written = int(trade_report.get("bytes_on_disk") or 0) + int(liq_report.get("bytes_on_disk") or 0)
    events_total = max(trade_n + liq_n, 1)
    compressed_bytes_per_event = bytes_written / events_total
    events_per_second = (trade_n + liq_n) / duration_s
    estimated_daily = compressed_bytes_per_event * events_per_second * 86400
    return {
        "schema": "microstructure_capture_session_summary",
        "capture_session_id": session_id,
        "capture_session_started": started,
        "capture_session_stopped_cleanly": stopped_cleanly,
        "exchange": "BYBIT",
        "capture_mode": "PUBLIC_READONLY_WEBSOCKET",
        "ws_endpoint": BYBIT_PUBLIC_WS,
        "selected_data_families": ["AGGRESSIVE_TRADE_FLOW", "LIQUIDATION_EVENTS"],
        "smoke_duration_minutes": duration_minutes,
        "smoke_symbol_count": len(symbols),
        "symbols": symbols,
        "universe_snapshot": universe,
        "heartbeat_ok": heartbeat_ok,
        "aggressive_trade_event_count": trade_n,
        "liquidation_event_count": liq_n,
        "duplicate_count": trade_report["duplicate_count"] + liq_report["duplicate_count"],
        "out_of_order_count": trade_report["out_of_order_count"] + liq_report["out_of_order_count"],
        "parse_error_count": trade_report["parse_error_count"] + liq_report["parse_error_count"],
        "gap_suspected_count": trade_report["gap_suspected_count"] + liq_report["gap_suspected_count"],
        "reconnect_count": trade_report["reconnect_count"] + liq_report["reconnect_count"],
        "trade_partition": trade_report,
        "liquidation_partition": liq_report,
        "storage_bytes_written": bytes_written,
        "storage_cap_bytes": storage_cap_bytes,
        "storage_cap_hit": trade_writer.cap_hit or liq_writer.cap_hit,
        "events_per_second": events_per_second,
        "compressed_bytes_per_event": compressed_bytes_per_event,
        "estimated_daily_storage": estimated_daily,
        "estimated_30_day_storage": estimated_daily * 30,
        "estimated_365_day_storage": estimated_daily * 365,
        "exchange_write_attempt_count": state["exchange_write_attempt_count"],
        "secret_required": state["secret_required"],
        "authenticated_client_used": False,
        "new_strategy_generated_count": 0,
        "backtest_executed": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
        "created_at": _utc(),
    }
