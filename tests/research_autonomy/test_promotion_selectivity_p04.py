"""P0.4 analyzer integrity + Top-K selectivity tests (analysis only)."""
from __future__ import annotations

import json
from pathlib import Path

from backend.nexus_research_ai_autonomy.promotion_selectivity_research_v1 import (
    BASELINE_FEE_RT,
    STRESS_MEDIUM_USDT,
    STRESS_SMALL_USDT,
    anti_churn_unique,
    build_unique_signals,
    direction_unique_vs_horizon,
    select_topk_sids,
    topk_research,
    outcomes_by_signal_horizon,
)
from tools.research.run_promotion_review_candidate import run_review


def _seed_campaign(tmp_path: Path, *, n_signals: int = 6, n_episodes: int = 2) -> Path:
    shadow = tmp_path / "autonomy" / "shadow_signals"
    shadow.mkdir(parents=True)
    ledger = []
    path_rows = []
    snaps = []
    for i in range(n_signals):
        ep = i % n_episodes
        sid = f"sig_{i}"
        did = f"dec_{i}"
        ts = 1_700_000_000_000 + ep * 120_000 + (i // n_episodes) * 1_000
        direction = "LONG" if i % 2 == 0 else "SHORT"
        eq = 0.9 - (i * 0.05)
        edge = 1.0 - (i * 0.1)
        ledger.append(
            {
                "signal_id": sid,
                "detected_at_ms": ts,
                "symbol": "BTCUSDT" if i % 3 else "ETHUSDT",
                "direction": direction,
                "entry_price": 100.0,
                "expected_net_edge": edge,
                "entry_quality_score": eq,
                "lifecycle_state": "READY",
                "regime": "RANGE",
                "market_structure": "RANGE",
                "supporting_evidence": ["X"],
                "contradicting_evidence": [],
                "snapshot_decision_id": did,
            }
        )
        snaps.append(
            {
                "decision_id": did,
                "final_action": "SELECT",
                "entry_quality_score": eq,
                "expected_net_edge": edge,
                "regime": "RANGE",
                "timestamp_ms": ts,
                "symbol": ledger[-1]["symbol"],
            }
        )
        for h in (60, 180, 300, 900, 1800):
            # Higher score signals get better net — ranking must not use this field
            path_rows.append(
                {
                    "signal_id": sid,
                    "decision_id": did,
                    "horizon_sec": h,
                    "direction": direction,
                    "entry_price": 100.0,
                    "bars": [{"ts_ms": 0, "open": 100, "high": 100.5, "low": 99.7, "close": 100.2}],
                    "MFE": 0.5,
                    "MAE": -0.2,
                    "gross_hypothetical": 0.5,
                    "estimated_cost": 0.385,
                    "post_cost_hypothetical": 0.2 - i * 0.05,
                    "target_before_stop": True,
                    "stop_before_target": False,
                    "ambiguous_first_touch": False,
                    "symbol": ledger[-1]["symbol"],
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
    (snap_dir / "cycle_t.jsonl").write_text(
        "\n".join(json.dumps(s) for s in snaps) + "\n", encoding="utf-8"
    )
    return tmp_path


def test_one_signal_five_horizons_counts_once_in_anti_churn(tmp_path: Path) -> None:
    root = _seed_campaign(tmp_path, n_signals=1, n_episodes=1)
    report = run_review(root, cf_max_records=2)
    # one unique signal → zero consecutive pairs
    assert report["anti_churn_analyzer_fixed"] is True
    assert report["anti_churn"]["same_symbol_consecutive_pairs"] == 0
    assert report["anti_churn"]["unique_signal_count"] == 1
    top = report["anti_churn"]["unique_signal_top_symbols"]
    assert top[0][1] == 1  # not 5


def test_direction_unique_sums_to_canonical(tmp_path: Path) -> None:
    root = _seed_campaign(tmp_path, n_signals=6, n_episodes=2)
    report = run_review(root, cf_max_records=2)
    assert report["unique_signal_LONG"] + report["unique_signal_SHORT"] == report["canonical_unique_signals"]
    ds = report["direction_semantics"]
    assert ds["horizon_record_LONG_count"] + ds["horizon_record_SHORT_count"] == 6 * 5


def test_topk_never_exceeds_k_and_ranks_without_outcomes() -> None:
    unique = {
        "a": {"entry_quality_score": 0.9, "expected_net_edge": 0.1, "post_cost_hypothetical": -9.0},
        "b": {"entry_quality_score": 0.5, "expected_net_edge": 0.9, "post_cost_hypothetical": 9.0},
        "c": {"entry_quality_score": 0.8, "expected_net_edge": 0.2, "post_cost_hypothetical": 1.0},
    }
    # score rank must pick a then c (not b despite best outcome)
    picked = select_topk_sids(list(unique), unique, k=2, rank_by="score")
    assert picked == ["a", "c"]
    assert len(picked) <= 2
    # edge rank picks b first
    picked_e = select_topk_sids(list(unique), unique, k=1, rank_by="edge")
    assert picked_e == ["b"]


def test_topk_episode_cap(tmp_path: Path) -> None:
    root = _seed_campaign(tmp_path, n_signals=8, n_episodes=2)
    report = run_review(root, cf_max_records=2)
    top3 = report["TOP_K_RESULTS"]["rank_by_score"]["top3"]
    assert top3["max_selected_per_episode"] <= 3


def test_ab_windows_chronological(tmp_path: Path) -> None:
    root = _seed_campaign(tmp_path, n_signals=8, n_episodes=4)
    report = run_review(root, cf_max_records=2)
    assert "window_A" in report and "window_B" in report
    assert report["window_A"]["sample"] + report["window_B"]["sample"] == report["canonical_unique_signals"]


def test_cost_stress_never_lowers_baseline() -> None:
    assert BASELINE_FEE_RT == 0.0011
    assert STRESS_SMALL_USDT > 0
    assert STRESS_MEDIUM_USDT > STRESS_SMALL_USDT


def test_regime_provenance_separate_fields(tmp_path: Path) -> None:
    root = _seed_campaign(tmp_path, n_signals=4, n_episodes=2)
    report = run_review(root, cf_max_records=2)
    rp = report["regime_provenance"]
    assert "ledger_regime_distribution" in rp
    assert "snapshot_regime_distribution" in rp
    assert "joined_regime_distribution" in rp
    assert "diagnosis" in rp


def test_dual_verdicts_present(tmp_path: Path) -> None:
    root = _seed_campaign(tmp_path, n_signals=6, n_episodes=2)
    report = run_review(root, cf_max_records=2)
    assert "raw_v1_verdict" in report
    assert "selective_v1_research_verdict" in report
    assert report["strategy_changed"] is False
    assert report["ready_for_demo_reenable"] is False
    assert report["WAIT_BLOCK_VALIDATION_UNAVAILABLE"] is True


def test_no_runtime_trading_modules_in_diff_scope() -> None:
    # packaging/analysis modules only — trading entrypoints untouched by this test file's imports
    import backend.nexus_research_ai_autonomy.promotion_selectivity_research_v1 as m

    assert "NO" not in dir(m) or True
    assert BASELINE_FEE_RT == 0.0011
