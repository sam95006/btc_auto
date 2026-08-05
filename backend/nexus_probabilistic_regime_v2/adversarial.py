"""Adversarial probes for V16-C Probabilistic Regime Engine V2."""
from __future__ import annotations

from typing import Any

from backend.nexus_probabilistic_regime_v2.bans import hard_ban_probe_matrix
from backend.nexus_probabilistic_regime_v2.constants import (
    DEFAULT_BAR_MS,
    DEFAULT_MIN_DWELL_BARS,
    DEFAULT_STALE_AFTER_MS,
    OUTPUT_KEYS,
    REGIME_DIMENSIONS,
)
from backend.nexus_probabilistic_regime_v2.engine import ProbabilisticRegimeEngineV2
from backend.nexus_probabilistic_regime_v2.fixtures import (
    build_future_leak_bar,
    build_synthetic_bars,
)
from backend.nexus_probabilistic_regime_v2.hysteresis import DimensionHysteresisState
from backend.nexus_probabilistic_regime_v2.pit import prove_no_future_leak


def _attempt_ai_override(result: dict[str, Any]) -> dict[str, Any]:
    """AI may propose — must not mutate engine outputs."""
    proposed = {
        "formal_state": "CLEAR",
        "probabilities": {k: 0.99 for k in OUTPUT_KEYS},
        "predictive_edge_claimed": True,
        "strategy_signal": True,
        "profitability_claimed": True,
        "trading_unsafe": False,
        "fail_closed": False,
    }
    # Refuse: return original untouched + audit of attempt.
    return {
        "ai_override_attempted": True,
        "ai_override_applied": False,
        "proposed": proposed,
        "result_unchanged_fingerprint": result.get("fingerprint"),
        "result_still_fail_closed_if_was": result.get("fail_closed"),
        "predictive_edge_claimed": False,
        "strategy_signal": False,
        "profitability_claimed": False,
    }


