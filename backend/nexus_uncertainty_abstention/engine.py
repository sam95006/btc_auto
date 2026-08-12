"""Core uncertainty → abstention verdict engine (fail-closed)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_uncertainty_abstention.constants import (
    AGREEMENT_ALLOW_MIN,
    AGREEMENT_CHANNELS,
    AGREEMENT_REDUCED_MIN,
    AGREEMENT_WAIT_MIN,
    CALIBRATION_ABSTAIN_MAX,
    CALIBRATION_ALLOW_MIN,
    CALIBRATION_DEGRADE_MAX_CONF,
    CONTRADICTION_GAP,
    COVERAGE_ABSTAIN_MAX,
    COVERAGE_ALLOW_MIN,
    DATA_AGREEMENT_HARD_MIN,
    FRESHNESS_ALLOW_MAX_SEC,
    FRESHNESS_STALE_SEC,
    FRESHNESS_WAIT_MAX_SEC,
    INTERVAL_ABSTAIN_MIN,
    INTERVAL_ALLOW_MAX,
    LANE,
    SCHEMA,
    VERDICT_SEVERITY,
    VERDICTS,
)
from backend.nexus_uncertainty_abstention.hard_bans import refuse_ai_override
from backend.nexus_uncertainty_abstention.parser import ParseFailure, parse_provider_payload


def _worse(a: str, b: str) -> str:
    return a if VERDICT_SEVERITY[a] >= VERDICT_SEVERITY[b] else b


def _reason(code: str, detail: str | None = None) -> dict[str, str]:
    return {"code": code, "detail": detail or code}


def evaluate_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Deterministic verdict from normalized inputs."""
    reasons: list[dict[str, str]] = []
    verdict = "ALLOW"
    size_multiplier = 1.0
    uncertainty_score = 0.0

    agreements = {k: float(inputs[k]) for k in AGREEMENT_CHANNELS}
    data_agreement = agreements["data_agreement"]
    min_agreement = min(agreements.values())
    mean_agreement = sum(agreements.values()) / len(agreements)
    # Model contradiction is among model/historical/regime — distinct from
    # risk↔execution disagreement (which is WAIT-or-worse, not auto-ABSTAIN).
    model_cluster = (
        agreements["model_agreement"],
        agreements["historical_agreement"],
        agreements["regime_agreement"],
    )
    model_gap = max(model_cluster) - min(model_cluster)
    contradiction = model_gap >= CONTRADICTION_GAP
    risk_exec_gap = abs(
        agreements["risk_agreement"] - agreements["execution_agreement"]
    )

    calibration = float(inputs["calibration_reliability"])
    coverage = float(inputs["similarity_coverage"])
    interval = float(inputs["prediction_interval_width"])
    freshness = float(inputs["data_freshness_sec"])
    confidence = float(inputs["stated_confidence"])

    # --- Hard fail-closed gates (cannot be overridden by consensus) ---
    if data_agreement < DATA_AGREEMENT_HARD_MIN:
        verdict = _worse(verdict, "ABSTAIN" if data_agreement >= 0.40 else "BLOCK")
        reasons.append(
            _reason(
                "BAD_DATA_NOT_OVERRIDABLE",
                f"data_agreement={data_agreement:.3f} below hard min "
                f"{DATA_AGREEMENT_HARD_MIN}; consensus ignored",
            )
        )
        uncertainty_score = max(uncertainty_score, 1.0 - data_agreement)

    if contradiction:
        verdict = _worse(verdict, "ABSTAIN")
        reasons.append(
            _reason(
                "MODEL_OR_CHANNEL_CONTRADICTION",
                f"model_cluster_gap={model_gap:.3f}",
            )
        )
        uncertainty_score = max(uncertainty_score, model_gap)

    if freshness >= FRESHNESS_STALE_SEC:
        verdict = _worse(verdict, "BLOCK")
        reasons.append(_reason("STALE_EVIDENCE", f"age_sec={freshness:.1f}"))
        uncertainty_score = max(uncertainty_score, 1.0)
    elif freshness > FRESHNESS_WAIT_MAX_SEC:
        verdict = _worse(verdict, "WAIT")
        reasons.append(_reason("FRESHNESS_WAIT", f"age_sec={freshness:.1f}"))
        uncertainty_score = max(uncertainty_score, 0.7)
    elif freshness > FRESHNESS_ALLOW_MAX_SEC:
        verdict = _worse(verdict, "ALLOW_REDUCED")
        reasons.append(_reason("FRESHNESS_DEGRADED", f"age_sec={freshness:.1f}"))
        size_multiplier = min(size_multiplier, 0.5)
        uncertainty_score = max(uncertainty_score, 0.4)

    # High confidence + low calibration MUST degrade (never ALLOW).
    if confidence >= CALIBRATION_DEGRADE_MAX_CONF and calibration < CALIBRATION_ALLOW_MIN:
        if calibration <= CALIBRATION_ABSTAIN_MAX:
            verdict = _worse(verdict, "ABSTAIN")
            reasons.append(
                _reason(
                    "HIGH_CONFIDENCE_LOW_CALIBRATION_ABSTAIN",
                    f"confidence={confidence:.3f} calibration={calibration:.3f}",
                )
            )
        else:
            verdict = _worse(verdict, "ALLOW_REDUCED")
            reasons.append(
                _reason(
                    "HIGH_CONFIDENCE_LOW_CALIBRATION_DEGRADE",
                    f"confidence={confidence:.3f} calibration={calibration:.3f}",
                )
            )
            size_multiplier = min(size_multiplier, 0.35)
        uncertainty_score = max(uncertainty_score, 1.0 - calibration)

    if calibration < CALIBRATION_ALLOW_MIN and confidence < CALIBRATION_DEGRADE_MAX_CONF:
        if calibration <= CALIBRATION_ABSTAIN_MAX:
            verdict = _worse(verdict, "ABSTAIN")
            reasons.append(_reason("CALIBRATION_ABSTAIN", f"calibration={calibration:.3f}"))
        else:
            verdict = _worse(verdict, "ALLOW_REDUCED")
            reasons.append(_reason("CALIBRATION_DEGRADE", f"calibration={calibration:.3f}"))
            size_multiplier = min(size_multiplier, 0.5)
        uncertainty_score = max(uncertainty_score, 1.0 - calibration)

    # Low similarity coverage ⇒ uncertainty (cannot full ALLOW).
    if coverage <= COVERAGE_ABSTAIN_MAX:
        verdict = _worse(verdict, "ABSTAIN")
        reasons.append(_reason("LOW_SIMILARITY_COVERAGE_ABSTAIN", f"coverage={coverage:.3f}"))
        uncertainty_score = max(uncertainty_score, 1.0 - coverage)
    elif coverage < COVERAGE_ALLOW_MIN:
        verdict = _worse(verdict, "ALLOW_REDUCED")
        reasons.append(_reason("LOW_SIMILARITY_COVERAGE", f"coverage={coverage:.3f}"))
        size_multiplier = min(size_multiplier, 0.5)
        uncertainty_score = max(uncertainty_score, 1.0 - coverage)

    if interval >= INTERVAL_ABSTAIN_MIN:
        verdict = _worse(verdict, "ABSTAIN")
        reasons.append(_reason("WIDE_PREDICTION_INTERVAL", f"width={interval:.3f}"))
        uncertainty_score = max(uncertainty_score, interval)
    elif interval > INTERVAL_ALLOW_MAX:
        verdict = _worse(verdict, "ALLOW_REDUCED")
        reasons.append(_reason("ELEVATED_PREDICTION_INTERVAL", f"width={interval:.3f}"))
        size_multiplier = min(size_multiplier, 0.6)
        uncertainty_score = max(uncertainty_score, interval)

    # Aggregate agreement ladder (after hard data gate).
    if min_agreement < AGREEMENT_WAIT_MIN:
        verdict = _worse(verdict, "ABSTAIN")
        reasons.append(_reason("LOW_AGREEMENT_ABSTAIN", f"min_agreement={min_agreement:.3f}"))
        uncertainty_score = max(uncertainty_score, 1.0 - min_agreement)
    elif min_agreement < AGREEMENT_REDUCED_MIN:
        verdict = _worse(verdict, "WAIT")
        reasons.append(_reason("LOW_AGREEMENT_WAIT", f"min_agreement={min_agreement:.3f}"))
        uncertainty_score = max(uncertainty_score, 1.0 - min_agreement)
    elif min_agreement < AGREEMENT_ALLOW_MIN:
        verdict = _worse(verdict, "ALLOW_REDUCED")
        reasons.append(_reason("PARTIAL_AGREEMENT", f"min_agreement={min_agreement:.3f}"))
        size_multiplier = min(size_multiplier, 0.55)
        uncertainty_score = max(uncertainty_score, 1.0 - min_agreement)

    # Risk/execution disagreement is WAIT-or-worse even if others agree.
    if risk_exec_gap >= CONTRADICTION_GAP:
        verdict = _worse(verdict, "WAIT")
        reasons.append(
            _reason("RISK_EXECUTION_DISAGREEMENT", f"gap={risk_exec_gap:.3f}")
        )
        uncertainty_score = max(uncertainty_score, 0.65)

    if verdict == "ALLOW" and not reasons:
        reasons.append(_reason("ALL_GATES_PASSED"))
        uncertainty_score = max(
            0.0,
            1.0 - mean_agreement,
            1.0 - calibration,
            1.0 - coverage,
            interval * 0.5,
        )

    if verdict == "ALLOW_REDUCED":
        size_multiplier = min(size_multiplier, 0.5)
    elif verdict in {"WAIT", "ABSTAIN", "BLOCK"}:
        size_multiplier = 0.0

    # Invariant: consensus of non-data channels cannot upgrade past bad data.
    consensus_attempted_allow = (
        mean_agreement >= AGREEMENT_ALLOW_MIN
        and data_agreement < DATA_AGREEMENT_HARD_MIN
    )
    if consensus_attempted_allow and VERDICT_SEVERITY[verdict] < VERDICT_SEVERITY["ABSTAIN"]:
        verdict = "ABSTAIN"
        reasons.append(_reason("CONSENSUS_OVERRIDE_BLOCKED"))

    assert verdict in VERDICTS

    return {
        "schema": SCHEMA,
        "lane": LANE,
        "verdict": verdict,
        "size_multiplier": round(size_multiplier, 6),
        "uncertainty_score": round(min(1.0, uncertainty_score), 6),
        "reasons": reasons,
        "agreements": agreements,
        "calibration_reliability": calibration,
        "similarity_coverage": coverage,
        "prediction_interval_width": interval,
        "data_freshness_sec": freshness,
        "stated_confidence": confidence,
        "contradiction": contradiction,
        "bad_data_blocked": data_agreement < DATA_AGREEMENT_HARD_MIN,
        "consensus_override_blocked": bool(consensus_attempted_allow),
        "provider_status": inputs.get("provider_status"),
        "symbol": inputs.get("symbol"),
        "case_id": inputs.get("case_id"),
        "execution_allowed": verdict in {"ALLOW", "ALLOW_REDUCED"},
        "fail_closed": True,
        "ai_override_applied": False,
    }


