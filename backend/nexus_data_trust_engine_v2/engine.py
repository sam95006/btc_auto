"""Core Data Quality and Trust Engine V2 (fail-closed).

Data Trust dominates AI confidence: DEGRADED/STALE/CONFLICTED/
LICENSE_BLOCKED/UNAVAILABLE ⇒ WAIT/ABSTAIN/BLOCK even if AI=99%.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_data_trust_engine_v2.constants import (
    AGREEMENT_CONFLICT_MAX,
    AGREEMENT_LIMITS_MIN,
    AGREEMENT_TRUSTED_MIN,
    ANOMALY_DEGRADED_MIN,
    ANOMALY_TRUSTED_MAX,
    CHANNEL_WEIGHTS,
    COMPLETENESS_LIMITS_MIN,
    COMPLETENESS_TRUSTED_MIN,
    COMPLETENESS_UNAVAILABLE_MAX,
    COVERAGE_DEGRADED_MAX,
    COVERAGE_LIMITS_MIN,
    COVERAGE_TRUSTED_MIN,
    DOMINANCE_TRUST_STATUSES,
    FRESHNESS_LIMITS_MIN,
    FRESHNESS_STALE_MAX,
    FRESHNESS_TRUSTED_MIN,
    GATE_SEVERITY,
    LANE,
    LICENSE_BLOCKING_STATUSES,
    MICRO_DEGRADED_MAX,
    MICRO_LIMITS_MIN,
    MICRO_TRUSTED_MIN,
    REVISION_UNCERTAINTY_DEGRADED_MIN,
    REVISION_UNCERTAINTY_TRUSTED_MAX,
    SCHEMA,
    SCHEMA_DEGRADED_MAX,
    SCHEMA_TRUSTED_MIN,
    TIMESTAMP_DEGRADED_MAX,
    TIMESTAMP_TRUSTED_MIN,
    TRUST_SEVERITY,
    TRUST_STATUSES,
)
from backend.nexus_data_trust_engine_v2.hard_bans import refuse_ai_confidence_override
from backend.nexus_data_trust_engine_v2.parser import ParseFailure, parse_trust_inputs


def _worse_trust(a: str, b: str) -> str:
    return a if TRUST_SEVERITY[a] >= TRUST_SEVERITY[b] else b


def _worse_gate(a: str, b: str) -> str:
    return a if GATE_SEVERITY[a] >= GATE_SEVERITY[b] else b


def _reason(code: str, detail: str | None = None) -> dict[str, str]:
    return {"code": code, "detail": detail or code}


def _channel_contribution(inputs: dict[str, Any]) -> dict[str, float]:
    """Per-channel quality contribution in [0,1] (higher = better)."""
    return {
        "freshness": float(inputs["freshness"]),
        "completeness": float(inputs["completeness"]),
        "cross_source_agreement": float(inputs["cross_source_agreement"]),
        "schema_validity": float(inputs["schema_validity"]),
        "timestamp_integrity": float(inputs["timestamp_integrity"]),
        "revision_uncertainty": 1.0 - float(inputs["revision_uncertainty"]),
        "market_coverage": float(inputs["market_coverage"]),
        "microstructure_availability": float(inputs["microstructure_availability"]),
        "anomaly_rate": 1.0 - float(inputs["anomaly_rate"]),
    }


def compute_trust_score(inputs: dict[str, Any]) -> float:
    contrib = _channel_contribution(inputs)
    score = 0.0
    for key, weight in CHANNEL_WEIGHTS.items():
        score += weight * contrib[key]
    return round(min(1.0, max(0.0, score)), 6)


def _map_trust_to_gate(trust_status: str, *, severe_degraded: bool) -> str:
    """Map trust status → gated posture. Dominance statuses never ALLOW."""
    if trust_status == "TRUSTED":
        return "ALLOW"
    if trust_status == "USABLE_WITH_LIMITS":
        return "ALLOW_REDUCED"
    if trust_status == "DEGRADED":
        return "ABSTAIN" if severe_degraded else "WAIT"
    if trust_status == "STALE":
        return "BLOCK"
    if trust_status == "CONFLICTED":
        return "ABSTAIN"
    if trust_status == "LICENSE_BLOCKED":
        return "BLOCK"
    if trust_status == "UNAVAILABLE":
        return "BLOCK"
    return "BLOCK"


def evaluate_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Deterministic trust evaluation from normalized inputs."""
    reasons: list[dict[str, str]] = []
    trust_status = "TRUSTED"
    degraded_hits = 0

    availability = bool(inputs.get("availability", True))
    if not availability:
        trust_status = _worse_trust(trust_status, "UNAVAILABLE")
        reasons.append(_reason("AVAILABILITY_FALSE"))

    license_status = str(inputs["license_status"])
    if license_status in LICENSE_BLOCKING_STATUSES:
        trust_status = _worse_trust(trust_status, "LICENSE_BLOCKED")
        reasons.append(
            _reason(
                "LICENSE_BLOCKED",
                f"license_status={license_status}",
            )
        )

    freshness = float(inputs["freshness"])
    if freshness < FRESHNESS_STALE_MAX:
        trust_status = _worse_trust(trust_status, "STALE")
        reasons.append(_reason("STALE_FRESHNESS", f"freshness={freshness:.3f}"))
    elif freshness < FRESHNESS_LIMITS_MIN:
        trust_status = _worse_trust(trust_status, "DEGRADED")
        degraded_hits += 1
        reasons.append(_reason("FRESHNESS_DEGRADED", f"freshness={freshness:.3f}"))
    elif freshness < FRESHNESS_TRUSTED_MIN:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(_reason("FRESHNESS_LIMITS", f"freshness={freshness:.3f}"))

    completeness = float(inputs["completeness"])
    if completeness <= COMPLETENESS_UNAVAILABLE_MAX:
        trust_status = _worse_trust(trust_status, "UNAVAILABLE")
        reasons.append(_reason("COMPLETENESS_UNAVAILABLE", f"completeness={completeness:.3f}"))
    elif completeness < COMPLETENESS_LIMITS_MIN:
        trust_status = _worse_trust(trust_status, "DEGRADED")
        degraded_hits += 1
        reasons.append(_reason("COMPLETENESS_DEGRADED", f"completeness={completeness:.3f}"))
    elif completeness < COMPLETENESS_TRUSTED_MIN:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(_reason("COMPLETENESS_LIMITS", f"completeness={completeness:.3f}"))

    agreement = float(inputs["cross_source_agreement"])
    if agreement < AGREEMENT_CONFLICT_MAX:
        trust_status = _worse_trust(trust_status, "CONFLICTED")
        reasons.append(_reason("CROSS_SOURCE_CONFLICT", f"agreement={agreement:.3f}"))
    elif agreement < AGREEMENT_LIMITS_MIN:
        trust_status = _worse_trust(trust_status, "DEGRADED")
        degraded_hits += 1
        reasons.append(_reason("AGREEMENT_DEGRADED", f"agreement={agreement:.3f}"))
    elif agreement < AGREEMENT_TRUSTED_MIN:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(_reason("AGREEMENT_LIMITS", f"agreement={agreement:.3f}"))

    schema_v = float(inputs["schema_validity"])
    if schema_v < SCHEMA_DEGRADED_MAX:
        trust_status = _worse_trust(trust_status, "DEGRADED")
        degraded_hits += 1
        reasons.append(_reason("SCHEMA_INVALID", f"schema_validity={schema_v:.3f}"))
    elif schema_v < SCHEMA_TRUSTED_MIN:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(_reason("SCHEMA_LIMITS", f"schema_validity={schema_v:.3f}"))

    ts_integrity = float(inputs["timestamp_integrity"])
    if ts_integrity < TIMESTAMP_DEGRADED_MAX:
        trust_status = _worse_trust(trust_status, "DEGRADED")
        degraded_hits += 1
        reasons.append(
            _reason("TIMESTAMP_INTEGRITY_FAILED", f"timestamp_integrity={ts_integrity:.3f}")
        )
    elif ts_integrity < TIMESTAMP_TRUSTED_MIN:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(
            _reason("TIMESTAMP_INTEGRITY_LIMITS", f"timestamp_integrity={ts_integrity:.3f}")
        )

    revision_u = float(inputs["revision_uncertainty"])
    if revision_u >= REVISION_UNCERTAINTY_DEGRADED_MIN:
        trust_status = _worse_trust(trust_status, "DEGRADED")
        degraded_hits += 1
        reasons.append(
            _reason("REVISION_UNCERTAINTY_HIGH", f"revision_uncertainty={revision_u:.3f}")
        )
    elif revision_u > REVISION_UNCERTAINTY_TRUSTED_MAX:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(
            _reason("REVISION_UNCERTAINTY_LIMITS", f"revision_uncertainty={revision_u:.3f}")
        )

    coverage = float(inputs["market_coverage"])
    if coverage <= COVERAGE_DEGRADED_MAX:
        trust_status = _worse_trust(trust_status, "DEGRADED")
        degraded_hits += 1
        reasons.append(_reason("MARKET_COVERAGE_LOW", f"market_coverage={coverage:.3f}"))
    elif coverage < COVERAGE_LIMITS_MIN:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(_reason("MARKET_COVERAGE_LIMITS", f"market_coverage={coverage:.3f}"))
    elif coverage < COVERAGE_TRUSTED_MIN:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(_reason("MARKET_COVERAGE_LIMITS", f"market_coverage={coverage:.3f}"))

    micro = float(inputs["microstructure_availability"])
    if micro <= MICRO_DEGRADED_MAX:
        trust_status = _worse_trust(trust_status, "DEGRADED")
        degraded_hits += 1
        reasons.append(
            _reason("MICROSTRUCTURE_UNAVAILABLE", f"microstructure_availability={micro:.3f}")
        )
    elif micro < MICRO_LIMITS_MIN:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(
            _reason("MICROSTRUCTURE_LIMITS", f"microstructure_availability={micro:.3f}")
        )
    elif micro < MICRO_TRUSTED_MIN:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(
            _reason("MICROSTRUCTURE_LIMITS", f"microstructure_availability={micro:.3f}")
        )

    anomaly = float(inputs["anomaly_rate"])
    if anomaly >= ANOMALY_DEGRADED_MIN:
        trust_status = _worse_trust(trust_status, "DEGRADED")
        degraded_hits += 1
        reasons.append(_reason("ANOMALY_RATE_HIGH", f"anomaly_rate={anomaly:.3f}"))
    elif anomaly > ANOMALY_TRUSTED_MAX:
        trust_status = _worse_trust(trust_status, "USABLE_WITH_LIMITS")
        reasons.append(_reason("ANOMALY_RATE_LIMITS", f"anomaly_rate={anomaly:.3f}"))

    if trust_status == "TRUSTED" and not reasons:
        reasons.append(_reason("ALL_TRUST_GATES_PASSED"))

    assert trust_status in TRUST_STATUSES

    severe_degraded = degraded_hits >= 3
    gate_action = _map_trust_to_gate(trust_status, severe_degraded=severe_degraded)

    ai_confidence = inputs.get("ai_confidence")
    dominance_applied = False
    dominance_refusal: dict[str, Any] | None = None

    # Data Trust dominates AI confidence.
    if trust_status in DOMINANCE_TRUST_STATUSES:
        if gate_action in {"ALLOW", "ALLOW_REDUCED"}:
            gate_action = "WAIT"
        if ai_confidence is not None and float(ai_confidence) >= 0.99:
            dominance_applied = True
            dominance_refusal = refuse_ai_confidence_override(
                trust_status=trust_status,
                ai_confidence=float(ai_confidence),
            )
            reasons.append(
                _reason(
                    "TRUST_DOMINATES_AI_CONFIDENCE",
                    f"trust={trust_status} ai_confidence={float(ai_confidence):.3f} "
                    f"gate={gate_action}",
                )
            )
        elif ai_confidence is not None:
            dominance_applied = True
            reasons.append(
                _reason(
                    "TRUST_DOMINATES_AI_CONFIDENCE",
                    f"trust={trust_status} ai_confidence={float(ai_confidence):.3f} "
                    f"gate={gate_action}",
                )
            )

    # Invariant: dominance statuses never allow execution.
    if trust_status in DOMINANCE_TRUST_STATUSES:
        assert gate_action in {"WAIT", "ABSTAIN", "BLOCK"}
        gate_action = _worse_gate(gate_action, "WAIT")

    trust_score = compute_trust_score(inputs)
    execution_allowed = gate_action in {"ALLOW", "ALLOW_REDUCED"}

    return {
        "schema": SCHEMA,
        "lane": LANE,
        "trust_status": trust_status,
        "trust_score": trust_score,
        "gate_action": gate_action,
        "size_multiplier": 1.0
        if gate_action == "ALLOW"
        else (0.5 if gate_action == "ALLOW_REDUCED" else 0.0),
        "reasons": reasons,
        "channels": {
            "freshness": freshness,
            "completeness": completeness,
            "cross_source_agreement": agreement,
            "schema_validity": schema_v,
            "timestamp_integrity": ts_integrity,
            "revision_uncertainty": revision_u,
            "license_status": license_status,
            "market_coverage": coverage,
            "microstructure_availability": micro,
            "anomaly_rate": anomaly,
        },
        "ai_confidence": ai_confidence,
        "dominance_applied": dominance_applied,
        "dominance_refusal": dominance_refusal,
        "license_blocked": trust_status == "LICENSE_BLOCKED"
        or license_status in LICENSE_BLOCKING_STATUSES,
        "execution_allowed": execution_allowed,
        "fail_closed": True,
        "case_id": inputs.get("case_id"),
        "symbol": inputs.get("symbol"),
        "source_id": inputs.get("source_id"),
        "ai_override_applied": False,
    }


