"""Tests for V16-C Probabilistic Regime Engine V2 — three passes."""
from __future__ import annotations

from backend.nexus_probabilistic_regime_v2.adversarial import (
    run_adversarial_review,
    run_independent_break_attempts,
)
from backend.nexus_probabilistic_regime_v2.bans import hard_ban_probe_matrix
from backend.nexus_probabilistic_regime_v2.calibration import (
    apply_calibration,
    calibration_contract,
)
from backend.nexus_probabilistic_regime_v2.constants import (
    HARD_BANS,
    OUTPUT_KEYS,
    REGIME_DIMENSIONS,
    SCHEMA_VERSION,
)
from backend.nexus_probabilistic_regime_v2.engine import (
    ProbabilisticRegimeEngineV2,
    evaluate_regime,
    run_engine_campaign,
)
from backend.nexus_probabilistic_regime_v2.fixtures import (
    build_future_leak_bar,
    build_synthetic_bars,
)
from backend.nexus_probabilistic_regime_v2.hysteresis import DimensionHysteresisState
from backend.nexus_probabilistic_regime_v2.pit import filter_pit, prove_no_future_leak


# --- Pass 1: core behaviour ---


def test_all_ten_dimensions_defined() -> None:
    assert len(REGIME_DIMENSIONS) == 10
    assert "Direction" in REGIME_DIMENSIONS
    assert "Microstructure" in REGIME_DIMENSIONS


def test_required_outputs_present_on_bull() -> None:
    bars = build_synthetic_bars(scenario="strong_bull", n=32)
    out = evaluate_regime(bars, as_of_ms=int(bars[-1]["exchange_timestamp"]))
    assert out["schema_version"] == SCHEMA_VERSION
    assert out["required_outputs_present"] is True
    for key in OUTPUT_KEYS:
        assert key in out["probabilities"]
        assert 0.0 <= float(out["probabilities"][key]) <= 1.0
    assert out["pit_proof"]["pit_clean"] is True
    assert out["predictive_edge_claimed"] is False
    assert "strong_bull" not in out  # no crude single-label top-level claim


def test_strong_bull_vs_bear_directionality() -> None:
    bull_bars = build_synthetic_bars(scenario="strong_bull", n=36)
    bear_bars = build_synthetic_bars(scenario="strong_bear", n=36)
    bull = evaluate_regime(bull_bars, as_of_ms=int(bull_bars[-1]["exchange_timestamp"]))
    bear = evaluate_regime(bear_bars, as_of_ms=int(bear_bars[-1]["exchange_timestamp"]))
    assert bull["probabilities"]["strong_bull_probability"] >= bull["probabilities"]["strong_bear_probability"]
    assert bear["probabilities"]["strong_bear_probability"] >= bear["probabilities"]["strong_bull_probability"]


def test_vol_expansion_and_liquidity_stress_outputs() -> None:
    vol_bars = build_synthetic_bars(scenario="vol_expansion", n=36)
    liq_bars = build_synthetic_bars(scenario="liquidity_stress", n=36)
    vol = evaluate_regime(vol_bars, as_of_ms=int(vol_bars[-1]["exchange_timestamp"]))
    liq = evaluate_regime(liq_bars, as_of_ms=int(liq_bars[-1]["exchange_timestamp"]))
    assert vol["probabilities"]["volatility_expansion_probability"] >= 0.4
    assert liq["probabilities"]["liquidity_stress_probability"] >= 0.4


def test_long_crowding_corr_breakdown_event_risk() -> None:
    crowd_bars = build_synthetic_bars(scenario="long_crowding", n=36)
    crowd = evaluate_regime(crowd_bars, as_of_ms=int(crowd_bars[-1]["exchange_timestamp"]))
    corr_bars = build_synthetic_bars(scenario="corr_breakdown", n=36)
    corr = evaluate_regime(corr_bars, as_of_ms=int(corr_bars[-1]["exchange_timestamp"]))
    evt_bars = build_synthetic_bars(scenario="event_risk", n=36)
    evt = evaluate_regime(evt_bars, as_of_ms=int(evt_bars[-1]["exchange_timestamp"]))
    assert crowd["probabilities"]["long_crowding_probability"] >= 0.5
    assert corr["probabilities"]["correlation_breakdown_probability"] >= 0.3
    assert evt["probabilities"]["event_risk_probability"] >= 0.3


def test_pit_excludes_future_bar() -> None:
    bars = build_synthetic_bars(scenario="strong_bull", n=20)
    as_of = int(bars[-1]["exchange_timestamp"])
    bars = bars + [build_future_leak_bar(as_of)]
    eligible = filter_pit(bars, as_of_ms=as_of)
    assert len(eligible) == 20
    proof = prove_no_future_leak(eligible, as_of_ms=as_of)
    assert proof["pit_clean"] is True
    out = evaluate_regime(bars, as_of_ms=as_of)
    assert out["eligible_bar_count"] == 20
    assert out["pit_proof"]["pit_clean"] is True