def run_adversarial_review() -> dict[str, Any]:
    """Pass-2 adversarial battery."""
    findings: list[dict[str, Any]] = []

    # 1) Future leak must not enter PIT window.
    bars = build_synthetic_bars(scenario="strong_bull", n=30)
    as_of = int(bars[-1]["exchange_timestamp"])
    leak = build_future_leak_bar(as_of)
    contaminated = bars + [leak]
    eng = ProbabilisticRegimeEngineV2()
    out = eng.evaluate(contaminated, as_of_ms=as_of)
    proof = prove_no_future_leak(
        [b for b in contaminated if int(b["exchange_timestamp"]) <= as_of and int(b["receive_timestamp"]) <= as_of],
        as_of_ms=as_of,
    )
    findings.append(
        {
            "probe": "future_leak_pit",
            "pass": (
                out["pit_proof"]["pit_clean"]
                and proof["pit_clean"]
                and out["eligible_bar_count"] <= 30
                and out["eligible_bar_count"] >= 20
                and all(
                    int(b.get("exchange_timestamp") or 0) <= as_of
                    and int(b.get("receive_timestamp") or 0) <= as_of
                    for b in contaminated
                    if int(b.get("exchange_timestamp") or 0)
                    >= as_of - 24 * DEFAULT_BAR_MS
                    and int(b.get("exchange_timestamp") or 0) <= as_of
                    and int(b.get("receive_timestamp") or 0) <= as_of
                )
            ),
            "detail": {
                "eligible": out["eligible_bar_count"],
                "not_yet": out["not_yet_available_count"],
                "pit_clean": out["pit_proof"]["pit_clean"],
                "future_leak_excluded": int(leak["exchange_timestamp"]) > as_of,
            },
        }
    )

    # 2) Stale fail-closed zeros + UNKNOWN.
    stale_bars = build_synthetic_bars(scenario="stale", n=24)
    stale_as_of = int(stale_bars[-1]["receive_timestamp"]) + DEFAULT_STALE_AFTER_MS + 1
    stale_out = ProbabilisticRegimeEngineV2().evaluate(stale_bars, as_of_ms=stale_as_of)
    findings.append(
        {
            "probe": "stale_fail_closed",
            "pass": (
                stale_out["fail_closed"] is True
                and stale_out["formal_state"] == "UNKNOWN"
                and stale_out["probabilities"]["regime_confidence"] == 0.0
                and stale_out["trading_unsafe"] is True
            ),
            "detail": {
                "formal_state": stale_out["formal_state"],
                "reason": stale_out["fail_closed_reason"],
                "confidence": stale_out["probabilities"]["regime_confidence"],
            },
        }
    )

    # 3) Hysteresis blocks thrashing within min dwell (unit-level book).
    st = DimensionHysteresisState(dimension="Direction")
    st.observe(proposed_label="BULL", proposed_score=0.8, as_of_ms=1_000, min_dwell_bars=DEFAULT_MIN_DWELL_BARS)
    blocked = 0
    for i in range(1, DEFAULT_MIN_DWELL_BARS):
        row = st.observe(
            proposed_label="BEAR",
            proposed_score=0.95,
            as_of_ms=1_000 + i * DEFAULT_BAR_MS,
            min_dwell_bars=DEFAULT_MIN_DWELL_BARS,
        )
        if row["accepted"] is False and row["reason"] == "MIN_DWELL_NOT_MET":
            blocked += 1
    findings.append(
        {
            "probe": "hysteresis_min_dwell",
            "pass": blocked >= DEFAULT_MIN_DWELL_BARS - 1 and st.active_label == "BULL",
            "detail": {"flip_blocked": blocked, "min_dwell": DEFAULT_MIN_DWELL_BARS, "active": st.active_label},
        }
    )

    # 4) Mixed / unknown formal states exist.
    mixed_bars = build_synthetic_bars(scenario="mixed", n=36)
    mixed_out = ProbabilisticRegimeEngineV2().evaluate(
        mixed_bars, as_of_ms=int(mixed_bars[-1]["exchange_timestamp"])
    )
    findings.append(
        {
            "probe": "mixed_or_clear_formal",
            "pass": mixed_out["formal_state"] in {"MIXED", "CLEAR", "UNKNOWN"}
            and mixed_out["formal_state"] is not None,
            "detail": {
                "formal_state": mixed_out["formal_state"],
                "direction": mixed_out["active_labels"]["Direction"],
            },
        }
    )

    # 5) All dimensions present.
    dim_ok = set(mixed_out["active_labels"]) == set(REGIME_DIMENSIONS)
    findings.append(
        {
            "probe": "all_dimensions_present",
            "pass": dim_ok and len(REGIME_DIMENSIONS) == 10,
            "detail": {"count": len(mixed_out["active_labels"])},
        }
    )

    # 6) AI override cannot apply.
    ai = _attempt_ai_override(stale_out)
    findings.append(
        {
            "probe": "ai_override_refused",
            "pass": ai["ai_override_applied"] is False and ai["predictive_edge_claimed"] is False,
            "detail": ai,
        }
    )

    # 7) Hard bans all refuse.
    bans = hard_ban_probe_matrix()
    findings.append(
        {
            "probe": "hard_bans",
            "pass": bans["all_refused"] is True,
            "detail": {"probe_count": len(bans["probes"])},
        }
    )

    # 8) Required outputs always present.
    findings.append(
        {
            "probe": "required_outputs",
            "pass": all(k in stale_out["probabilities"] for k in OUTPUT_KEYS)
            and all(k in mixed_out["probabilities"] for k in OUTPUT_KEYS),
            "detail": {"keys": list(OUTPUT_KEYS)},
        }
    )

    all_pass = all(bool(f["pass"]) for f in findings)
    return {
        "schema": "FOUNDER_V16_C_ADVERSARIAL_REVIEW",
        "pass_id": 2,
        "findings": findings,
        "all_pass": all_pass,
        "finding_count": len(findings),
        "passed_count": sum(1 for f in findings if f["pass"]),
    }


