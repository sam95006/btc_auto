"""P0 shadow accumulation lifecycle repair — ledger, per-horizon once, no premature OUTCOME."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.shadow_observation_v1 import build_observation_report
from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    evaluate_ohlc_path,
    evaluate_signal_horizons,
    existing_path_keys,
    fetch_ohlc_path,
    load_path_records,
    refresh_mature_shadow_outcomes,
)
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    ledger_stats,
    load_shadow_signal_ledger,
    load_signal_state,
    mark_horizon_complete,
    persist_shadow_signals,
)


def _bar(ts: int, o: float, h: float, l: float, c: float, *, partial: bool = False) -> dict[str, Any]:
    return {
        "ts_ms": ts,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "entry_candle_partial": partial,
    }


def _sig(sid: str, *, ts: int, state: str = "READY") -> dict[str, Any]:
    return {
        "signal_id": sid,
        "lifecycle_state": state,
        "detected_at_ms": ts,
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "entry_price": 100.0,
        "expected_net_edge": 0.5,
        "entry_quality_score": 0.7,
        "direction_confidence_quant": 0.6,
        "supporting_evidence": ["MOMENTUM_5M_POSITIVE"],
        "contradicting_evidence": [],
        "snapshot_decision_id": f"dec_{sid}",
    }


class _FakeKlineClient:
    """Returns OHLC covering a historical start/end window (not only 'latest')."""

    def __init__(self, entry_ts: int):
        self.entry_ts = entry_ts
        self.calls: list[dict[str, str]] = []

    def public_get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        assert path == "/v5/market/kline"
        self.calls.append(dict(params))
        assert "start" in params and "end" in params
        start = int(params["start"])
        end = int(params["end"])
        rows = []
        # Bybit-style newest-first; include candles across the requested window
        t = start
        while t <= end:
            # modest favorable move
            rows.append([str(t), "100", "100.6", "99.7", "100.2", "1", "1"])
            t += 60_000
        rows.reverse()
        return {"result": {"list": rows}}


def test_cycle_b_overwrite_latest_does_not_drop_ledger_signal(tmp_path: Path) -> None:
    t0 = int(time.time() * 1000) - 3_600_000
    persist_shadow_signals(tmp_path, [_sig("sig_a", ts=t0)])
    # Cycle B overwrites latest with a different batch
    persist_shadow_signals(tmp_path, [_sig("sig_b", ts=t0 + 120_000)])
    ledger = load_shadow_signal_ledger(tmp_path)
    ids = {s["signal_id"] for s in ledger}
    assert ids == {"sig_a", "sig_b"}
    latest = json.loads(
        (tmp_path / "autonomy" / "shadow_signals" / "active_shadow_signals_latest.json").read_text()
    )
    assert [s["signal_id"] for s in latest["signals"]] == ["sig_b"]


def test_ledger_dedupes_duplicate_rows(tmp_path: Path) -> None:
    t0 = 1_700_000_000_000
    path = tmp_path / "autonomy" / "shadow_signals" / "active_shadow_signals.jsonl"
    path.parent.mkdir(parents=True)
    row = _sig("sig_dup", ts=t0)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.write(json.dumps({**row, "lifecycle_state": "OUTCOME"}) + "\n")
    stats = ledger_stats(tmp_path)
    assert stats["ledger_rows"] == 2
    assert stats["unique_signal_ids"] == 1
    assert stats["duplicate_signal_rows"] == 1
    uniq = load_shadow_signal_ledger(tmp_path)
    assert len(uniq) == 1
    assert uniq[0]["lifecycle_state"] == "READY"  # first wins


def test_1m_maturity_does_not_block_later_horizons(tmp_path: Path) -> None:
    entry = int(time.time() * 1000) - 600_000  # 10m ago → 1m/3m/5m due
    sig = _sig("sig_partial", ts=entry)
    persist_shadow_signals(tmp_path, [sig])
    client = _FakeKlineClient(entry)
    out1 = refresh_mature_shadow_outcomes(client, campaign_root=tmp_path)
    assert out1["signals_evaluated"] >= 1
    state = load_signal_state(tmp_path)
    entry_st = state["signals"]["sig_partial"]
    assert entry_st["lifecycle_state"] == "PARTIAL_OUTCOME"
    assert entry_st["fully_matured"] is False
    assert entry_st["completed_horizons"]["1m"] is True
    assert entry_st["completed_horizons"]["3m"] is True
    assert entry_st["completed_horizons"]["5m"] is True
    # 15m/30m not yet due
    assert entry_st["completed_horizons"]["15m"] is False
    keys = existing_path_keys(tmp_path)
    assert ("sig_partial", 60) in keys
    assert ("sig_partial", 180) in keys
    assert ("sig_partial", 300) in keys
    # Second refresh must not duplicate
    n_before = len(load_path_records(tmp_path))
    refresh_mature_shadow_outcomes(client, campaign_root=tmp_path)
    n_after = len(load_path_records(tmp_path))
    assert n_after == n_before


def test_full_horizon_ladder_exactly_once(tmp_path: Path) -> None:
    entry = int(time.time() * 1000) - 2_000_000  # >30m ago
    sig = _sig("sig_full", ts=entry)
    persist_shadow_signals(tmp_path, [sig])
    client = _FakeKlineClient(entry)
    refresh_mature_shadow_outcomes(client, campaign_root=tmp_path)
    keys = existing_path_keys(tmp_path)
    for h in (60, 180, 300, 900, 1800):
        assert ("sig_full", h) in keys
    # exactly one row per horizon
    rows = load_path_records(tmp_path)
    from collections import Counter

    c = Counter((r["signal_id"], int(r["horizon_sec"])) for r in rows)
    assert all(v == 1 for v in c.values())
    state = load_signal_state(tmp_path)["signals"]["sig_full"]
    assert state["fully_matured"] is True
    assert state["lifecycle_state"] == "OUTCOME"
    # refresh again — still once
    refresh_mature_shadow_outcomes(client, campaign_root=tmp_path)
    assert len(load_path_records(tmp_path)) == 5


def test_historical_kline_uses_start_end(tmp_path: Path) -> None:
    entry = 1_700_000_000_000
    client = _FakeKlineClient(entry)
    meta = fetch_ohlc_path(client, symbol="BTCUSDT", entry_ts_ms=entry, horizon_sec=300)
    assert client.calls
    assert "start" in client.calls[0] and "end" in client.calls[0]
    assert int(client.calls[0]["start"]) <= entry
    assert meta["point_count"] > 0
    assert meta["path_source"] == "bybit_public_1m_ohlc_start_end"


def test_entry_partial_and_ambiguous_still_hold() -> None:
    bars = [
        _bar(0, 100.0, 105.0, 99.0, 100.1, partial=True),
        _bar(60_000, 100.1, 100.3, 100.0, 100.2),
    ]
    out = evaluate_ohlc_path(
        entry_price=100.0, direction="LONG", bars=bars, stop_pct=1.0, target_pct=2.0, notional=100.0
    )
    assert out["mfe_pct"] == 0.3
    amb = evaluate_ohlc_path(
        entry_price=100.0,
        direction="LONG",
        bars=[_bar(60_000, 100.0, 100.6, 99.5, 100.1)],
        stop_pct=0.40,
        target_pct=0.55,
        notional=350.0,
    )
    assert amb["ambiguous_first_touch"] is True


def test_observation_uses_cumulative_ledger_not_latest_batch(tmp_path: Path) -> None:
    t0 = int(time.time() * 1000) - 3_600_000
    persist_shadow_signals(tmp_path, [_sig("sig_1", ts=t0), _sig("sig_2", ts=t0)])
    persist_shadow_signals(tmp_path, [_sig("sig_3", ts=t0)])  # latest batch size 1
    report = build_observation_report(campaign_root=tmp_path)
    assert report["unique_signals_created_total"] == 3
    assert report["signals_created"] == 3
    assert report["canonical_promotion_maturity_metric"] == "signals_fully_matured_valid_all_horizons"
    assert report["path_record_rows"] == 0
    assert report["signals_created"] != 1  # not latest batch


def test_gate_metric_not_path_record_rows(tmp_path: Path) -> None:
    t0 = int(time.time() * 1000) - 2_000_000
    persist_shadow_signals(tmp_path, [_sig("sig_x", ts=t0)])
    client = _FakeKlineClient(t0)
    refresh_mature_shadow_outcomes(client, campaign_root=tmp_path)
    report = build_observation_report(campaign_root=tmp_path)
    assert report["path_record_rows"] == 5
    assert report["unique_signals_created_total"] == 1
    assert report["signals_fully_matured_all_horizons"] == 1
    assert report["signals_matured"] == 1  # alias to fully matured
    assert report["path_record_rows"] != report["unique_signals_created_total"]


def test_mark_horizon_complete_partial_then_full() -> None:
    entry: dict[str, Any] = {
        "completed_horizons": {k: False for k in ("1m", "3m", "5m", "15m", "30m")},
        "completed_horizon_secs": [],
        "lifecycle_state": "READY",
        "fully_matured": False,
    }
    mark_horizon_complete(entry, horizon_sec=60, now_ms=1)
    assert entry["lifecycle_state"] == "PARTIAL_OUTCOME"
    assert entry["fully_matured"] is False
    for h in (180, 300, 900, 1800):
        mark_horizon_complete(entry, horizon_sec=h, now_ms=h)
    assert entry["fully_matured"] is True
    assert entry["lifecycle_state"] == "OUTCOME"


def test_evaluate_skips_immature_horizons(tmp_path: Path) -> None:
    class _Boom:
        def public_get(self, *_a, **_k):  # pragma: no cover
            raise AssertionError("must not fetch")

    now = int(time.time() * 1000)
    rows = evaluate_signal_horizons(
        _Boom(),
        signal=_sig("sig_new", ts=now),
        campaign_root=tmp_path,
        horizons=(60, 180, 300),
    )
    assert rows == []
