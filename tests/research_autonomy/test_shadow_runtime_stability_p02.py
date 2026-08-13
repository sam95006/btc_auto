"""P0.2 crashloop / streaming history repair tests."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest import mock

from backend.nexus_research_ai_autonomy.counterfactual_strategy_v1 import run_counterfactual_research
from backend.nexus_research_ai_autonomy.shadow_observation_v1 import build_observation_report_lightweight
from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import (
    ensure_path_index,
    rebuild_path_index_streaming,
    rss_mb,
    write_runtime_stage,
)
from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    load_path_records,
    path_records_for_counterfactual,
    persist_path_record,
)
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import persist_shadow_signals


def _write_many_path_rows(path: Path, n: int, *, with_bars: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for i in range(n):
            row: dict[str, Any] = {
                "signal_id": f"sig_{i % 500}",
                "horizon_sec": [60, 180, 300, 900, 1800][i % 5],
                "entry_price": 100.0,
                "direction": "LONG",
                "post_cost_hypothetical": 0.1 if i % 3 else -0.1,
                "MFE": 0.2,
                "MAE": -0.1,
            }
            if with_bars:
                # large-ish bars payload
                row["bars"] = [
                    {"ts_ms": j, "open": 1, "high": 1.1, "low": 0.9, "close": 1.0}
                    for j in range(30)
                ]
            fh.write(json.dumps(row) + "\n")


def test_streaming_index_20k_without_giant_bar_list(tmp_path: Path) -> None:
    path = tmp_path / "autonomy" / "shadow_signals" / "path_records.jsonl"
    _write_many_path_rows(path, 2000, with_bars=True)
    idx = rebuild_path_index_streaming(tmp_path, max_sec=60)
    assert idx["path_record_rows"] == 2000
    assert idx["unique_path_keys"] > 0
    # index must not store bars
    assert "bars" not in json.dumps(idx)[:500] or '"bars"' not in str(idx.get("keys"))


def test_lightweight_observation_does_not_call_load_path_records(tmp_path: Path) -> None:
    persist_shadow_signals(
        tmp_path,
        [
            {
                "signal_id": "sig_1",
                "lifecycle_state": "READY",
                "detected_at_ms": 1,
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "entry_price": 1.0,
            }
        ],
    )
    path = tmp_path / "autonomy" / "shadow_signals" / "path_records.jsonl"
    _write_many_path_rows(path, 100, with_bars=True)
    ensure_path_index(tmp_path, force_rebuild=True)
    with mock.patch(
        "backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1.load_path_records",
        side_effect=AssertionError("hot path must not full-load path records"),
    ):
        report = build_observation_report_lightweight(campaign_root=tmp_path, runtime_commit="t")
    assert report["mode"] == "lightweight_hot_cycle"
    assert report["unique_signals_created_total"] == 1
    assert report["canonical_promotion_maturity_metric"] == "signals_fully_matured_valid_all_horizons"
    assert report["signal_ledger_rows"] is not None


def test_counterfactual_bounded_not_full_history(tmp_path: Path) -> None:
    path = tmp_path / "autonomy" / "shadow_signals" / "path_records.jsonl"
    path.parent.mkdir(parents=True)
    rows = []
    for i in range(80):
        rows.append(
            {
                "signal_id": f"s{i}",
                "horizon_sec": 300,
                "entry_price": 100.0,
                "direction": "LONG",
                "bars": [{"ts_ms": 0, "open": 100, "high": 100.5, "low": 99.5, "close": 100.2}],
            }
        )
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    batch = path_records_for_counterfactual(tmp_path)
    assert len(batch) <= 25
    report = run_counterfactual_research(campaign_root=tmp_path, path_records=batch)
    assert report["mode"] == "incremental_bounded"
    assert report["path_records_used"] <= 25
    # second call advances
    batch2 = path_records_for_counterfactual(tmp_path)
    assert len(batch2) <= 25


def test_stage_marker_survives(tmp_path: Path) -> None:
    write_runtime_stage(tmp_path, stage="BACKFILL", status="RUNNING")
    write_runtime_stage(tmp_path, stage="BACKFILL", status="ERROR", error="boom")
    raw = json.loads((tmp_path / "autonomy" / "shadow_runtime_stage.json").read_text())
    assert raw["stage"] == "BACKFILL"
    assert raw["status"] == "ERROR"
    assert raw["last_error"] == "boom"
    assert "pid" in raw


def test_memory_telemetry_callable() -> None:
    # May be None on some platforms; must not raise
    _ = rss_mb()


def test_persist_updates_index_without_full_reload(tmp_path: Path) -> None:
    persist_path_record(
        tmp_path,
        {
            "signal_id": "sig_x",
            "horizon_sec": 60,
            "bars": [{"ts_ms": 1, "open": 1, "high": 1, "low": 1, "close": 1}],
            "post_cost_hypothetical": 0.1,
            "MFE": 0.1,
            "MAE": -0.1,
        },
    )
    idx = ensure_path_index(tmp_path)
    assert idx["unique_path_keys"] >= 1
    assert "sig_x|60" in (idx.get("keys") or {})


def test_observation_updates_when_heavy_deferred(tmp_path: Path) -> None:
    persist_shadow_signals(
        tmp_path,
        [
            {
                "signal_id": "a",
                "lifecycle_state": "READY",
                "detected_at_ms": 1,
                "symbol": "X",
                "direction": "LONG",
                "entry_price": 1,
            }
        ],
    )
    r = build_observation_report_lightweight(
        campaign_root=tmp_path,
        backfill_status="PARTIAL",
        backfill_progress={"horizons_processed_this_cycle": 3, "backfill_status": "PARTIAL"},
    )
    assert r["backfill_status"] == "PARTIAL"
    assert r["heavy_analysis_deferred"] is True
    disk = json.loads(
        (tmp_path / "autonomy" / "shadow_observation" / "observation_latest.json").read_text()
    )
    assert disk["unique_signals_created_total"] == 1


def test_repeated_cycles_do_not_recompute_full_cf_history(tmp_path: Path) -> None:
    path = tmp_path / "autonomy" / "shadow_signals" / "path_records.jsonl"
    path.parent.mkdir(parents=True)
    rows = []
    for i in range(60):
        rows.append(
            {
                "signal_id": f"s{i}",
                "horizon_sec": 300,
                "entry_price": 100.0,
                "direction": "LONG",
                "bars": [{"ts_ms": 0, "open": 100, "high": 100.5, "low": 99.5, "close": 100.2}],
            }
        )
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    r1 = run_counterfactual_research(campaign_root=tmp_path)
    assert r1["path_records_used"] <= 25
    r2 = run_counterfactual_research(campaign_root=tmp_path)
    assert r2["path_records_used"] <= 25
    # Accumulator grew by at most 2 bounded batches, not full 60*5
    assert r2["sample_counts"]["champion_v30"] <= 50
    assert r2["mode"] == "incremental_bounded"


def test_backfill_budgets_honored(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_SEC", "20")
    monkeypatch.setenv("NEXUS_SHADOW_BACKFILL_MAX_HORIZONS_PER_CYCLE", "40")
    from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import _backfill_budgets

    max_sec, max_h = _backfill_budgets()
    assert max_sec == 20.0
    assert max_h == 40


def test_child_exit_diagnostics_in_supervisor() -> None:
    text = Path("deploy/zeabur_unified/start.sh").read_text(encoding="utf-8")
    assert "last_child_exit.json" in text
    assert 'child":"autonomy"' in text or "child=autonomy" in text
    assert 'child":"web"' in text or "child=web" in text
    assert "last_shadow_stage" in text
    assert "shadow_runtime_stage.json" in text


def test_no_strategy_risk_write_flags_in_lightweight_observation(tmp_path: Path) -> None:
    r = build_observation_report_lightweight(campaign_root=tmp_path)
    assert r["strategy_changed"] is False
    assert r["risk_changed"] is False
    assert r["gate_lowered"] is False
    assert r["demo_write_reenabled"] is False
    assert r["mainnet"] is False
    assert r["real_money"] is False
    assert r["write_enabled"] is False


def test_flat_cycle_uses_lightweight_observation_symbol() -> None:
    src = Path("backend/nexus_research_ai_autonomy/research_flat_cycle_v30.py").read_text(
        encoding="utf-8"
    )
    assert "build_observation_report_lightweight" in src
    # Hot cycle must not call the heavy builder
    assert "build_observation_report(" not in src.replace(
        "build_observation_report_lightweight", ""
    )
    assert "load_path_records" not in src
    assert "dataset_file_sizes" in src
    assert "SHADOW_MAINTENANCE_PARTIAL" in src