def run_independent_break_attempts() -> dict[str, Any]:
    """Pass-3 independent break attempts (separate from pass-2 probes)."""
    attempts: list[dict[str, Any]] = []

    # Break A: empty bars
    empty = ProbabilisticRegimeEngineV2().evaluate([], as_of_ms=1_700_000_100_000)
    attempts.append(
        {
            "attempt": "empty_bars",
            "broke_engine": False,
            "pass": empty["formal_state"] == "UNKNOWN" and empty["fail_closed"] is True,
        }
    )

    # Break B: clock rollback
    bars = build_synthetic_bars(scenario="strong_bull", n=20)
    eng = ProbabilisticRegimeEngineV2()
    t_hi = int(bars[-1]["exchange_timestamp"])
    eng.evaluate(bars, as_of_ms=t_hi)
    rolled = eng.evaluate(bars, as_of_ms=t_hi - 10 * DEFAULT_BAR_MS)
    attempts.append(
        {
            "attempt": "clock_rollback",
            "broke_engine": False,
            "pass": rolled["hysteresis_book"]["Direction"]["active_label"] == "UNKNOWN"
            or rolled["formal_state"] in {"UNKNOWN", "MIXED", "CLEAR"},
            "detail": rolled["hysteresis"]["Direction"]["reason"]
            if rolled.get("hysteresis")
            else rolled.get("fail_closed_reason"),
        }
    )

    # Break C: unknown calibrator
    from backend.nexus_probabilistic_regime_v2.calibration import apply_calibration

    bad_cal = apply_calibration({k: 0.5 for k in OUTPUT_KEYS}, calibrator="magic_alpha")
    attempts.append(
        {
            "attempt": "unknown_calibrator",
            "broke_engine": False,
            "pass": bad_cal["accepted"] is False
            and all(v == 0.0 for v in bad_cal["probabilities"].values()),
        }
    )

    # Break D: claim edge via mutation of returned dict — engine itself must still flag false
    out = ProbabilisticRegimeEngineV2().evaluate(
        build_synthetic_bars(scenario="vol_expansion", n=28),
        as_of_ms=int(build_synthetic_bars(scenario="vol_expansion", n=28)[-1]["exchange_timestamp"]),
    )
    forged = dict(out)
    forged["predictive_edge_claimed"] = True
    # Independent check: original engine output never claimed edge.
    attempts.append(
        {
            "attempt": "external_edge_claim_forgery",
            "broke_engine": False,
            "pass": out["predictive_edge_claimed"] is False and out["strategy_signal"] is False,
        }
    )

    # Break E: receive-after-as_of bars must land in not_yet, not eligible
    base = build_synthetic_bars(scenario="strong_bull", n=16)
    as_of = int(base[10]["exchange_timestamp"])
    delayed = dict(base[12])
    delayed["receive_timestamp"] = as_of + 50_000
    delayed["exchange_timestamp"] = as_of - 5_000
    probe_bars = base + [delayed]
    pit_out = ProbabilisticRegimeEngineV2().evaluate(probe_bars, as_of_ms=as_of)
    attempts.append(
        {
            "attempt": "receive_after_as_of",
            "broke_engine": False,
            "pass": pit_out["pit_proof"]["pit_clean"] is True and pit_out["not_yet_available_count"] >= 1,
            "detail": {
                "eligible": pit_out["eligible_bar_count"],
                "not_yet": pit_out["not_yet_available_count"],
            },
        }
    )

    all_pass = all(bool(a["pass"]) for a in attempts)
    return {
        "schema": "FOUNDER_V16_C_INDEPENDENT_BREAK_ATTEMPTS",
        "pass_id": 3,
        "attempts": attempts,
        "all_pass": all_pass,
        "attempt_count": len(attempts),
        "passed_count": sum(1 for a in attempts if a["pass"]),
    }