def evaluate_raw(raw: Any) -> dict[str, Any]:
    """Parse then evaluate. Provider/JSON failures → BLOCK (never ALLOW)."""
    try:
        inputs = parse_provider_payload(raw)
    except ParseFailure as exc:
        return {
            "schema": SCHEMA,
            "lane": LANE,
            "verdict": "BLOCK",
            "size_multiplier": 0.0,
            "uncertainty_score": 1.0,
            "reasons": [_reason(exc.reason, exc.detail)],
            "agreements": None,
            "calibration_reliability": None,
            "similarity_coverage": None,
            "prediction_interval_width": None,
            "data_freshness_sec": None,
            "stated_confidence": None,
            "contradiction": None,
            "bad_data_blocked": True,
            "consensus_override_blocked": False,
            "provider_status": exc.reason,
            "symbol": None,
            "case_id": None,
            "execution_allowed": False,
            "fail_closed": True,
            "ai_override_applied": False,
            "parse_failure": True,
        }
    result = evaluate_inputs(inputs)
    result["parse_failure"] = False
    return result


def apply_ai_suggestion(
    decision: dict[str, Any],
    suggestion: dict[str, Any] | None,
) -> dict[str, Any]:
    """AI cannot upgrade or mutate the abstention verdict."""
    out = deepcopy(decision)
    out["ai_override_applied"] = False
    if not suggestion:
        out["ai_override_attempted"] = False
        out["ai_override_refusal"] = None
        return out

    protected = {
        "verdict",
        "size_multiplier",
        "uncertainty_score",
        "execution_allowed",
        "fail_closed",
        "reasons",
        "bad_data_blocked",
        "consensus_override_blocked",
    }
    attempted = [k for k in suggestion if k in protected]
    if attempted:
        out["ai_override_attempted"] = True
        out["ai_override_refusal"] = refuse_ai_override(attempted_fields=attempted)
        return out

    out["ai_override_attempted"] = False
    out["ai_override_refusal"] = None
    out["ai_annotation"] = {k: v for k, v in suggestion.items() if k not in protected}
    return out
