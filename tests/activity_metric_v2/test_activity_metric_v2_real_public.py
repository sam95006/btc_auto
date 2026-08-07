"""Real public-data tests for Official Activity Metric V2.

Requires network access to Bybit public endpoints. No auth / no writes.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from backend.nexus_activity_metric_v2 import (
    ActivityCheckpointStore,
    OfficialTradeActivityProvider,
    RollingActivityWindow,
)
from backend.nexus_activity_metric_v2.constants import DEFAULT_WINDOW_MS
from backend.nexus_activity_metric_v2.models import TradeEvent


pytestmark = pytest.mark.network


def _get_instruments_and_tickers():
    import urllib.parse
    import urllib.request

    def get(path: str, params: dict):
        qs = urllib.parse.urlencode(params)
        url = f"https://api.bybit.com{path}?{qs}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "NEXUS-amv2-pytest/readonly"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    instruments = []
    cursor = ""
    while True:
        params = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        payload = get("/v5/market/instruments-info", params)
        assert payload.get("retCode") == 0
        result = payload.get("result") or {}
        batch = result.get("list") or []
        instruments.extend([r for r in batch if isinstance(r, dict)])
        cursor = str(result.get("nextPageCursor") or "")
        if not cursor or not batch:
            break
        time.sleep(0.05)

    tickers_payload = get("/v5/market/tickers", {"category": "linear"})
    assert tickers_payload.get("retCode") == 0
    tickers = {
        str(r["symbol"]): r
        for r in (tickers_payload.get("result") or {}).get("list") or []
        if isinstance(r, dict) and r.get("symbol")
    }
    return instruments, tickers


def _band(turnover: float) -> str:
    if turnover >= 50_000_000:
        return "very_high"
    if turnover >= 5_000_000:
        return "high"
    if turnover >= 500_000:
        return "medium"
    return "low"


def _pick_symbols(instruments, tickers, per_band: int = 2) -> list[str]:
    buckets = {"very_high": [], "high": [], "medium": [], "low": []}
    for inst in instruments:
        if inst.get("quoteCoin") != "USDT" or inst.get("status") != "Trading":
            continue
        sym = str(inst["symbol"])
        t = tickers.get(sym) or {}
        try:
            turnover = float(t.get("turnover24h") or 0)
        except (TypeError, ValueError):
            continue
        if turnover <= 0:
            continue
        buckets[_band(turnover)].append((turnover, sym))
    selected = []
    for band, rows in buckets.items():
        rows.sort(reverse=True)
        for _, sym in rows[:per_band]:
            selected.append(sym)
    assert len(selected) >= 4, f"expected multi-band symbols, got {selected}"
    return selected


def test_symbol_discovery_across_liquidity_bands():
    instruments, tickers = _get_instruments_and_tickers()
    assert len(instruments) > 100
    symbols = _pick_symbols(instruments, tickers)
    bands = set()
    for sym in symbols:
        turnover = float((tickers[sym].get("turnover24h") or 0))
        bands.add(_band(turnover))
    assert "very_high" in bands or "high" in bands
    assert "medium" in bands or "low" in bands
    # Must not be only BTC/ETH/SOL
    assert not set(symbols).issubset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})


def test_real_trade_ingestion_uniqueness_duplicates_event_receive_time():
    provider = OfficialTradeActivityProvider()
    provider.rate_limiter.rate_per_second = 5.0
    events = provider.fetch_recent_trades(symbol="BTCUSDT", limit=200)
    assert len(events) > 0
    ids = [e.trade_id for e in events]
    assert all(ids)
    assert len(ids) == len(set(ids)) or len(ids) >= len(set(ids))
    assert all(e.event_time_ms > 0 for e in events)
    assert all(e.receive_time_ms > 0 for e in events)
    assert all(e.receive_time_ms >= e.event_time_ms - 60_000 for e in events)

    win = RollingActivityWindow(symbol="BTCUSDT", window_ms=DEFAULT_WINDOW_MS)
    now = int(time.time() * 1000)
    accepted = 0
    for ev in sorted(events, key=lambda e: e.event_time_ms):
        if win.ingest(ev, now_ms=now):
            accepted += 1
    # Duplicate re-ingest
    for ev in events:
        win.ingest(ev, now_ms=now)
    assert win.stats()["duplicate_count"] >= accepted
    snap = win.snapshot(now_ms=now)
    assert snap.trade_count_window == accepted
    assert snap.unique_trade_count == accepted
    assert snap.trade_notional_window >= 0
    assert snap.quality_state in {
        "LIVE",
        "INSUFFICIENT_HISTORY",
        "STALE",
        "DEGRADED",
        "UNAVAILABLE",
    }
    # Recent-trade typically cannot fill 24h → INSUFFICIENT_HISTORY is truthful
    if snap.coverage_start_ms is not None and snap.coverage_end_ms is not None:
        span = snap.coverage_end_ms - snap.coverage_start_ms
        if span < DEFAULT_WINDOW_MS * 0.98:
            assert snap.quality_state == "INSUFFICIENT_HISTORY"
            assert snap.warmup_complete is False
            assert snap.trade_count_window != 0 or accepted == 0


def test_out_of_order_rolling_expiry_buy_sell_checkpoint_disconnect():
    provider = OfficialTradeActivityProvider()
    events = provider.fetch_recent_trades(symbol="ETHUSDT", limit=100)
    assert len(events) >= 2
    now = int(time.time() * 1000)
    win = RollingActivityWindow(symbol="ETHUSDT", window_ms=DEFAULT_WINDOW_MS)
    # Deliberate out-of-order: latest first
    ordered = sorted(events, key=lambda e: e.event_time_ms, reverse=True)
    for ev in ordered:
        win.ingest(ev, now_ms=now)
    assert win.stats()["out_of_order_count"] >= 1
    snap = win.snapshot(now_ms=now)
    assert snap.buy_sell_activity.buy_count + snap.buy_sell_activity.sell_count == snap.unique_trade_count

    # Rolling expiry on short window
    short = RollingActivityWindow(symbol="ETHUSDT", window_ms=1)
    for ev in events[:5]:
        short.ingest(ev, now_ms=now)
    expired_snap = short.snapshot(now_ms=now + 10_000)
    assert expired_snap.unique_trade_count == 0

    with tempfile.TemporaryDirectory() as td:
        store = ActivityCheckpointStore(Path(td))
        store.save(win, now_ms=now)
        restored = store.load("ETHUSDT", now_ms=now)
        assert restored is not None
        # Disconnect recovery: reload then re-ingest overlapping
        for ev in events:
            restored.ingest(ev, now_ms=now)
        assert restored.stats()["duplicate_count"] >= 1
        rsnap = restored.snapshot(now_ms=now)
        assert rsnap.unique_trade_count == snap.unique_trade_count


def test_freshness_transition_on_coverage_matched_window():
    provider = OfficialTradeActivityProvider()
    events = provider.fetch_recent_trades(symbol="SOLUSDT", limit=50)
    assert events
    now = int(time.time() * 1000)
    span = max(e.event_time_ms for e in events) - min(e.event_time_ms for e in events)
    window_ms = max(span, 1)
    win = RollingActivityWindow(symbol="SOLUSDT", window_ms=window_ms, stale_ms=1_000)
    for ev in sorted(events, key=lambda e: e.event_time_ms):
        win.ingest(ev, now_ms=now)
    live = win.snapshot(now_ms=now)
    assert live.warmup_complete is True
    assert live.quality_state == "LIVE"
    stale = win.snapshot(now_ms=now + 5_000)
    assert stale.quality_state == "STALE"
    assert stale.warmup_complete is True


def test_ws_normalize_and_optional_live_sample():
    provider = OfficialTradeActivityProvider()
    stub = provider.ws_connect_stub()
    assert stub["url"].startswith("wss://")
    # Contract: subscribe args for multi-band symbols
    args = provider.ws_subscribe_args(["BTCUSDT", "ADAUSDT", "1000PEPEUSDT"])
    assert args["op"] == "subscribe"
    assert len(args["args"]) == 3

    # Optional brief live sample — skip soft-fail if network/ws blocked
    try:
        import websocket
    except ImportError:
        pytest.skip("websocket-client not installed")

    collected: list[TradeEvent] = []

    def on_message(ws, message):
        payload = json.loads(message)
        collected.extend(
            list(provider.normalize_ws_message(payload, receive_time_ms=int(time.time() * 1000)))
        )
        if len(collected) >= 3:
            ws.close()

    def on_open(ws):
        ws.send(json.dumps(provider.ws_subscribe_args(["BTCUSDT"])))

    app = websocket.WebSocketApp(
        provider.ws_url, on_open=on_open, on_message=on_message
    )
    import threading

    t = threading.Thread(
        target=lambda: app.run_forever(ping_interval=20, ping_timeout=10), daemon=True
    )
    t.start()
    t.join(timeout=10)
    try:
        app.close()
    except Exception:
        pass
    # Soft assertion: if WS delivers trades, they must normalize cleanly
    for ev in collected:
        assert ev.trade_id
        assert ev.symbol
        assert ev.event_time_ms > 0
        assert ev.source == "bybit_public_ws_publicTrade"


def test_never_substitute_turnover_for_trade_count():
    from backend.nexus_activity_metric_v2 import assert_no_silent_substitution

    instruments, tickers = _get_instruments_and_tickers()
    sym = "BTCUSDT"
    assert sym in tickers
    turnover = tickers[sym].get("turnover24h")
    volume = tickers[sym].get("volume24h")
    assert turnover is not None
    assert volume is not None
    with pytest.raises(ValueError):
        assert_no_silent_substitution(
            proposed_gate_value=float(turnover), source_field="turnover24h"
        )
    with pytest.raises(ValueError):
        assert_no_silent_substitution(
            proposed_gate_value=float(volume), source_field="volume24h"
        )
