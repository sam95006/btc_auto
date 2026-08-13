"""P0.1 bounded shadow backfill + valid maturity gates."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.shadow_observation_v1 import build_observation_report
from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    existing_path_key_status,
    load_path_records,
    path_outcome_audit,
    refresh_mature_shadow_outcomes,
)
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    ensure_signal_state_entry,
    ledger_stats,
    load_backfill_progress,
    load_signal_state,
    mark_horizon_complete,
    persist_shadow_signals,
    recompute_maturity_flags,
    save_signal_state,
)


def _sig(sid: str, *, ts: int) -> dict[str, Any]:
    return {
        "signal_id": sid,
        "lifecycle_state": "READY",
        "detected_at_ms": ts,
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "entry_price": 100.0,
        "snapshot_decision_id": f"dec_{sid}",
    }


class _FakeClient:
    def __init__(self):
        self.calls = 0

    def public_get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        self.calls += 1
        start = int(params.get("start") or 0)
        end = int(params.get("end") or start)
        rows = []
        t = start
        while t <= end:
            rows.append([str(t), "100", "100.5", "99.8", "100.2", "1", "1"])
            t += 60_000
        rows.reverse()
        return {"result": {"list": rows}}


class _BoomClient:
    def public_get(self, *_a, **_k):
        raise RuntimeError("api_fail")


def test_large_ledger_bounded_partial(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_SEC", "2")
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE", "5")
    t0 = int(time.time() * 1000) - 3_600_000
    # Simulate large ledger uniquely (keep unique count high but work-budget small)
    batch = [_sig(f"sig_{i:04d}", ts=t0 - i * 1000) for i in range(200)]
    # append in chunks via persist
    for i in range(0, len(batch), 20):
        persist_shadow_signals(tmp_path, batch[i : i + 20])
    client = _FakeClient()
    out = refresh_mature_shadow_outcomes(client, campaign_root=tmp_path)
    assert out["bounded_backfill"] is True
    assert out["backfill_status"] in {"PARTIAL", "CAUGHT_UP"}
    assert out["horizons_processed_this_cycle"] <= 5
    assert out["backfill_work_budget"] == 5
    # Not required to finish 200*5 horizons in one pass
    assert out["horizons_processed_this_cycle"] < 200 * 5


def test_budget_returns_partial_cleanly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE", "3")
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_SEC", "30")
    t0 = int(time.time() * 1000) - 2_000_000
    persist_shadow_signals(tmp_path, [_sig(f"sig_{i}", ts=t0) for i in range(10)])
    out = refresh_mature_shadow_outcomes(_FakeClient(), campaign_root=tmp_path)
    assert out["backfill_status"] == "PARTIAL"
    assert out["horizons_processed_this_cycle"] == 3


def test_state_checkpoint_after_partial(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE", "4")
    t0 = int(time.time() * 1000) - 2_000_000
    persist_shadow_signals(tmp_path, [_sig("sig_a", ts=t0), _sig("sig_b", ts=t0)])
    refresh_mature_shadow_outcomes(_FakeClient(), campaign_root=tmp_path)
    state = load_signal_state(tmp_path)
    assert state["signals"]
    # some horizons marked
    any_done = any(
        str(st) != "PENDING"
        for e in state["signals"].values()
        for st in (e.get("horizon_status") or {}).values()
    )
    assert any_done
    prog = load_backfill_progress(tmp_path)
    assert "cursor_index" in prog


def test_existing_path_sync_no_api(tmp_path: Path) -> None:
    t0 = int(time.time() * 1000) - 2_000_000
    persist_shadow_signals(tmp_path, [_sig("sig_sync", ts=t0)])
    sh = tmp_path / "autonomy" / "shadow_signals"
    # Pre-seed path records for all horizons (valid)
    rows = []
    for h in (60, 180, 300, 900, 1800):
        rows.append(
            {
                "signal_id": "sig_sync",
                "horizon_sec": h,
                "bars": [{"ts_ms": t0, "open": 1, "high": 1, "low": 1, "close": 1}],
                "post_cost_hypothetical": 0.1,
                "MFE": 0.2,
                "MAE": -0.1,
            }
        )
    (sh / "path_records.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    client = _BoomClient()  # must not be called for sync-only
    out = refresh_mature_shadow_outcomes(client, campaign_root=tmp_path)
    assert out["state_synced_from_existing_paths"] >= 5
    assert out["new_paths_written"] == 0
    st = load_signal_state(tmp_path)["signals"]["sig_sync"]
    assert st["fully_matured_valid_all_horizons"] is True
    assert st["fully_resolved_all_horizons"] is True


def test_second_cycle_resumes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE", "2")
    t0 = int(time.time() * 1000) - 2_000_000
    persist_shadow_signals(tmp_path, [_sig(f"sig_{i}", ts=t0) for i in range(5)])
    c = _FakeClient()
    a = refresh_mature_shadow_outcomes(c, campaign_root=tmp_path)
    b = refresh_mature_shadow_outcomes(c, campaign_root=tmp_path)
    assert a["backfill_status"] == "PARTIAL"
    keys = existing_path_key_status(tmp_path)
    assert len(keys) == a["horizons_processed_this_cycle"] + b["horizons_processed_this_cycle"]
    # no duplicate keys
    assert len(keys) == len(load_path_records(tmp_path))


def test_unavailable_resolved_not_valid() -> None:
    entry: dict[str, Any] = ensure_signal_state_entry(
        {"signals": {}}, _sig("sig_u", ts=1)
    )
    mark_horizon_complete(entry, horizon_sec=60, now_ms=1, unavailable_reason="HISTORICAL_PATH_UNAVAILABLE")
    assert entry["horizon_status"]["1m"] == "UNAVAILABLE"
    assert entry["completed_horizons"]["1m"] is True
    assert entry["fully_matured_valid_all_horizons"] is False
    for h in (180, 300, 900, 1800):
        mark_horizon_complete(entry, horizon_sec=h, now_ms=h, unavailable_reason="HISTORICAL_PATH_UNAVAILABLE")
    assert entry["fully_resolved_all_horizons"] is True
    assert entry["fully_matured_valid_all_horizons"] is False
    assert entry["fully_matured"] is False
    assert entry["invalid_for_promotion"] is True


def test_five_valid_horizons_promotion_ready() -> None:
    entry: dict[str, Any] = ensure_signal_state_entry({"signals": {}}, _sig("sig_v", ts=1))
    for h in (60, 180, 300, 900, 1800):
        mark_horizon_complete(entry, horizon_sec=h, now_ms=h)
    assert entry["fully_matured_valid_all_horizons"] is True
    assert entry["fully_matured"] is True
    assert entry["fully_resolved_all_horizons"] is True


def test_observation_updates_on_partial(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE", "2")
    t0 = int(time.time() * 1000) - 2_000_000
    persist_shadow_signals(tmp_path, [_sig(f"sig_{i}", ts=t0) for i in range(8)])
    out = refresh_mature_shadow_outcomes(_FakeClient(), campaign_root=tmp_path)
    assert out["backfill_status"] == "PARTIAL"
    report = build_observation_report(
        campaign_root=tmp_path,
        runtime_commit="test",
        backfill_status=out.get("backfill_status"),
        backfill_progress=out,
    )
    assert report["signal_ledger_rows"] is not None
    assert report["unique_signals_created_total"] == 8
    assert report["canonical_promotion_maturity_metric"] == "signals_fully_matured_valid_all_horizons"
    assert report["backfill_status"] == "PARTIAL"
    assert report["next_checkpoint"].endswith("VALID_FULLY_MATURED")
    disk = json.loads(
        (tmp_path / "autonomy" / "shadow_observation" / "observation_latest.json").read_text()
    )
    assert disk["unique_signals_created_total"] == 8


def test_gate_uses_valid_full_only(tmp_path: Path) -> None:
    report = build_observation_report(campaign_root=tmp_path)
    assert report["canonical_promotion_maturity_metric"] == "signals_fully_matured_valid_all_horizons"
    assert "VALID_FULLY_MATURED" in report["next_checkpoint"]


def test_ledger_and_path_duplicate_audit(tmp_path: Path) -> None:
    sh = tmp_path / "autonomy" / "shadow_signals"
    sh.mkdir(parents=True)
    row = _sig("sig_d", ts=1)
    with (sh / "active_shadow_signals.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.write(json.dumps(row) + "\n")
    with (sh / "path_records.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"signal_id": "sig_d", "horizon_sec": 60, "bars": [1]}) + "\n")
        fh.write(json.dumps({"signal_id": "sig_d", "horizon_sec": 60, "bars": [1]}) + "\n")
    ls = ledger_stats(tmp_path)
    assert ls["ledger_rows"] == 2 and ls["unique_signal_ids"] == 1 and ls["duplicate_signal_rows"] == 1
    aud = path_outcome_audit(tmp_path)
    assert aud["path_record_rows"] == 2
    assert aud["unique_path_keys"] == 1
    assert aud["duplicate_path_record_rows"] == 1
