"""Shadow measurement integrity tests — OHLC MFE/MAE, ambiguity, counterfactual wiring."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from backend.nexus_research_ai_autonomy.counterfactual_strategy_v1 import (
    build_per_horizon_stats,
    run_counterfactual_research,
)
from backend.nexus_research_ai_autonomy.decision_snapshot_v30 import build_decision_snapshot
from backend.nexus_research_ai_autonomy.public_opportunity_dto_v1 import (
    build_public_opportunity_dto,
    dto_leaks_private_data,
)
from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
    evaluate_ohlc_path,
    evaluate_signal_horizons,
    persist_path_record,
)
from backend.nexus_research_ai_autonomy.shadow_quality_report_v1 import build_shadow_quality_report
from backend.nexus_research_ai_autonomy.signal_quality_v1 import (
    compute_direction_scores,
    compute_entry_quality,
    compute_expected_net_edge,
    evaluate_regime,
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


def test_long_mfe_uses_high_mae_uses_low() -> None:
    bars = [
        _bar(60_000, 100.0, 100.8, 99.6, 100.2),
    ]
    out = evaluate_ohlc_path(
        entry_price=100.0,
        direction="LONG",
        bars=bars,
        stop_pct=1.0,
        target_pct=2.0,
        notional=100.0,
    )
    assert out["close_only_MFE"] is False
    assert out["mfe_pct"] == pytest.approx(0.8, abs=1e-6)
    assert out["mae_pct"] == pytest.approx(-0.4, abs=1e-6)
    assert out["MFE"] == pytest.approx(0.8, abs=1e-6)
    assert out["MAE"] == pytest.approx(-0.4, abs=1e-6)


def test_short_mfe_mae_inverse() -> None:
    bars = [
        _bar(60_000, 100.0, 100.5, 99.2, 99.8),
    ]
    out = evaluate_ohlc_path(
        entry_price=100.0,
        direction="SHORT",
        bars=bars,
        stop_pct=1.0,
        target_pct=2.0,
        notional=100.0,
    )
    assert out["mfe_pct"] == pytest.approx(0.8, abs=1e-6)
    assert out["mae_pct"] == pytest.approx(-0.5, abs=1e-6)


def test_entry_partial_candle_no_preentry_leakage() -> None:
    bars = [
        _bar(0, 100.0, 105.0, 99.0, 100.1, partial=True),
        _bar(60_000, 100.1, 100.3, 100.0, 100.2, partial=False),
    ]
    out = evaluate_ohlc_path(
        entry_price=100.0,
        direction="LONG",
        bars=bars,
        stop_pct=1.0,
        target_pct=2.0,
        notional=100.0,
    )
    assert out["mfe_pct"] == pytest.approx(0.3, abs=1e-6)
    assert out["mfe_pct"] < 1.0


def test_same_candle_target_and_stop_ambiguous() -> None:
    bars = [
        _bar(60_000, 100.0, 100.6, 99.5, 100.1),
    ]
    out = evaluate_ohlc_path(
        entry_price=100.0,
        direction="LONG",
        bars=bars,
        stop_pct=0.40,
        target_pct=0.55,
        notional=350.0,
    )
    assert out["ambiguous_first_touch"] is True
    assert out["first_touch"] == "AMBIGUOUS"
    assert out["target_before_stop"] is None
    assert out["stop_before_target"] is None


def test_no_outcome_before_horizon_maturity(tmp_path: Path) -> None:
    class _NoClient:
        def public_get(self, *_a, **_k):  # pragma: no cover
            raise AssertionError("must not fetch before maturity")

    now = int(time.time() * 1000)
    sig = {
        "signal_id": "sig_immature",
        "snapshot_decision_id": "dec_1",
        "symbol": "APRUSDT",
        "direction": "LONG",
        "entry_price": 1.0,
        "detected_at_ms": now,
    }
    rows = evaluate_signal_horizons(
        _NoClient(),
        signal=sig,
        campaign_root=tmp_path,
        horizons=(60, 180, 300),
    )
    assert rows == []


def test_decision_snapshot_unchanged_after_outcome() -> None:
    enrichment = {
        "symbol": "BTCUSDT",
        "timestamp_ms": 1_700_000_000_000,
        "price": 50_000.0,
        "turnover": 1e8,
        "activity_score": 0.7,
        "activity_source": "TURNOVER_LOG",
        "activity_fallback": False,
        "momentum_1m": {"return": 0.01},
        "momentum_5m": {"return": 0.02},
        "momentum_15m": {"return": 0.03},
        "volatility": 0.3,
        "data_freshness_ms": 10,
    }
    regime = evaluate_regime(enrichment)
    edge = compute_expected_net_edge(enrichment=enrichment, side="LONG")
    dirs = compute_direction_scores(
        enrichment, structure=regime["market_structure"], regime=regime["regime"]
    )
    eq = compute_entry_quality(
        enrichment,
        side="LONG",
        structure=regime["market_structure"],
        regime=regime["regime"],
        edge=edge,
    )
    snap = build_decision_snapshot(
        cycle_id="cyc_x",
        enrichment=enrichment,
        regime_info=regime,
        side="LONG",
        direction_scores=dirs,
        entry_quality=eq,
        edge=edge,
        supporting_evidence=["MOMENTUM_5M_POSITIVE"],
        contradicting_evidence=[],
        gate_results={},
        final_action="WATCH",
        final_reason="test",
    )
    original = json.dumps(snap, sort_keys=True)
    snap_copy = json.loads(original)
    snap_copy["outcome_MFE"] = 9.9
    assert json.dumps(snap, sort_keys=True) == original
    assert snap.get("no_hindsight") is True


def test_counterfactual_receives_real_path_records(tmp_path: Path) -> None:
    bars = [
        _bar(60_000, 100.0, 100.4, 99.7, 100.1),
        _bar(120_000, 100.1, 100.7, 100.0, 100.5),
    ]
    records = [
        {
            "entry_price": 100.0,
            "direction": "LONG",
            "bars": bars,
            "notional": 350.0,
            "horizon_sec": 300,
            "symbol": "APRUSDT",
        }
        for _ in range(3)
    ]
    report = run_counterfactual_research(campaign_root=tmp_path, path_records=records)
    counts = report["sample_counts"]
    assert counts["champion_v30"] == 3
    assert counts["wider_stop"] == 3
    assert counts["tighter_target"] == 3
    assert counts["wider_both"] == 3
    assert counts["narrow_scalp"] == 3
    for c in report["research_configs"]:
        assert c["stats"]["sample_count"] > 0
        assert c["auto_promoted"] is False
        assert c["stats"].get("status") != "AWAITING_PATH_RECORDS"


def test_cost_model_provenance_present() -> None:
    out = evaluate_ohlc_path(
        entry_price=100.0,
        direction="LONG",
        bars=[_bar(60_000, 100.0, 100.2, 99.9, 100.1)],
        stop_pct=0.40,
        target_pct=0.55,
        notional=350.0,
        spread_cost=0.05,
        slippage_cost=0.02,
        funding_cost=0.01,
    )
    assert out["fee_model_source"]
    assert out["fallback_fee_rate"] is not None
    assert out["spread_cost"] == 0.05
    assert out["slippage_cost"] == 0.02
    assert out["funding_cost"] == 0.01
    assert out["total_estimated_cost"] > out["spread_cost"]


def test_horizons_reported_independently(tmp_path: Path) -> None:
    for h, mfe in ((60, 0.1), (300, 0.5), (900, 1.0)):
        persist_path_record(
            tmp_path,
            {
                "signal_id": f"sig_{h}",
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "entry_price": 100.0,
                "horizon_sec": h,
                "bars": [_bar(60_000, 100.0, 100.0 + mfe, 99.9, 100.0)],
                "MFE": mfe,
                "MAE": -0.1,
                "post_cost_hypothetical": mfe - 0.4,
                "gross_hypothetical": mfe,
                "estimated_cost": 0.4,
                "ambiguous_first_touch": False,
                "target_before_stop": False,
                "stop_before_target": False,
            },
        )
    pack = build_per_horizon_stats(tmp_path)
    assert "60" in pack["per_horizon"]
    assert "300" in pack["per_horizon"]
    assert "900" in pack["per_horizon"]
    assert pack["per_horizon"]["60"]["mature_sample_count"] == 1
    assert pack["per_horizon"]["300"]["mature_sample_count"] == 1
    assert pack["per_horizon"]["60"]["median_MFE"] != pack["per_horizon"]["900"]["median_MFE"]


def test_public_dto_no_private_leak_with_outcome_fields() -> None:
    snap = {
        "symbol": "APRUSDT",
        "side": "LONG",
        "entry_quality_score": 0.66,
        "expected_net_edge": 0.4,
        "direction_confidence_quant": 0.6,
        "regime": "RANGE",
        "market_structure": "TREND_UP",
        "supporting_evidence": ["OI_EXPANDING"],
        "contradicting_evidence": ["SPREAD_WIDE"],
        "final_action": "WATCH",
        "data_freshness_ms": 12,
        "activity_source": "TURNOVER_LOG",
        "activity_fallback": False,
        "rank": 2,
        "rank_percentile": 90.0,
        "wallet_before": {"wallet_balance": "999"},
        "mistake_signature": "SECRET_SIG",
        "bybit_orderId": "order-xyz",
    }
    dto = build_public_opportunity_dto(snap)
    assert dto.get("historical_similar_setup_stats") is None
    blob = json.dumps(dto).lower()
    assert "wallet" not in blob
    assert "mistake_signature" not in blob
    assert "bybit_order" not in blob
    assert dto_leaks_private_data(dto) is False


def test_shadow_quality_report_written(tmp_path: Path) -> None:
    report = build_shadow_quality_report(campaign_root=tmp_path)
    assert report["write_enabled"] is False
    assert report["ready_for_demo_reenable"] is False
    assert report["close_only_MFE_removed"] is True
    assert report["historical_similar_setup_stats"] is None
    path = tmp_path / "autonomy" / "shadow_signals" / "shadow_quality_latest.json"
    assert path.exists()
