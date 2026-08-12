"""Shadow observation gate — aggregate only; no strategy mutation."""
from __future__ import annotations

import json
from pathlib import Path

from backend.nexus_research_ai_autonomy.shadow_observation_v1 import (
    STAGE_THRESHOLDS,
    build_observation_report,
    observation_dir,
)


def test_observation_empty_campaign_ready_false(tmp_path: Path) -> None:
    report = build_observation_report(campaign_root=tmp_path, runtime_commit="test")
    assert report["ready_for_demo_reenable"] is False
    assert report["demo_write_reenabled"] is False
    assert report["strategy_changed"] is False
    assert report["risk_changed"] is False
    assert report["gate_lowered"] is False
    assert report["signals_created"] == 0
    assert report["signals_matured"] == 0
    assert report["next_checkpoint"] == "EARLY_DIAGNOSTIC_AT_50_MATURED"
    assert set(report["per_horizon"].keys()) == {"1m", "3m", "5m", "15m", "30m"}
    out = observation_dir(tmp_path) / "observation_latest.json"
    assert out.exists()
    disk = json.loads(out.read_text(encoding="utf-8"))
    assert disk["schema"] == "v30_shadow_observation_v1"
    assert STAGE_THRESHOLDS[0][1] == 50


def test_observation_does_not_merge_horizons(tmp_path: Path) -> None:
    sh = tmp_path / "autonomy" / "shadow_signals"
    sh.mkdir(parents=True)
    # Two matured path rows on different horizons — must stay separate
    rows = [
        {
            "signal_id": "s1",
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "horizon_sec": 300,
            "post_cost_hypothetical": 1.0,
            "MFE": 2.0,
            "MAE": -0.5,
            "target_before_stop": True,
            "stop_before_target": False,
            "ambiguous_first_touch": False,
        },
        {
            "signal_id": "s2",
            "symbol": "ETHUSDT",
            "direction": "SHORT",
            "horizon_sec": 900,
            "post_cost_hypothetical": -1.0,
            "MFE": 0.5,
            "MAE": -2.0,
            "target_before_stop": False,
            "stop_before_target": True,
            "ambiguous_first_touch": False,
        },
    ]
    (sh / "path_records.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    (sh / "active_shadow_signals_latest.json").write_text(
        json.dumps({"signals": [{"signal_id": "s1"}, {"signal_id": "s2"}]}),
        encoding="utf-8",
    )
    report = build_observation_report(campaign_root=tmp_path)
    assert report["per_horizon"]["5m"]["signals_matured"] == 1
    assert report["per_horizon"]["15m"]["signals_matured"] == 1
    assert report["per_horizon"]["5m"]["post_cost_expectancy"] == 1.0
    assert report["per_horizon"]["15m"]["post_cost_expectancy"] == -1.0
    # No merged headline win_rate field
    assert "headline_win_rate" not in report
    assert report["ready_for_demo_reenable"] is False