def test_stale_fail_closed_unknown() -> None:
    bars = build_synthetic_bars(scenario="stale", n=20)
    as_of = int(bars[-1]["receive_timestamp"]) + 500_000
    out = evaluate_regime(bars, as_of_ms=as_of)
    assert out["formal_state"] == "UNKNOWN"
    assert out["fail_closed"] is True
    assert out["trading_unsafe"] is True
    assert out["probabilities"]["regime_confidence"] == 0.0
    assert out["probabilities"]["regime_freshness"] == 0.0


def test_hysteresis_min_dwell_blocks_flip() -> None:
    st = DimensionHysteresisState(dimension="Direction")
    r1 = st.observe(proposed_label="BULL", proposed_score=0.8, as_of_ms=1000, min_dwell_bars=3)
    assert r1["accepted"] is True
    r2 = st.observe(proposed_label="BEAR", proposed_score=0.9, as_of_ms=2000, min_dwell_bars=3)
    assert r2["accepted"] is False
    assert r2["reason"] == "MIN_DWELL_NOT_MET"
    assert st.active_label == "BULL"
    st.observe(proposed_label="BULL", proposed_score=0.8, as_of_ms=3000, min_dwell_bars=3)
    st.observe(proposed_label="BULL", proposed_score=0.8, as_of_ms=4000, min_dwell_bars=3)
    r_ok = st.observe(proposed_label="BEAR", proposed_score=0.95, as_of_ms=5000, min_dwell_bars=3)
    assert r_ok["accepted"] is True
    assert st.active_label == "BEAR"


def test_mixed_and_unknown_are_formal() -> None:
    mixed_bars = build_synthetic_bars(scenario="mixed", n=40)
    mixed = evaluate_regime(mixed_bars, as_of_ms=int(mixed_bars[-1]["exchange_timestamp"]))
    assert mixed["formal_state"] in {"MIXED", "CLEAR", "UNKNOWN"}
    empty = evaluate_regime([], as_of_ms=1_700_000_050_000)
    assert empty["formal_state"] == "UNKNOWN"
    assert empty["fail_closed"] is True


def test_calibration_interface() -> None:
    contract = calibration_contract()
    assert contract["mutates_risk_or_leverage"] is False
    assert contract["predictive_edge_claimed"] is False
    probs = {k: 0.5 for k in OUTPUT_KEYS}
    ok = apply_calibration(probs, calibrator="identity")
    assert ok["accepted"] is True
    bad = apply_calibration(probs, calibrator="undocumented")
    assert bad["accepted"] is False
    assert all(v == 0.0 for v in bad["probabilities"].values())


def test_transition_probability_in_outputs() -> None:
    eng = ProbabilisticRegimeEngineV2()
    bars = build_synthetic_bars(scenario="strong_bull", n=30)
    out = None
    for i in range(8):
        as_of = int(bars[15 + i]["exchange_timestamp"])
        out = eng.evaluate(bars, as_of_ms=as_of)
    assert out is not None
    assert "regime_transition_probability" in out["probabilities"]
    assert "regime_confidence" in out["probabilities"]
    assert "regime_freshness" in out["probabilities"]


def test_campaign_pass1_hard_bans() -> None:
    report = run_engine_campaign(pass_id=1)
    assert report["scenario_count"] == 10
    assert report["hard_ban_matrix"]["all_refused"] is True
    assert report["status_json_written"] is False
    assert set(HARD_BANS) == set(report["hard_ban_matrix"]["hard_bans"])


# --- Pass 2: adversarial ---


def test_pass2_adversarial_all_pass() -> None:
    review = run_adversarial_review()
    assert review["all_pass"] is True, review
    assert review["passed_count"] == review["finding_count"]


def test_hard_ban_matrix_complete() -> None:
    matrix = hard_ban_probe_matrix()
    assert matrix["all_refused"] is True
    assert len(matrix["probes"]) >= 15


# --- Pass 3: independent break attempts ---


def test_pass3_independent_breaks() -> None:
    result = run_independent_break_attempts()
    assert result["all_pass"] is True, result
    assert result["attempt_count"] >= 5


def test_deterministic_fingerprint() -> None:
    bars = build_synthetic_bars(scenario="event_risk", n=28)
    as_of = int(bars[-1]["exchange_timestamp"])
    a = ProbabilisticRegimeEngineV2().evaluate(bars, as_of_ms=as_of)
    b = ProbabilisticRegimeEngineV2().evaluate(bars, as_of_ms=as_of)
    assert a["fingerprint"] == b["fingerprint"]
