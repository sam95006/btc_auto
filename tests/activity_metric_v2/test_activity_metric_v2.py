"""Unit tests for Official Activity Metric V2 — fixtures only, no exchange writes."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.nexus_activity_metric_v2 import (
    ActivityCheckpointStore,
    OfficialTradeActivityProvider,
    RollingActivityWindow,
    assert_no_silent_substitution,
    explicit_proxy_binding,
    gate_intent_document,
)
from backend.nexus_activity_metric_v2.constants import DEFAULT_WINDOW_MS
from tests.activity_metric_v2.fixtures import (
    bybit_rest_fixture_rows,
    bybit_ws_fixture_message,
    make_trade,
    synthetic_stream,
)


WINDOW_MS = 3_600_000  # 1h for fast tests


def test_dedupe_and_symbol_isolation():
    win = RollingActivityWindow(symbol="BTCUSDT", window_ms=WINDOW_MS)
    t0 = 1_700_000_000_000
    assert win.ingest(make_trade(trade_id="a", event_time_ms=t0), now_ms=t0)
    assert not win.ingest(make_trade(trade_id="a", event_time_ms=t0 + 1), now_ms=t0 + 1)
    assert not win.ingest(
        make_trade(trade_id="b", symbol="ETHUSDT", event_time_ms=t0 + 2),
        now_ms=t0 + 2,
    )
    snap = win.snapshot(now_ms=t0 + 10)
    assert snap.unique_trade_count == 1
    assert win.stats()["duplicate_count"] == 1
    assert win.stats()["rejected_cross_symbol"] == 1


def test_window_expiration():
    win = RollingActivityWindow(symbol="BTCUSDT", window_ms=10_000)
    t0 = 1_700_000_000_000
    win.ingest(make_trade(trade_id="old", event_time_ms=t0), now_ms=t0)
    win.ingest(make_trade(trade_id="new", event_time_ms=t0 + 15_000), now_ms=t0 + 15_000)
    snap = win.snapshot(now_ms=t0 + 15_000)
    assert snap.unique_trade_count == 1
    assert snap.trade_count_window == 1


def test_out_of_order_still_accepted_when_unique():
    win = RollingActivityWindow(symbol="BTCUSDT", window_ms=WINDOW_MS)
    t0 = 1_700_000_000_000
    win.ingest(make_trade(trade_id="late", event_time_ms=t0 + 5_000), now_ms=t0 + 5_000)
    assert win.ingest(make_trade(trade_id="early", event_time_ms=t0), now_ms=t0 + 5_001)
    assert win.stats()["out_of_order_count"] == 1
    assert win.snapshot(now_ms=t0 + 5_001).unique_trade_count == 2


def test_clock_skew_clamped():
    win = RollingActivityWindow(
        symbol="BTCUSDT", window_ms=WINDOW_MS, max_clock_skew_ms=1_000
    )
    recv = 1_700_000_000_000
    # Event 1 hour ahead of receive → clamp
    win.ingest(
        make_trade(
            trade_id="skew",
            event_time_ms=recv + 3_600_000,
            receive_time_ms=recv,
        ),
        now_ms=recv,
    )
    assert win.stats()["clock_skew_count"] == 1
    snap = win.snapshot(now_ms=recv)
    assert snap.event_time_ms == recv


def test_partial_warmup_is_insufficient_history_not_zero_live():
    win = RollingActivityWindow(symbol="BTCUSDT", window_ms=DEFAULT_WINDOW_MS)
    t0 = 1_700_000_000_000
    # Only 1 hour of coverage inside a 24h window
    for ev in synthetic_stream(start_ms=t0, count=10, step_ms=360_000):
        win.ingest(ev, now_ms=t0 + 3_600_000)
    snap = win.snapshot(now_ms=t0 + 3_600_000)
    assert snap.quality_state == "INSUFFICIENT_HISTORY"
    assert snap.warmup_complete is False
    assert snap.trade_count_window == 10  # real count, not fabricated zero
    assert snap.trade_count_window != 0 or snap.quality_state != "LIVE"


def test_full_warmup_live():
    win = RollingActivityWindow(symbol="BTCUSDT", window_ms=WINDOW_MS, stale_ms=60_000)
    t0 = 1_700_000_000_000
    # Cover full 1h window
    for ev in synthetic_stream(start_ms=t0, count=61, step_ms=60_000):
        win.ingest(ev, now_ms=t0 + 3_600_000)
    snap = win.snapshot(now_ms=t0 + 3_600_000)
    assert snap.warmup_complete is True
    assert snap.quality_state == "LIVE"
    assert snap.trade_count_window == 61
    assert snap.buy_sell_activity.buy_count + snap.buy_sell_activity.sell_count == 61
    assert snap.freshness_ms is not None
    assert snap.coverage_start_ms == t0
    assert snap.coverage_end_ms == t0 + 60 * 60_000


def test_stale_after_warmup():
    win = RollingActivityWindow(symbol="BTCUSDT", window_ms=WINDOW_MS, stale_ms=1_000)
    t0 = 1_700_000_000_000
    for ev in synthetic_stream(start_ms=t0, count=61, step_ms=60_000):
        win.ingest(ev, now_ms=t0 + 3_600_000)
    warm = win.snapshot(now_ms=t0 + 3_600_000)
    assert warm.warmup_complete is True
    assert warm.quality_state == "LIVE"
    # Advance now far beyond last receive
    snap = win.snapshot(now_ms=t0 + 3_600_000 + 120_000)
    assert snap.warmup_complete is True
    assert snap.quality_state == "STALE"


def test_checkpoint_restart_recovery():
    t0 = 1_700_000_000_000
    win = RollingActivityWindow(symbol="BTCUSDT", window_ms=WINDOW_MS)
    for ev in synthetic_stream(start_ms=t0, count=20, step_ms=60_000):
        win.ingest(ev, now_ms=t0 + 20 * 60_000)

    with tempfile.TemporaryDirectory() as td:
        store = ActivityCheckpointStore(Path(td))
        store.save(win, now_ms=t0 + 20 * 60_000)
        assert store.exists("BTCUSDT")
        restored = store.load("BTCUSDT", now_ms=t0 + 20 * 60_000)
        assert restored is not None
        snap = restored.snapshot(now_ms=t0 + 20 * 60_000)
        assert snap.unique_trade_count == 20
        assert snap.symbol == "BTCUSDT"


def test_provider_rest_normalize_with_fixture_http():
    rows = bybit_rest_fixture_rows()

    def fake_get(url: str, params: dict):
        assert "/v5/market/recent-trade" in url
        assert params["symbol"] == "BTCUSDT"
        return {"retCode": 0, "result": {"list": rows}}

    provider = OfficialTradeActivityProvider(http_get=fake_get)
    events = provider.fetch_recent_trades(symbol="BTCUSDT", limit=5)
    assert len(events) == 5
    assert events[0].source == "bybit_public_rest_recent_trade"
    assert events[0].trade_id == "exec-0"


def test_provider_rate_limit_handling():
    calls = {"n": 0}

    def flaky_get(url: str, params: dict):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"retCode": 10006, "retMsg": "Too many visits", "result": {"list": []}}
        return {
            "retCode": 0,
            "result": {"list": bybit_rest_fixture_rows()},
        }

    provider = OfficialTradeActivityProvider(
        http_get=flaky_get, max_retries=2, backoff_base_seconds=0.0
    )
    provider.rate_limiter.rate_per_second = 1000.0
    provider.rate_limiter.tokens = 1000.0
    events = provider.fetch_recent_trades(symbol="BTCUSDT")
    assert provider.rate_limit_response_count >= 1
    assert provider.degraded is True
    assert len(events) == 5


def test_ws_stub_normalize():
    provider = OfficialTradeActivityProvider()
    stub = provider.ws_connect_stub()
    assert stub["stub"] is True
    assert "publicTrade" in stub["topics_supported"][0]
    sub = provider.ws_subscribe_args(["BTCUSDT", "ETHUSDT"])
    assert sub["op"] == "subscribe"
    assert "publicTrade.BTCUSDT" in sub["args"]
    events = list(
        provider.normalize_ws_message(bybit_ws_fixture_message(), receive_time_ms=1)
    )
    assert len(events) == 3
    assert events[0].source == "bybit_public_ws_publicTrade"


def test_gate_contract_forbids_volume_substitution():
    with pytest.raises(ValueError, match="silent_substitution_forbidden"):
        assert_no_silent_substitution(
            proposed_gate_value=12345, source_field="volume24h"
        )
    with pytest.raises(ValueError, match="silent_substitution_forbidden"):
        assert_no_silent_substitution(
            proposed_gate_value=999, source_field="turnover24h"
        )
    doc = gate_intent_document()
    assert doc["field"] == "trade_count_24h"
    assert doc["bybit_public_ticker_publishes_trade_count_24h"] is False
    assert doc["fail_closed_when_missing"] is True
    assert doc["thresholds_unchanged"] is True


def test_explicit_proxy_binding_versioned():
    win = RollingActivityWindow(symbol="BTCUSDT", window_ms=WINDOW_MS)
    t0 = 1_700_000_000_000
    for ev in synthetic_stream(start_ms=t0, count=61, step_ms=60_000):
        win.ingest(ev, now_ms=t0 + 3_600_000)
    snap = win.snapshot(now_ms=t0 + 3_600_000)
    binding = explicit_proxy_binding(snap)
    assert binding["proxy_metric"] == "trade_count_window"
    assert binding["gate_field"] == "trade_count_24h"
    assert binding["silent_substitution"] is False
    assert "volume24h" in binding["forbidden_sources"]
    # Must not claim injection happened
    assert "activity_metric_v2" in binding["proxy_version"]


def test_metrics_notional_and_source_fields():
    win = RollingActivityWindow(symbol="ETHUSDT", window_ms=WINDOW_MS)
    t0 = 1_700_000_000_000
    win.ingest(
        make_trade(
            trade_id="n1",
            symbol="ETHUSDT",
            price=2000.0,
            size=1.5,
            side="Buy",
            event_time_ms=t0,
        ),
        now_ms=t0,
    )
    snap = win.snapshot(now_ms=t0)
    assert snap.trade_notional_window == pytest.approx(3000.0)
    assert snap.source
    assert "trade_count_window" in snap.to_dict()
    assert snap.gate_field_proxy["silent_substitution_forbidden"] is True
