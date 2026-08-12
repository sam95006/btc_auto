# -*- coding: utf-8 -*-
"""V18.2.19 — real transport provenance labels + sim never claims REAL."""
from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import (
    TRANSPORT_MODE_REAL,
)
from backend.nexus_research_ai_autonomy.fast_path import (
    ProvenanceRecordingTransport,
    SimulatedDemoTransport,
)


def test_simulated_never_claims_real_transport():
    sim = SimulatedDemoTransport(send_delay_ms=1, ack_delay_ms=2, fill_delay_ms=3)
    wrap = ProvenanceRecordingTransport(inner=sim)
    out = wrap.send_research_order({"symbol": "ETHUSDT", "side": "Buy", "qty": 0.01})
    assert out["real_http_request"] is False
    assert out["transport_mode"] == "LOCAL_SIMULATION"
    assert out["latency_class"] == "LOCAL_SIMULATION_LATENCY"
    prov = out["latency_provenance"]
    assert prov["transport_mode"] != TRANSPORT_MODE_REAL
    assert prov["real_http_request"] is False


def test_provenance_records_split_and_domain():
    sim = SimulatedDemoTransport()
    wrap = ProvenanceRecordingTransport(inner=sim)
    out = wrap.send_research_order({"symbol": "BTCUSDT", "side": "Sell", "qty": 0.001})
    split = out["latency_provenance"]["split"]
    for k in ("network_roundtrip", "exchange_ack", "fill", "e2e"):
        assert k in split
    assert out["latency_provenance"]["exchange_domain"]


def test_real_transport_mode_constant():
    assert TRANSPORT_MODE_REAL == "BYBIT_DEMO_REAL_TRANSPORT"


def test_market_history_store_bounded(tmp_path):
    from backend.nexus_research_ai_autonomy.market_history_store import MarketHistoryStore

    store = MarketHistoryStore(root=tmp_path, max_jsonl_lines=5, max_sqlite_rows=5)
    for i in range(8):
        store.record_market_cycle(
            market_summary={"i": i},
            breadth=0.5,
            regime="TREND_UP",
            risk={"ok": True},
            radar_count=4,
        )
    st = store.stats()
    assert st["jsonl_lines"] <= 5
    assert st["sqlite_rows"] <= 5
    assert st["bounded"] is True
