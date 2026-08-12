"""V16-C Probabilistic Regime Engine V2 — core evaluate path."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_probabilistic_regime_v2.bans import (
    default_control_flags,
    hard_ban_probe_matrix,
)
from backend.nexus_probabilistic_regime_v2.calibration import apply_calibration
from backend.nexus_probabilistic_regime_v2.constants import (
    BASE_COMMIT,
    BRANCH,
    CALIBRATION_INTERFACE_VERSION,
    DEFAULT_BAR_MS,
    DEFAULT_HYSTERESIS_MARGIN,
    DEFAULT_LOOKBACK_BARS,
    DEFAULT_MIN_DWELL_BARS,
    DEFAULT_STALE_AFTER_MS,
    DEFAULT_TRANSITION_LOOKBACK,
    HARD_BANS,
    LANE,
    LANE_NAME,
    NON_CLAIMS,
    OUTPUT_KEYS,
    OWNED_PATHS,
    REGIME_DIMENSIONS,
    SCHEMA,
    SCHEMA_VERSION,
)
from backend.nexus_probabilistic_regime_v2.dimensions import score_dimensions
from backend.nexus_probabilistic_regime_v2.hysteresis import HysteresisBook
from backend.nexus_probabilistic_regime_v2.pit import (
    filter_pit_lookback,
    freshness_score,
    prove_no_future_leak,
)
from backend.nexus_probabilistic_regime_v2.transitions import estimate_transition_probability


def _fail_closed_outputs() -> dict[str, float]:
    return {k: 0.0 for k in OUTPUT_KEYS}


def _aggregate_outputs(dim_scores: dict[str, dict[str, Any]]) -> dict[str, float]:
    d = dim_scores
    return {
        "strong_bull_probability": float(
            d["Direction"].get("strong_bull_probability", 0.0)
        ),
        "strong_bear_probability": float(
            d["Direction"].get("strong_bear_probability", 0.0)
        ),
        "volatility_expansion_probability": float(
            d["Volatility"].get("volatility_expansion_probability", 0.0)
        ),
        "liquidity_stress_probability": float(
            d["Liquidity"].get("liquidity_stress_probability", 0.0)
        ),
        "long_crowding_probability": float(
            d["LeverageCrowding"].get("long_crowding_probability", 0.0)
        ),
        "correlation_breakdown_probability": float(
            d["CrossAssetCorrelation"].get("correlation_breakdown_probability", 0.0)
        ),
        "event_risk_probability": float(
            d["EventRisk"].get("event_risk_probability", 0.0)
        ),
        "regime_transition_probability": 0.0,  # filled by transition detector
        "regime_confidence": 0.0,  # filled later
        "regime_freshness": 0.0,  # filled later
    }


def _formal_state(dim_labels: dict[str, str]) -> str:
    labels = list(dim_labels.values())
    if not labels or all(x == "UNKNOWN" for x in labels):
        return "UNKNOWN"
    if any(x == "UNKNOWN" for x in labels) or any(x == "MIXED" for x in labels):
        if sum(1 for x in labels if x in {"UNKNOWN", "MIXED"}) >= max(2, len(labels) // 3):
            return "MIXED" if any(x == "MIXED" for x in labels) else "UNKNOWN"
        return "MIXED"
    # Conflicting bull/bear with other stress → MIXED
    if dim_labels.get("Direction") == "MIXED":
        return "MIXED"
    return "CLEAR"


def _confidence(
    *,
    formal_state: str,
    freshness: float,
    dim_scores: dict[str, dict[str, Any]],
    stale: bool,
) -> float:
    if stale or formal_state == "UNKNOWN":
        return 0.0
    scores = [float(v.get("score") or 0.0) for v in dim_scores.values()]
    mean_score = sum(scores) / len(scores) if scores else 0.0
    base = 0.55 * mean_score + 0.45 * freshness
    if formal_state == "MIXED":
        base *= 0.55
    return round(max(0.0, min(1.0, base)), 6)


class ProbabilisticRegimeEngineV2:
    """Stateful multi-dimensional probabilistic regime engine."""

    def __init__(
        self,
        *,
        min_dwell_bars: int = DEFAULT_MIN_DWELL_BARS,
        hysteresis_margin: float = DEFAULT_HYSTERESIS_MARGIN,
        stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
        lookback_bars: int = DEFAULT_LOOKBACK_BARS,
        bar_ms: int = DEFAULT_BAR_MS,
    ) -> None:
        self.min_dwell_bars = min_dwell_bars
        self.hysteresis_margin = hysteresis_margin
        self.stale_after_ms = stale_after_ms
        self.lookback_bars = lookback_bars
        self.bar_ms = bar_ms
        self.book = HysteresisBook()
        self._direction_label_history: list[str] = []

    def evaluate(
        self,
        bars: list[dict[str, Any]],
        *,
        as_of_ms: int,
        symbol: str = "BTCUSDT",
    ) -> dict[str, Any]:
        lookback_start = as_of_ms - self.lookback_bars * self.bar_ms
        eligible, not_yet = filter_pit_lookback(
            [b for b in bars if b.get("symbol") == symbol],
            as_of_ms=as_of_ms,
            lookback_start_ms=lookback_start,
        )
        pit_proof = prove_no_future_leak(eligible, as_of_ms=as_of_ms)
        available_at = (
            max(int(b["receive_timestamp"]) for b in eligible) if eligible else None
        )
        fresh, stale, staleness_ms = freshness_score(
            as_of_ms=as_of_ms,
            available_at_ms=available_at,
            stale_after_ms=self.stale_after_ms,
        )

        # Stale / empty → formal UNKNOWN fail-closed.
        if stale or not eligible:
            if not eligible:
                reason = "NO_ELIGIBLE_BARS_FAIL_CLOSED"
            else:
                reason = "STALE_DATA_FAIL_CLOSED"
            raw = _fail_closed_outputs()
            cal = apply_calibration({k: float(raw[k]) for k in OUTPUT_KEYS})
            dim_labels = {d: "UNKNOWN" for d in REGIME_DIMENSIONS}
            for dim in REGIME_DIMENSIONS:
                self.book.state_for(dim).observe(
                    proposed_label="UNKNOWN",
                    proposed_score=0.0,
                    as_of_ms=as_of_ms,
                    min_dwell_bars=self.min_dwell_bars,
                    hysteresis_margin=self.hysteresis_margin,
                )
            self._direction_label_history.append("UNKNOWN")
            trans = estimate_transition_probability(
                self._direction_label_history,
                lookback=DEFAULT_TRANSITION_LOOKBACK,
            )
            cal["probabilities"]["regime_transition_probability"] = float(
                trans["regime_transition_probability"]
            )
            return self._package(
                symbol=symbol,
                as_of_ms=as_of_ms,
                lookback_start=lookback_start,
                eligible=eligible,
                not_yet=not_yet,
                pit_proof=pit_proof,
                fresh=0.0,
                stale=True if stale else False,
                staleness_ms=staleness_ms,
                dim_scores={d: {"label": "UNKNOWN", "score": 0.0} for d in REGIME_DIMENSIONS},
                dim_labels=dim_labels,
                hysteresis={},
                formal_state="UNKNOWN",
                calibrated=cal,
                transition=trans,
                fail_closed=True,
                fail_closed_reason=reason,
                trading_unsafe=True,
            )

        dim_scores = score_dimensions(eligible)
        hysteresis_rows: dict[str, Any] = {}
        dim_labels: dict[str, str] = {}
        for dim in REGIME_DIMENSIONS:
            proposed = str(dim_scores[dim]["label"])
            score = float(dim_scores[dim].get("score") or 0.0)
            row = self.book.state_for(dim).observe(
                proposed_label=proposed,
                proposed_score=score,
                as_of_ms=as_of_ms,
                min_dwell_bars=self.min_dwell_bars,
                hysteresis_margin=self.hysteresis_margin,
            )
            hysteresis_rows[dim] = row
            dim_labels[dim] = row["active_label"]
            # Reflect active label back into scores for consumers.
            dim_scores[dim]["active_label"] = row["active_label"]
            dim_scores[dim]["hysteresis_accepted"] = row["accepted"]

        self._direction_label_history.append(dim_labels["Direction"])
        trans = estimate_transition_probability(
            self._direction_label_history,
            lookback=DEFAULT_TRANSITION_LOOKBACK,
        )

        formal = _formal_state(dim_labels)
        # If hysteresis forced mixed/unknown labels, escalate.
        if any(v == "UNKNOWN" for v in dim_labels.values()) and formal == "CLEAR":
            formal = "MIXED"

        raw = _aggregate_outputs(dim_scores)
        raw["regime_transition_probability"] = float(trans["regime_transition_probability"])
        raw["regime_freshness"] = float(fresh)
        conf = _confidence(
            formal_state=formal,
            freshness=fresh,
            dim_scores=dim_scores,
            stale=False,
        )
        raw["regime_confidence"] = conf
        if formal == "UNKNOWN":
            for k in OUTPUT_KEYS:
                if k not in {"regime_freshness", "regime_confidence", "regime_transition_probability"}:
                    raw[k] = 0.0
            raw["regime_confidence"] = 0.0

        cal = apply_calibration({k: float(raw[k]) for k in OUTPUT_KEYS})
        return self._package(
            symbol=symbol,
            as_of_ms=as_of_ms,
            lookback_start=lookback_start,
            eligible=eligible,
            not_yet=not_yet,
            pit_proof=pit_proof,
            fresh=fresh,
            stale=False,
            staleness_ms=staleness_ms,
            dim_scores=dim_scores,
            dim_labels=dim_labels,
            hysteresis=hysteresis_rows,
            formal_state=formal,
            calibrated=cal,
            transition=trans,
            fail_closed=formal == "UNKNOWN",
            fail_closed_reason=None if formal != "UNKNOWN" else "FORMAL_UNKNOWN",
            trading_unsafe=formal in {"UNKNOWN", "MIXED"} or conf < 0.25,
        )

    def _package(self, **kwargs: Any) -> dict[str, Any]:
        cal = kwargs["calibrated"]
        probs = cal["probabilities"]
        for k in OUTPUT_KEYS:
            assert k in probs
        payload = {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "lane": LANE,
            "lane_name": LANE_NAME,
            "branch": BRANCH,
            "base_sha": BASE_COMMIT,
            "symbol": kwargs["symbol"],
            "as_of_ms": kwargs["as_of_ms"],
            "lookback_start_ms": kwargs["lookback_start"],
            "lookback_end_ms": kwargs["as_of_ms"],
            "eligible_bar_count": len(kwargs["eligible"]),
            "not_yet_available_count": len(kwargs["not_yet"]),
            "pit_proof": kwargs["pit_proof"],
            "regime_freshness": probs["regime_freshness"],
            "regime_confidence": probs["regime_confidence"],
            "staleness_ms": kwargs["staleness_ms"],
            "stale": kwargs["stale"],
            "stale_after_ms": self.stale_after_ms,
            "formal_state": kwargs["formal_state"],
            "dimensions": kwargs["dim_scores"],
            "active_labels": kwargs["dim_labels"],
            "hysteresis": kwargs["hysteresis"],
            "hysteresis_book": self.book.snapshot(),
            "transition": kwargs["transition"],
            "probabilities": probs,
            "calibration": {
                "accepted": cal["accepted"],
                "calibrator": cal["calibrator"],
                "interface_version": CALIBRATION_INTERFACE_VERSION,
            },
            "fail_closed": kwargs["fail_closed"],
            "fail_closed_reason": kwargs["fail_closed_reason"],
            "trading_unsafe": kwargs["trading_unsafe"],
            "required_outputs_present": all(k in probs for k in OUTPUT_KEYS),
            "regime_dimensions": list(REGIME_DIMENSIONS),
            "non_claims": list(NON_CLAIMS),
            "hard_bans": sorted(HARD_BANS),
            "control_flags": default_control_flags(),
            "predictive_edge_claimed": False,
            "strategy_signal": False,
            "profitability_claimed": False,
            "contemporaneous_only": True,
        }
        payload["fingerprint"] = _fingerprint(payload)
        return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    slim = {
        "schema_version": payload["schema_version"],
        "as_of_ms": payload["as_of_ms"],
        "symbol": payload["symbol"],
        "formal_state": payload["formal_state"],
        "active_labels": payload["active_labels"],
        "probabilities": payload["probabilities"],
        "fail_closed": payload["fail_closed"],
        "pit_clean": payload["pit_proof"]["pit_clean"],
    }
    blob = json.dumps(slim, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def evaluate_regime(
    bars: list[dict[str, Any]],
    *,
    as_of_ms: int,
    symbol: str = "BTCUSDT",
    engine: ProbabilisticRegimeEngineV2 | None = None,
) -> dict[str, Any]:
    eng = engine or ProbabilisticRegimeEngineV2()
    return eng.evaluate(bars, as_of_ms=as_of_ms, symbol=symbol)


def run_engine_campaign(*, pass_id: int = 1) -> dict[str, Any]:
    """Deterministic multi-scenario campaign for pass evidence (no status JSON)."""
    from backend.nexus_probabilistic_regime_v2.fixtures import build_synthetic_bars

    if pass_id not in (1, 2, 3):
        raise ValueError("pass_id must be 1, 2, or 3")

    scenarios = (
        "strong_bull",
        "strong_bear",
        "vol_expansion",
        "liquidity_stress",
        "long_crowding",
        "corr_breakdown",
        "event_risk",
        "mixed",
        "stale",
        "unknown_thin",
    )
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        bars = build_synthetic_bars(scenario=scenario, n=40)
        as_of = int(bars[-1]["exchange_timestamp"])
        if scenario == "stale":
            # Force as_of far beyond last receive → stale fail-closed.
            as_of = int(bars[-1]["receive_timestamp"]) + DEFAULT_STALE_AFTER_MS + 60_000
        eng = ProbabilisticRegimeEngineV2()
        # Multi-step for hysteresis dwell on mixed/bull path.
        for step in range(max(1, DEFAULT_MIN_DWELL_BARS + 1)):
            step_as_of = as_of - (DEFAULT_MIN_DWELL_BARS - step) * DEFAULT_BAR_MS
            if step_as_of < int(bars[0]["exchange_timestamp"]) + 5 * DEFAULT_BAR_MS:
                step_as_of = int(bars[10]["exchange_timestamp"])
            out = eng.evaluate(bars, as_of_ms=step_as_of if scenario != "stale" else as_of)
        assert out["required_outputs_present"] is True
        results.append(
            {
                "scenario": scenario,
                "formal_state": out["formal_state"],
                "fail_closed": out["fail_closed"],
                "trading_unsafe": out["trading_unsafe"],
                "probabilities": out["probabilities"],
                "active_labels": out["active_labels"],
                "pit_clean": out["pit_proof"]["pit_clean"],
                "fingerprint": out["fingerprint"],
            }
        )

    ban_matrix = hard_ban_probe_matrix()
    return {
        "schema": SCHEMA,
        "lane": LANE,
        "pass_id": pass_id,
        "branch": BRANCH,
        "base_sha": BASE_COMMIT,
        "owned_paths": list(OWNED_PATHS),
        "scenario_count": len(results),
        "scenarios": results,
        "hard_ban_matrix": ban_matrix,
        "status_json_written": False,
        "acceleration_report_edited": False,
        "non_claims": list(NON_CLAIMS),
    }
