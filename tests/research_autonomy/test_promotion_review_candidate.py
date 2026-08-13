"""Synthetic smoke for offline promotion review (no live Zeabur data)."""
from __future__ import annotations

import json
from pathlib import Path

from tools.research.run_promotion_review_candidate import run_review


def test_promotion_review_streams_without_retaining_bars(tmp_path: Path) -> None:
    shadow = tmp_path / "autonomy" / "shadow_signals"
    shadow.mkdir(parents=True)
    ledger = []
    path_rows = []
    for i in range(2):
        sid = f"sig_{i}"
        ledger.append(
            {
                "signal_id": sid,
                "detected_at_ms": 1_700_000_000_000 + i * 1000,
                "symbol": "BTCUSDT" if i == 0 else "ETHUSDT",
                "direction": "LONG",
                "entry_price": 100.0,
                "expected_net_edge": 0.5 if i == 0 else -0.2,
                "entry_quality_score": 0.8 if i == 0 else 0.4,
                "lifecycle_state": "READY" if i == 0 else "WATCH",
                "regime": "TREND_UP",
                "market_structure": "TREND_UP",
                "supporting_evidence": ["MOMENTUM_ALIGN"],
                "contradicting_evidence": [],
                "snapshot_decision_id": f"dec_{i}",
            }
        )
        for h in (60, 180, 300, 900, 1800):
            path_rows.append(
                {
                    "signal_id": sid,
                    "decision_id": f"dec_{i}",
                    "horizon_sec": h,
                    "direction": "LONG",
                    "entry_price": 100.0,
                    "bars": [{"ts_ms": 0, "open": 100, "high": 100.6, "low": 99.8, "close": 100.3}],
                    "MFE": 0.5,
                    "MAE": -0.2,
                    "gross_hypothetical": 0.4,
                    "estimated_cost": 0.15,
                    "post_cost_hypothetical": 0.25 if i == 0 else -0.1,
                    "target_before_stop": True,
                    "stop_before_target": False,
                    "ambiguous_first_touch": False,
                }
            )
    (shadow / "active_shadow_signals.jsonl").write_text(
        "\n".join(json.dumps(r) for r in ledger) + "\n", encoding="utf-8"
    )
    (shadow / "path_records.jsonl").write_text(
        "\n".join(json.dumps(r) for r in path_rows) + "\n", encoding="utf-8"
    )
    snap_dir = tmp_path / "autonomy" / "decision_snapshots"
    snap_dir.mkdir(parents=True)
    (snap_dir / "cycle_test.jsonl").write_text(
        json.dumps(
            {
                "decision_id": "dec_0",
                "final_action": "SELECT",
                "entry_quality_score": 0.8,
                "expected_net_edge": 0.5,
                "regime": "TREND_UP",
            }
        )
        + "\n"
        + json.dumps(
            {
                "decision_id": "dec_1",
                "final_action": "WATCH",
                "entry_quality_score": 0.4,
                "expected_net_edge": -0.2,
                "regime": "RANGE",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = run_review(tmp_path, cf_max_records=5, cycles_run_hint=2)
    assert report["index_valid_full_count"] == 2
    assert report["dataset_integrity"] in {"PASS", "WARNING"}
    assert report["NO_AUTO_PROMOTION"] is True
    assert report["ready_for_demo_reenable"] is False
    assert report["strategy_changed"] is False
    assert "15m" in report["per_horizon"]
    assert report["per_horizon"]["15m"]["valid_sample_count"] == 2
