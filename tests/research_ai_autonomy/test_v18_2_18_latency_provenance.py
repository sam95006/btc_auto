# -*- coding: utf-8 -*-
from backend.nexus_research_ai_autonomy.fast_path import (
    ProvenanceRecordingTransport,
    SimulatedDemoTransport,
)


def test_simulated_transport_labeled_local_not_exchange():
    sim = SimulatedDemoTransport(send_delay_ms=1, ack_delay_ms=2, fill_delay_ms=3)
    wrap = ProvenanceRecordingTransport(inner=sim)
    out = wrap.send_research_order({"symbol": "BTCUSDT", "side": "Buy", "qty": 0.001})
    assert out["real_http_request"] is False
    assert out["latency_class"] == "LOCAL_SIMULATION_LATENCY"
    assert out["transport_mode"] == "LOCAL_SIMULATION"
    assert out["not_bybit_exchange_latency"] is True
    prov = out["latency_provenance"]
    assert prov["exchange_domain"]
    assert "monotonic" in prov
    assert "split" in prov
    assert wrap.records


def test_provenance_split_keys():
    sim = SimulatedDemoTransport()
    wrap = ProvenanceRecordingTransport(inner=sim)
    out = wrap.send_research_order({"symbol": "ETHUSDT", "side": "Sell", "qty": 0.01})
    split = out["latency_provenance"]["split"]
    for k in ("network_roundtrip", "exchange_ack", "fill", "e2e"):
        assert k in split