def evaluate_raw(raw: Any) -> dict[str, Any]:
    """Parse then evaluate. Parse failures → UNAVAILABLE / BLOCK (never TRUSTED)."""
    try:
        inputs = parse_trust_inputs(raw)
    except ParseFailure as exc:
        return {
            "schema": SCHEMA,
            "lane": LANE,
            "trust_status": "UNAVAILABLE",
            "trust_score": 0.0,
            "gate_action": "BLOCK",
            "size_multiplier": 0.0,
            "reasons": [_reason(exc.reason, exc.detail)],
            "channels": None,
            "ai_confidence": None,
            "dominance_applied": True,
            "dominance_refusal": refuse_ai_confidence_override(
                trust_status="UNAVAILABLE",
                ai_confidence=1.0,
            ),
            "license_blocked": False,
            "execution_allowed": False,
            "fail_closed": True,
            "case_id": None,
            "symbol": None,
            "source_id": None,
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
    """AI cannot upgrade trust_status or reopen a blocked/degraded gate."""
    out = deepcopy(decision)
    out["ai_override_applied"] = False
    if not suggestion:
        out["ai_override_attempted"] = False
        out["ai_override_refusal"] = None
        return out

    protected = {
        "trust_status",
        "trust_score",
        "gate_action",
        "size_multiplier",
        "execution_allowed",
        "fail_closed",
        "reasons",
        "license_blocked",
        "dominance_applied",
    }
    attempted = [k for k in suggestion if k in protected]
    if attempted:
        out["ai_override_attempted"] = True
        trust = str(out.get("trust_status") or "UNAVAILABLE")
        conf = suggestion.get("ai_confidence", out.get("ai_confidence") or 0.99)
        try:
            conf_f = float(conf)
        except (TypeError, ValueError):
            conf_f = 0.99
        out["ai_override_refusal"] = refuse_ai_confidence_override(
            trust_status=trust,
            ai_confidence=conf_f,
        )
        return out

    out["ai_override_attempted"] = False
    out["ai_override_refusal"] = None
    out["ai_annotation"] = {k: v for k, v in suggestion.items() if k not in protected}
    return out
