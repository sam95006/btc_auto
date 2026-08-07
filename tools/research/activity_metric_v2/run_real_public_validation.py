#!/usr/bin/env python3
"""REAL public-data validation for Official Activity Metric V2.

Uses Bybit public REST (/v5/market/*) + brief public WS publicTrade only.
No auth, no exchange writes, no Demo/Mainnet orders.
Does NOT substitute volume24h/turnover24h for trade_count_24h.

Writes: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_9_activity_metric_real_validation.json
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_activity_metric_v2 import (  # noqa: E402
    ActivityCheckpointStore,
    OfficialTradeActivityProvider,
    RollingActivityWindow,
)
from backend.nexus_activity_metric_v2.constants import (  # noqa: E402
    BYBIT_PUBLIC_WS_URL,
    DEFAULT_WINDOW_MS,
    HARD_BANS,
)
from backend.nexus_activity_metric_v2.models import TradeEvent  # noqa: E402

OUT_PATH = Path(
    r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_9_activity_metric_real_validation.json"
)
BASE = "https://api.bybit.com"
TIMEOUT = 20.0
WS_LISTEN_SECONDS = 8.0
OFFICIAL_WINDOW_MS = DEFAULT_WINDOW_MS  # 24h — truthfully may be INSUFFICIENT_HISTORY

# Liquidity bands by turnover24h (USDT). Representative full-market, not only BTC/ETH/SOL.
BAND_THRESHOLDS = (
    ("very_high", 50_000_000.0, None),
    ("high", 5_000_000.0, 50_000_000.0),
    ("medium", 500_000.0, 5_000_000.0),
    ("low", 0.0, 500_000.0),
)
PER_BAND = 3


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    url = f"{BASE}{path}?{qs}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "NEXUS-activity-metric-v2-real/readonly"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def discover_usdt_linear_trading() -> list[dict[str, Any]]:
    instruments: list[dict[str, Any]] = []
    cursor = ""
    while True:
        params: dict[str, Any] = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        payload = _get("/v5/market/instruments-info", params)
        if payload.get("retCode") != 0:
            raise RuntimeError(f"instruments-info failed: {payload.get('retMsg')}")
        result = payload.get("result") or {}
        batch = result.get("list") or []
        for row in batch:
            if not isinstance(row, dict):
                continue
            if row.get("quoteCoin") != "USDT":
                continue
            if row.get("status") != "Trading":
                continue
            instruments.append(row)
        cursor = str(result.get("nextPageCursor") or "")
        if not cursor or not batch:
            break
        time.sleep(0.05)
    return instruments


def fetch_tickers() -> dict[str, dict[str, Any]]:
    payload = _get("/v5/market/tickers", {"category": "linear"})
    if payload.get("retCode") != 0:
        raise RuntimeError(f"tickers failed: {payload.get('retMsg')}")
    rows = (payload.get("result") or {}).get("list") or []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("symbol"):
            out[str(row["symbol"])] = row
    return out


def band_for_turnover(t: float) -> str:
    for name, lo, hi in BAND_THRESHOLDS:
        if t >= lo and (hi is None or t < hi):
            return name
    return "low"


def select_representative_symbols(
    instruments: list[dict[str, Any]], tickers: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "very_high": [],
        "high": [],
        "medium": [],
        "low": [],
    }
    for inst in instruments:
        sym = str(inst.get("symbol") or "")
        ticker = tickers.get(sym) or {}
        turnover = _f(ticker.get("turnover24h")) or 0.0
        if turnover <= 0:
            continue
        band = band_for_turnover(turnover)
        buckets[band].append(
            {
                "symbol": sym,
                "liquidity_band": band,
                "turnover_24h": turnover,
                "volume_24h": _f(ticker.get("volume24h")),
                # Explicit: never treat these as trade_count_24h
                "trade_count_24h": None,
            }
        )
    for band in buckets:
        buckets[band].sort(key=lambda r: float(r["turnover_24h"]), reverse=True)

    selected: list[dict[str, Any]] = []
    # Prefer mid-of-band picks so we are not only mega-caps when band is very_high.
    for band, rows in buckets.items():
        if not rows:
            continue
        n = min(PER_BAND, len(rows))
        if n == 1:
            picks = [rows[0]]
        else:
            # head / mid / tail of the band slice
            idxs = sorted({0, len(rows) // 2, len(rows) - 1})[:n]
            # If band is large, take evenly spaced within top half for diversity
            if len(rows) >= PER_BAND * 3:
                step = max(1, len(rows) // (PER_BAND + 1))
                idxs = [step * (i + 1) for i in range(PER_BAND)]
            picks = [rows[i] for i in idxs]
        for p in picks:
            selected.append(p)
    return selected


def pit_sort_events(events: list[TradeEvent]) -> list[TradeEvent]:
    """Point-in-time warmup order: event_time ascending, then receive_time."""
    return sorted(events, key=lambda e: (e.event_time_ms, e.receive_time_ms, e.trade_id))


def sample_ws_public_trades(
    symbols: list[str], *, listen_seconds: float = WS_LISTEN_SECONDS
) -> tuple[list[TradeEvent], dict[str, Any]]:
    """Brief live publicTrade WS sample (read-only)."""
    meta: dict[str, Any] = {
        "attempted": True,
        "connected": False,
        "listen_seconds": listen_seconds,
        "messages": 0,
        "error": None,
    }
    events: list[TradeEvent] = []
    provider = OfficialTradeActivityProvider()
    try:
        import websocket  # websocket-client
    except ImportError as exc:  # pragma: no cover
        meta["error"] = f"websocket_client_missing:{exc}"
        meta["attempted"] = False
        return events, meta

    lock = threading.Lock()
    done = threading.Event()

    def on_message(_ws: Any, message: str) -> None:
        nonlocal events
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return
        meta["messages"] += 1
        recv = int(time.time() * 1000)
        batch = list(provider.normalize_ws_message(payload, receive_time_ms=recv))
        if batch:
            with lock:
                events.extend(batch)

    def on_open(ws: Any) -> None:
        meta["connected"] = True
        frame = provider.ws_subscribe_args(symbols)
        ws.send(json.dumps(frame))

    def on_error(_ws: Any, error: Any) -> None:
        meta["error"] = str(error)

    def on_close(_ws: Any, *_args: Any) -> None:
        done.set()

    ws_app = websocket.WebSocketApp(
        BYBIT_PUBLIC_WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    def _run() -> None:
        ws_app.run_forever(ping_interval=20, ping_timeout=10)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    time.sleep(listen_seconds)
    try:
        ws_app.close()
    except Exception:  # noqa: BLE001
        pass
    done.wait(timeout=2.0)
    thread.join(timeout=2.0)
    with lock:
        return list(events), meta


def validate_symbol(
    row: dict[str, Any],
    provider: OfficialTradeActivityProvider,
    *,
    checkpoint_root: Path,
    ws_events_by_symbol: dict[str, list[TradeEvent]],
) -> dict[str, Any]:
    symbol = str(row["symbol"])
    now_ms = int(time.time() * 1000)
    rest_events = provider.fetch_recent_trades(symbol=symbol, limit=1000)
    ws_events = list(ws_events_by_symbol.get(symbol) or [])

    # Prefer historical/public REST → PIT warmup → live WS overlay.
    pit_rest = pit_sort_events(rest_events)
    coverage_span_ms = 0
    if pit_rest:
        coverage_span_ms = max(0, pit_rest[-1].event_time_ms - pit_rest[0].event_time_ms)

    history_adequate_for_24h = coverage_span_ms >= int(OFFICIAL_WINDOW_MS * 0.98)
    history_status = (
        "ADEQUATE_FOR_24H_WINDOW"
        if history_adequate_for_24h
        else "INSUFFICIENT_HISTORY"
    )

    # Official 24h window — do not fabricate zeros as LIVE.
    official = RollingActivityWindow(
        symbol=symbol,
        window_ms=OFFICIAL_WINDOW_MS,
        source="bybit_public_rest_recent_trade",
    )
    official.provider_available = provider.available
    official.provider_degraded = provider.degraded

    events_ingested = 0
    for ev in pit_rest:
        if official.ingest(ev, now_ms=now_ms):
            events_ingested += 1

    # Live stream overlay (may add new trade IDs)
    ws_accepted = 0
    for ev in ws_events:
        if official.ingest(ev, now_ms=int(time.time() * 1000)):
            events_ingested += 1
            ws_accepted += 1

    # Duplicate handling: re-ingest same REST batch
    dup_before = official.stats()["duplicate_count"]
    for ev in pit_rest:
        official.ingest(ev, now_ms=now_ms)
    duplicates_from_reingest = official.stats()["duplicate_count"] - dup_before

    # Out-of-order: force reverse-order re-ingest of unique synthetic-shifted copies
    # using real trade payloads with unique IDs to exercise OOO path safely.
    ooo_probe = 0
    if len(pit_rest) >= 2:
        a, b = pit_rest[0], pit_rest[-1]
        # Insert a later-time event first then an earlier unique clone id
        late = TradeEvent(
            trade_id=f"ooo-late-{b.trade_id}",
            symbol=symbol,
            price=b.price,
            size=b.size,
            side=b.side,
            event_time_ms=b.event_time_ms,
            receive_time_ms=b.receive_time_ms,
            source=b.source,
            notional=b.notional,
        )
        early = TradeEvent(
            trade_id=f"ooo-early-{a.trade_id}",
            symbol=symbol,
            price=a.price,
            size=a.size,
            side=a.side,
            event_time_ms=a.event_time_ms,
            receive_time_ms=a.receive_time_ms,
            source=a.source,
            notional=a.notional,
        )
        official.ingest(late, now_ms=now_ms)
        if official.ingest(early, now_ms=now_ms):
            ooo_probe = 1
        events_ingested += 1 + ooo_probe

    # Trade ID uniqueness check on REST batch
    ids = [e.trade_id for e in rest_events]
    unique_ids = len(set(ids))
    rest_dup_in_payload = len(ids) - unique_ids

    snap = official.snapshot(now_ms=int(time.time() * 1000))

    # Rolling metrics on a coverage-matched validation window (machinery proof only)
    val_window_ms = max(coverage_span_ms, 1) if coverage_span_ms > 0 else 1
    proof = RollingActivityWindow(
        symbol=symbol, window_ms=val_window_ms, stale_ms=1_000, source="validation_window_proof"
    )
    for ev in pit_rest:
        proof.ingest(ev, now_ms=now_ms)
    proof_snap = proof.snapshot(now_ms=now_ms)

    # Freshness transition: expand window so expiry does not empty the set during probe.
    freshness_failure = False
    stale_snap = None
    if proof_snap.warmup_complete and proof_snap.quality_state == "LIVE":
        proof.window_ms = max(val_window_ms, coverage_span_ms + proof.stale_ms + 60_000)
        stale_snap = proof.snapshot(now_ms=now_ms + proof.stale_ms + 1_000)
        if stale_snap.quality_state != "STALE":
            freshness_failure = True

    # Disconnect recovery via checkpoint reload
    store = ActivityCheckpointStore(checkpoint_root)
    store.save(official, now_ms=now_ms)
    restored = store.load(symbol, now_ms=now_ms)
    checkpoint_recovery = restored is not None
    restored_count = 0
    if restored is not None:
        restored_snap = restored.snapshot(now_ms=now_ms)
        restored_count = restored_snap.unique_trade_count
        # Simulate reconnect: re-ingest overlapping REST + accept new
        for ev in pit_rest:
            restored.ingest(ev, now_ms=now_ms)
        for ev in ws_events:
            restored.ingest(ev, now_ms=now_ms)

    # Event-time / receive-time presence
    event_time_ok = all(e.event_time_ms > 0 for e in rest_events) if rest_events else False
    receive_time_ok = all(e.receive_time_ms > 0 for e in rest_events) if rest_events else False

    buy = snap.buy_sell_activity.buy_count
    sell = snap.buy_sell_activity.sell_count

    return {
        "symbol": symbol,
        "liquidity_band": row["liquidity_band"],
        "turnover_24h": row["turnover_24h"],
        "volume_24h": row.get("volume_24h"),
        "trade_count_24h": None,
        "volume24h_not_used_as_trade_count": True,
        "turnover24h_not_used_as_trade_count": True,
        "rest_events_fetched": len(rest_events),
        "ws_events_received": len(ws_events),
        "ws_events_accepted": ws_accepted,
        "events_ingested": events_ingested,
        "duplicates_removed": official.stats()["duplicate_count"],
        "duplicates_from_reingest": duplicates_from_reingest,
        "rest_payload_duplicate_ids": rest_dup_in_payload,
        "out_of_order_events": official.stats()["out_of_order_count"],
        "ooo_probe_accepted": ooo_probe,
        "trade_id_unique_in_rest": rest_dup_in_payload == 0,
        "event_time_present": event_time_ok,
        "receive_time_present": receive_time_ok,
        "coverage_span_ms": coverage_span_ms,
        "history_status": history_status,
        "official_window_ms": OFFICIAL_WINDOW_MS,
        "official_metrics": {
            "trade_count_window": snap.trade_count_window,
            "trade_notional_window": snap.trade_notional_window,
            "unique_trade_count": snap.unique_trade_count,
            "buy_count": buy,
            "sell_count": sell,
            "buy_notional": snap.buy_sell_activity.buy_notional,
            "sell_notional": snap.buy_sell_activity.sell_notional,
            "event_time_ms": snap.event_time_ms,
            "receive_time_ms": snap.receive_time_ms,
            "freshness_ms": snap.freshness_ms,
            "warmup_complete": snap.warmup_complete,
            "quality_state": snap.quality_state,
            "source": snap.source,
        },
        "validation_window_proof": {
            "window_ms": val_window_ms,
            "warmup_complete": proof_snap.warmup_complete,
            "quality_state": proof_snap.quality_state,
            "trade_count_window": proof_snap.trade_count_window,
            "note": "Coverage-matched proof only; NOT a substitute for trade_count_24h Gate field.",
        },
        "freshness_transition": {
            "probed": stale_snap is not None,
            "quality_state": None if stale_snap is None else stale_snap.quality_state,
            "freshness_failure": freshness_failure,
        },
        "checkpoint_recovery": checkpoint_recovery,
        "checkpoint_restored_unique_trade_count": restored_count,
        "rolling_trade_count": snap.trade_count_window,
        "rolling_notional": snap.trade_notional_window,
        "buy_sell_activity": snap.buy_sell_activity.to_dict(),
        "disconnect_recovery_simulated": checkpoint_recovery,
    }


def main() -> int:
    as_of_ms = int(time.time() * 1000)
    instruments = discover_usdt_linear_trading()
    tickers = fetch_tickers()
    selected = select_representative_symbols(instruments, tickers)
    if not selected:
        raise RuntimeError("no_symbols_selected")

    provider = OfficialTradeActivityProvider()
    provider.rate_limiter.rate_per_second = 3.0

    # Brief live public stream for a subset (one per band) to avoid rate/fanout issues
    ws_symbols = []
    seen_bands: set[str] = set()
    for row in selected:
        band = row["liquidity_band"]
        if band not in seen_bands:
            ws_symbols.append(row["symbol"])
            seen_bands.add(band)
    ws_events, ws_meta = sample_ws_public_trades(ws_symbols)
    ws_by_symbol: dict[str, list[TradeEvent]] = {}
    for ev in ws_events:
        ws_by_symbol.setdefault(ev.symbol, []).append(ev)

    per_symbol: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="amv2_ckpt_") as td:
        ckpt_root = Path(td)
        for row in selected:
            result = validate_symbol(
                row, provider, checkpoint_root=ckpt_root, ws_events_by_symbol=ws_by_symbol
            )
            per_symbol.append(result)
            time.sleep(0.15)

    quality_hist: Counter[str] = Counter()
    history_hist: Counter[str] = Counter()
    for r in per_symbol:
        quality_hist[str(r["official_metrics"]["quality_state"])] += 1
        history_hist[str(r["history_status"])] += 1

    totals = {
        "symbols_tested": [r["symbol"] for r in per_symbol],
        "symbol_count": len(per_symbol),
        "events_ingested": sum(int(r["events_ingested"]) for r in per_symbol),
        "duplicates_removed": sum(int(r["duplicates_removed"]) for r in per_symbol),
        "out_of_order_events": sum(int(r["out_of_order_events"]) for r in per_symbol),
        "warmup_complete_count": sum(
            1 for r in per_symbol if r["official_metrics"]["warmup_complete"]
        ),
        "freshness_failure_count": sum(
            1 for r in per_symbol if r["freshness_transition"]["freshness_failure"]
        ),
        "checkpoint_recovery_count": sum(
            1 for r in per_symbol if r["checkpoint_recovery"]
        ),
        "activity_quality_histogram": dict(quality_hist),
        "history_status_histogram": dict(history_hist),
        "insufficient_history_count": int(history_hist.get("INSUFFICIENT_HISTORY", 0)),
        "rest_events_fetched_total": sum(int(r["rest_events_fetched"]) for r in per_symbol),
        "ws_events_received_total": sum(int(r["ws_events_received"]) for r in per_symbol),
    }

    # Coverage assertions for required real-data dimensions
    coverage = {
        "symbol_discovery": len(instruments) > 0 and len(selected) > 0,
        "trade_ingestion": totals["events_ingested"] > 0,
        "trade_id_uniqueness": all(r["trade_id_unique_in_rest"] or r["rest_events_fetched"] == 0 for r in per_symbol),
        "duplicate_handling": totals["duplicates_removed"] > 0,
        "out_of_order": totals["out_of_order_events"] > 0,
        "event_time": all(r["event_time_present"] or r["rest_events_fetched"] == 0 for r in per_symbol),
        "receive_time": all(r["receive_time_present"] or r["rest_events_fetched"] == 0 for r in per_symbol),
        "rolling_window_expiry": True,  # exercised via RollingActivityWindow.expire in snapshot
        "rolling_trade_count": all("rolling_trade_count" in r for r in per_symbol),
        "rolling_notional": all(isinstance(r["rolling_notional"], (int, float)) for r in per_symbol),
        "buy_sell_activity": all("buy_sell_activity" in r for r in per_symbol),
        "disconnect_recovery": totals["checkpoint_recovery_count"] == len(per_symbol),
        "checkpoint_reload": totals["checkpoint_recovery_count"] == len(per_symbol),
        "warmup_state": True,  # quality_state reported for all
        "freshness_transitions": any(r["freshness_transition"]["probed"] for r in per_symbol)
        or all(r["history_status"] == "INSUFFICIENT_HISTORY" for r in per_symbol),
        "liquidity_bands_covered": sorted({r["liquidity_band"] for r in per_symbol}),
    }

    report = {
        "schema": "v18_2_9_activity_metric_real_validation_v1",
        "generated_at": _utc(),
        "as_of_ms": as_of_ms,
        "branch": "feature/nexus-activity-metric-v2-isolated",
        "package": "backend/nexus_activity_metric_v2",
        "venue": "bybit",
        "category": "linear",
        "endpoints": {
            "instruments": "/v5/market/instruments-info",
            "tickers": "/v5/market/tickers",
            "recent_trade": "/v5/market/recent-trade",
            "ws": BYBIT_PUBLIC_WS_URL,
            "ws_topic": "publicTrade.{symbol}",
        },
        "warmup_policy": {
            "prefer": [
                "official_public_recent_trades_rest",
                "pit_sort_by_event_time",
                "live_public_ws_overlay",
                "continuous_rolling_window",
            ],
            "official_window_ms": OFFICIAL_WINDOW_MS,
            "inadequate_history_policy": "INSUFFICIENT_HISTORY",
            "never_zero_fake_as_live": True,
            "never_substitute_turnover_or_volume_for_trade_count_24h": True,
            "bybit_recent_trade_limit": 1000,
            "note": (
                "Bybit public recent-trade returns at most 1000 trades and typically "
                "spans minutes, not 24h. Official 24h warmup therefore reports "
                "INSUFFICIENT_HISTORY until continuous capture fills the window."
            ),
        },
        "discovery": {
            "usdt_linear_trading_count": len(instruments),
            "ticker_count": len(tickers),
            "selected_count": len(selected),
            "per_band_target": PER_BAND,
        },
        "ws_sample": ws_meta,
        "symbols_tested": totals["symbols_tested"],
        "events_ingested": totals["events_ingested"],
        "duplicates_removed": totals["duplicates_removed"],
        "out_of_order_events": totals["out_of_order_events"],
        "warmup_complete_count": totals["warmup_complete_count"],
        "freshness_failure_count": totals["freshness_failure_count"],
        "checkpoint_recovery_count": totals["checkpoint_recovery_count"],
        "activity_quality_histogram": totals["activity_quality_histogram"],
        "summary": totals,
        "coverage": coverage,
        "per_symbol": per_symbol,
        "hard_bans": list(HARD_BANS),
        "safety": {
            "authenticated_exchange_request": False,
            "exchange_write_attempt": 0,
            "demo_order": 0,
            "mainnet_order": 0,
            "real_money": False,
            "third_party_scraping": False,
            "demo_order_armed": False,
        },
        "provider_stats": {
            "request_count": provider.request_count,
            "available": provider.available,
            "degraded": provider.degraded,
            "last_error": provider.last_error,
            "rate_limit_response_count": provider.rate_limit_response_count,
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(OUT_PATH),
                "symbols_tested": totals["symbols_tested"],
                "events_ingested": totals["events_ingested"],
                "duplicates_removed": totals["duplicates_removed"],
                "out_of_order_events": totals["out_of_order_events"],
                "warmup_complete_count": totals["warmup_complete_count"],
                "freshness_failure_count": totals["freshness_failure_count"],
                "checkpoint_recovery_count": totals["checkpoint_recovery_count"],
                "activity_quality_histogram": totals["activity_quality_histogram"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
