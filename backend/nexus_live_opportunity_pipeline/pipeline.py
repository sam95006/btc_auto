"""V18-D Live Opportunity Pipeline — shadow decision orchestrator."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_data_trust_engine_v2 import apply_ai_suggestion as apply_trust_ai
from backend.nexus_data_trust_engine_v2 import evaluate_raw as evaluate_trust
from backend.nexus_decision_memory_graph import DecisionMemoryGraph
from backend.nexus_gold_feature_factory import build_synthetic_market, compute_all_features
from backend.nexus_historical_universe import reconstruct_universe
from backend.nexus_live_opportunity_pipeline.constants import (
    AS_OF_MS_DEFAULT,
    DECISION_ENUM,
    DECISION_SEVERITY,
    DEFAULT_MARKET,
    ENTRY_SIDES,
    HARD_BANS,
    LANE,
    LANE_NAME,
    MAX_COST_BPS_FEASIBLE,
    MIN_CANDIDATE_SCORE_FOR_ENTRY,
    PIPELINE_STAGES,
    REQUIRED_DECISION_FIELDS,
    SCHEMA,
    TIP_MODULES,
)
from backend.nexus_live_opportunity_pipeline.hard_bans import (
    assert_shadow_flags,
    refuse_ai_override_data_trust,
    refuse_ai_override_risk,
)
from backend.nexus_live_opportunity_pipeline.live_hooks import resolve_data_class
from backend.nexus_probabilistic_regime_v2 import build_synthetic_bars, evaluate_regime
from backend.nexus_strategy_expert_router import StrategyExpertRouter
from backend.nexus_strategy_expert_router.models import MarketContext, RegimeProbabilities
from backend.nexus_uncertainty_abstention import (
    apply_ai_suggestion as apply_abstention_ai,
)
from backend.nexus_uncertainty_abstention import evaluate_raw as evaluate_abstention


def _sha(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _worse_decision(a: str, b: str) -> str:
    if a not in DECISION_SEVERITY:
        return b
    if b not in DECISION_SEVERITY:
        return a
    # Prefer non-directional restraint when severity ties (WAIT > LONG/SHORT).
    if DECISION_SEVERITY[a] == DECISION_SEVERITY[b]:
        if a in ENTRY_SIDES and b not in ENTRY_SIDES:
            return b
        if b in ENTRY_SIDES and a not in ENTRY_SIDES:
            return a
        return a
    return a if DECISION_SEVERITY[a] >= DECISION_SEVERITY[b] else b


def _map_gate_to_decision(gate: str) -> str:
    mapping = {
        "ALLOW": "LONG",  # placeholder; expert side applied later
        "ALLOW_REDUCED": "REDUCE",
        "WAIT": "WAIT",
        "ABSTAIN": "ABSTAIN",
        "BLOCK": "BLOCK",
    }
    return mapping.get(str(gate), "BLOCK")


def _map_abstention_to_decision(verdict: str) -> str:
    mapping = {
        "ALLOW": "LONG",
        "ALLOW_REDUCED": "REDUCE",
        "WAIT": "WAIT",
        "ABSTAIN": "ABSTAIN",
        "BLOCK": "BLOCK",
    }
    return mapping.get(str(verdict), "BLOCK")


def tip_module_presence() -> dict[str, bool]:
    out: dict[str, bool] = {}
    for key, mod in TIP_MODULES.items():
        try:
            __import__(mod)
            out[key] = True
        except Exception:  # noqa: BLE001
            out[key] = False
    return out


def stage_eligible_universe(as_of_ms: int) -> dict[str, Any]:
    universe = reconstruct_universe(as_of_ms=int(as_of_ms))
    return {
        "stage": "eligible_universe",
        "as_of_ms": int(as_of_ms),
        "eligible": list(universe.get("historical_eligible_universe") or []),
        "excluded": list(universe.get("historical_excluded_universe") or []),
        "eligible_count": int(universe.get("eligible_count") or 0),
        "lineage": _sha(
            {
                "eligible": universe.get("historical_eligible_universe"),
                "as_of": as_of_ms,
            }
        ),
        "raw": {
            "source_kind": universe.get("source_kind"),
            "schema": universe.get("schema"),
        },
    }


def stage_feature_snapshot(symbol: str, *, as_of_ms: int) -> dict[str, Any]:
    market = build_synthetic_market(seed=f"v18d-{symbol}", n_bars=48)
    # Align as_of to fixture default when within range; else use market default.
    cutoff = int(market.get("as_of_default") or as_of_ms)
    bundle = compute_all_features(market, as_of=cutoff)
    return {
        "stage": "feature_snapshot",
        "symbol": symbol,
        "as_of": cutoff,
        "feature_count": len(bundle.get("features") or {}),
        "fingerprint": bundle.get("bundle_checksum")
        or _sha(bundle.get("features") or {}),
        "bundle_schema": bundle.get("schema"),
        "data_class": "FIXTURE",
    }


def stage_regime(symbol: str, *, as_of_ms: int, scenario: str) -> dict[str, Any]:
    bars = build_synthetic_bars(symbol=symbol, scenario=scenario, n=48, start_ms=as_of_ms - 48 * 60_000)
    # as_of near last bar receive time
    last_rx = int(bars[-1]["receive_timestamp"])
    result = evaluate_regime(bars, as_of_ms=last_rx, symbol=symbol)
    nested = result.get("probabilities") if isinstance(result.get("probabilities"), dict) else {}
    keys = (
        "strong_bull_probability",
        "strong_bear_probability",
        "volatility_expansion_probability",
        "liquidity_stress_probability",
        "long_crowding_probability",
        "correlation_breakdown_probability",
        "event_risk_probability",
        "regime_transition_probability",
    )
    probs = {
        k: float(nested.get(k, result.get(k, 0.0)) or 0.0)
        for k in keys
    }
    return {
        "stage": "regime",
        "symbol": symbol,
        "as_of": last_rx,
        "scenario": scenario,
        "probabilities": probs,
        "formal_state": result.get("formal_state") or result.get("regime_formal_state"),
        "regime_confidence": float(
            result.get("regime_confidence")
            or nested.get("regime_confidence")
            or 0.0
        ),
        "regime_freshness": float(
            result.get("regime_freshness")
            or nested.get("regime_freshness")
            or 0.0
        ),
        "trading_unsafe": bool(result.get("trading_unsafe", False)),
        "raw_keys": sorted(result.keys()),
    }


def stage_data_trust(trust_inputs: dict[str, Any], *, ai_attempt_override: bool) -> dict[str, Any]:
    trust = evaluate_trust(trust_inputs)
    if ai_attempt_override:
        suggestion = {
            "trust_status": "TRUSTED",
            "gate_action": "ALLOW",
            "ai_confidence": float(trust_inputs.get("ai_confidence") or 0.99),
        }
        trust = apply_trust_ai(trust, suggestion)
        # Dominance must hold: never allow AI to reopen degraded/blocked gates.
        if trust.get("ai_override_applied"):
            refuse_ai_override_data_trust()
    return {
        "stage": "data_trust",
        "trust_status": trust.get("trust_status"),
        "trust_score": float(trust.get("trust_score") or 0.0),
        "gate_action": trust.get("gate_action"),
        "dominance_applied": bool(trust.get("dominance_applied")),
        "ai_override_applied": bool(trust.get("ai_override_applied")),
        "execution_allowed": bool(trust.get("execution_allowed")),
        "reasons": list(trust.get("reasons") or []),
        "raw": trust,
    }


def stage_strategy_experts(
    *,
    symbol: str,
    as_of_ms: int,
    regime: dict[str, Any],
    trust_score: float,
    cost_bps: float,
    liquidity: float,
    stability: float,
    uncertainty: float,
    portfolio_exposure: float,
    risk_gate_allow: bool,
    risk_gate_reason: str,
    open_position_side: str | None,
    abstention_verdict: str | None,
    trading_unsafe: bool,
    formal_state: str | None,
) -> dict[str, Any]:
    probs = regime.get("probabilities") or {}
    ctx = MarketContext(
        symbol=symbol,
        ts_ms=int(as_of_ms),
        regime=RegimeProbabilities(
            strong_bull_probability=float(probs.get("strong_bull_probability") or 0.0),
            strong_bear_probability=float(probs.get("strong_bear_probability") or 0.0),
            volatility_expansion_probability=float(
                probs.get("volatility_expansion_probability") or 0.0
            ),
            liquidity_stress_probability=float(
                probs.get("liquidity_stress_probability") or 0.0
            ),
            long_crowding_probability=float(probs.get("long_crowding_probability") or 0.0),
            correlation_breakdown_probability=float(
                probs.get("correlation_breakdown_probability") or 0.0
            ),
            event_risk_probability=float(probs.get("event_risk_probability") or 0.0),
            regime_transition_probability=float(
                probs.get("regime_transition_probability") or 0.0
            ),
            regime_confidence=float(regime.get("regime_confidence") or 0.0),
            regime_freshness=float(regime.get("regime_freshness") or 0.0),
        ),
        data_trust=float(trust_score),
        execution_cost_bps=float(cost_bps),
        liquidity_score=float(liquidity),
        historical_stability=float(stability),
        uncertainty=float(uncertainty),
        portfolio_exposure=float(portfolio_exposure),
        risk_gate_allow=bool(risk_gate_allow),
        risk_gate_reason=str(risk_gate_reason),
        open_position_side=open_position_side,
        regime_formal_state=str(formal_state or "CLEAR"),
        trading_unsafe=bool(trading_unsafe),
        abstention_verdict=abstention_verdict,
    )
    routed = StrategyExpertRouter().route(ctx)
    return {
        "stage": "strategy_experts",
        "expert_id": routed.expert_id,
        "side": routed.side,
        "score": float(routed.score),
        "no_trade": bool(routed.no_trade),
        "reason_trace": routed.reason_trace.to_dict(),
        "expert_scores": [e.to_dict() for e in routed.expert_scores],
    }


def stage_candidate_score(expert: dict[str, Any], *, trust_score: float) -> dict[str, Any]:
    """Candidate score is research ranking — never a trade signal."""
    raw = float(expert.get("score") or 0.0)
    adjusted = raw * max(0.0, min(1.0, float(trust_score)))
    return {
        "stage": "candidate_score",
        "raw_score": raw,
        "adjusted_score": round(adjusted, 6),
        "is_trade_signal": False,
        "candidate_only": True,
        "eligible_for_shadow_entry_rank": adjusted >= MIN_CANDIDATE_SCORE_FOR_ENTRY
        and not bool(expert.get("no_trade")),
    }


def stage_evidence(expert: dict[str, Any], regime: dict[str, Any]) -> dict[str, Any]:
    supporting: list[dict[str, str]] = []
    contradicting: list[dict[str, str]] = []
    probs = regime.get("probabilities") or {}
    side = str(expert.get("side") or "WAIT")
    bull = float(probs.get("strong_bull_probability") or 0.0)
    bear = float(probs.get("strong_bear_probability") or 0.0)
    if side == "LONG":
        supporting.append({"code": "REGIME_BULL", "detail": f"bull={bull:.3f}"})
        if bear > 0.35:
            contradicting.append({"code": "REGIME_BEAR_PRESENT", "detail": f"bear={bear:.3f}"})
    elif side == "SHORT":
        supporting.append({"code": "REGIME_BEAR", "detail": f"bear={bear:.3f}"})
        if bull > 0.35:
            contradicting.append({"code": "REGIME_BULL_PRESENT", "detail": f"bull={bull:.3f}"})
    else:
        supporting.append({"code": "NO_TRADE_POSTURE", "detail": side})
    for step in (expert.get("reason_trace") or {}).get("steps") or []:
        supporting.append(
            {
                "code": f"ROUTER_{step.get('step')}",
                "detail": str(step.get("detail") or "")[:160],
            }
        )
    stress = float(probs.get("liquidity_stress_probability") or 0.0)
    if stress >= 0.55:
        contradicting.append({"code": "LIQUIDITY_STRESS", "detail": f"stress={stress:.3f}"})
    return {
        "stage": "evidence",
        "supporting_evidence": supporting[:12],
        "contradicting_evidence": contradicting[:12],
    }


def stage_cost_feasibility(cost_bps: float) -> dict[str, Any]:
    feasible = float(cost_bps) <= MAX_COST_BPS_FEASIBLE
    return {
        "stage": "cost_feasibility",
        "cost_estimate": {
            "execution_cost_bps": float(cost_bps),
            "max_feasible_bps": MAX_COST_BPS_FEASIBLE,
            "feasible": feasible,
            "authority": "pipeline_cost_gate_v18d",
        },
        "feasible": feasible,
    }


def stage_uncertainty(
    abstention_inputs: dict[str, Any],
    *,
    ai_confidence: float,
) -> dict[str, Any]:
    verdict = evaluate_abstention(abstention_inputs)
    # AI high confidence cannot reopen abstention gates.
    verdict = apply_abstention_ai(
        verdict,
        {
            "verdict": "ALLOW",
            "stated_confidence": float(ai_confidence),
        },
    )
    return {
        "stage": "uncertainty",
        "verdict": verdict.get("verdict"),
        "uncertainty_score": float(verdict.get("uncertainty_score") or 0.0),
        "size_multiplier": float(verdict.get("size_multiplier") or 0.0),
        "ai_override_applied": bool(verdict.get("ai_override_applied")),
        "reasons": list(verdict.get("reasons") or []),
        "raw": verdict,
    }


def stage_risk_review(
    *,
    risk_gate_allow: bool,
    risk_gate_reason: str,
    portfolio_exposure: float,
    cost_feasible: bool,
    trust_gate: str,
    abstention_verdict: str,
    ai_attempt_override_risk: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    status = "PASS"
    allow = bool(risk_gate_allow)
    if not risk_gate_allow:
        status = "BLOCKED"
        reasons.append(str(risk_gate_reason or "RISK_GATE_DENY"))
    if portfolio_exposure >= 0.85:
        status = "BLOCKED" if status == "BLOCKED" else "REDUCE_REQUIRED"
        allow = False
        reasons.append("PORTFOLIO_EXPOSURE_HIGH")
    if not cost_feasible:
        if status == "PASS":
            status = "COST_INFEASIBLE"
        reasons.append("COST_INFEASIBLE")
        allow = False
    if trust_gate in {"WAIT", "ABSTAIN", "BLOCK"}:
        reasons.append(f"TRUST_GATE_{trust_gate}")
        allow = False
        if trust_gate == "BLOCK":
            status = "BLOCKED"
    if abstention_verdict in {"WAIT", "ABSTAIN", "BLOCK"}:
        reasons.append(f"ABSTENTION_{abstention_verdict}")
        allow = False
        if abstention_verdict == "BLOCK":
            status = "BLOCKED"

    refusal = None
    if ai_attempt_override_risk and not allow:
        refusal = {
            "allowed": False,
            "applied": False,
            "reason": "AI_CANNOT_OVERRIDE_RISK",
        }
        # Prove ban path raises when forced apply is attempted.
        try:
            refuse_ai_override_risk()
        except Exception as exc:  # noqa: BLE001
            refusal["exception"] = type(exc).__name__

    return {
        "stage": "risk_review",
        "risk_status": status,
        "risk_gate_allow": allow,
        "risk_gate_reason": risk_gate_reason if risk_gate_allow else (reasons[0] if reasons else risk_gate_reason),
        "reasons": reasons,
        "ai_override_attempted": bool(ai_attempt_override_risk),
        "ai_override_applied": False,
        "refusal": refusal,
    }


def _decision_status_for(side: str) -> str:
    if side == "BLOCK":
        return "BLOCKED"
    if side == "ABSTAIN":
        return "ABSTAINED"
    if side == "WAIT":
        return "WAITING"
    if side in ENTRY_SIDES:
        return "SHADOW_READY"
    if side == "REDUCE":
        return "REVIEWED"
    return "CANDIDATE"


def _compose_final_side(
    *,
    expert_side: str,
    trust_gate: str,
    abstention_verdict: str,
    risk: dict[str, Any],
    cost_feasible: bool,
    candidate: dict[str, Any],
) -> str:
    side = str(expert_side)
    if side not in DECISION_ENUM:
        side = "ABSTAIN"

    # Trust / abstention dominance (never allow AI confidence to reopen).
    trust_dec = _map_gate_to_decision(trust_gate)
    if trust_gate in {"WAIT", "ABSTAIN", "BLOCK"}:
        side = _worse_decision(side, trust_dec if trust_dec != "LONG" else "WAIT")
    elif trust_gate == "ALLOW_REDUCED" and side in ENTRY_SIDES:
        side = "REDUCE" if risk.get("risk_status") == "REDUCE_REQUIRED" else "WAIT"

    abs_dec = _map_abstention_to_decision(abstention_verdict)
    if abstention_verdict in {"WAIT", "ABSTAIN", "BLOCK"}:
        side = _worse_decision(side, abs_dec if abs_dec != "LONG" else "WAIT")
    elif abstention_verdict == "ALLOW_REDUCED" and side in ENTRY_SIDES:
        side = "REDUCE" if side in ENTRY_SIDES and risk.get("open_position") else "WAIT"

    if not risk.get("risk_gate_allow", True):
        if risk.get("risk_status") == "BLOCKED":
            side = _worse_decision(side, "BLOCK" if "MAX_DRAWDOWN" in str(risk.get("risk_gate_reason")) or trust_gate == "BLOCK" else "ABSTAIN")
        else:
            side = _worse_decision(side, "ABSTAIN")

    if not cost_feasible and side in ENTRY_SIDES:
        side = _worse_decision(side, "WAIT")

    if side in ENTRY_SIDES and not candidate.get("eligible_for_shadow_entry_rank"):
        side = _worse_decision(side, "WAIT")

    return side


def _seal_memory(decision: dict[str, Any], *, as_of_ms: int) -> dict[str, Any]:
    graph = DecisionMemoryGraph()
    node = graph.seal_node(
        kind="DECISION",
        as_of_ms=int(as_of_ms),
        payload={
            "decision_id": decision["decision_id"],
            "symbol": decision["symbol"],
            "side": decision["decision"],
            "decision_status": decision["decision_status"],
            "actual_ordered": False,
            "actual_filled": False,
            "is_trade_signal": False,
        },
        version_pins={"code_version": "v18d", "policy_version": "shadow_only"},
    )
    return {
        "node_id": node.get("node_id"),
        "lineage_hash": node.get("lineage_hash"),
        "kind": node.get("kind"),
        "sealed": not bool(node.get("unavailable")),
    }


def run_symbol_pipeline(case: dict[str, Any], *, force_fixture: bool = True) -> dict[str, Any]:
    """Run full shadow pipeline for one fixture case."""
    as_of_ms = int(case.get("as_of_ms") or AS_OF_MS_DEFAULT)
    symbol = str(case["symbol"])
    market = str(case.get("market") or DEFAULT_MARKET)
    data_class, live_hooks = resolve_data_class(force_fixture=force_fixture)

    stages: dict[str, Any] = {}
    universe = stage_eligible_universe(as_of_ms)
    stages["eligible_universe"] = universe
    if symbol not in universe["eligible"] and not case.get("force_symbols"):
        # Still produce a BLOCK decision with full schema for ineligible symbols.
        decision = {
            "decision_id": f"v18d-{symbol}-{as_of_ms}-ineligible",
            "decision": "BLOCK",
            "symbol": symbol,
            "market": market,
            "as_of": as_of_ms,
            "data_class": data_class,
            "data_trust": {"trust_status": "UNAVAILABLE", "trust_score": 0.0},
            "regime_probabilities": {},
            "strategy_expert": None,
            "supporting_evidence": [],
            "contradicting_evidence": [{"code": "NOT_IN_ELIGIBLE_UNIVERSE", "detail": symbol}],
            "cost_estimate": {"execution_cost_bps": None, "feasible": False},
            "uncertainty": {"verdict": "BLOCK", "uncertainty_score": 1.0},
            "risk_status": "BLOCKED",
            "invalidation": ["NOT_IN_ELIGIBLE_UNIVERSE"],
            "freshness": {"regime_freshness": 0.0, "data_freshness_sec": None},
            "lineage": {"universe": universe["lineage"]},
            "decision_status": "BLOCKED",
            "actual_ordered": False,
            "actual_filled": False,
            "is_trade_signal": False,
            "exchange_order_id": None,
            "candidate_score": None,
        }
        assert_shadow_flags(decision)
        return {
            "case_id": case.get("case_id"),
            "stages": stages,
            "decision": decision,
            "live_hooks": live_hooks,
            "pipeline_stages": list(PIPELINE_STAGES),
        }

    features = stage_feature_snapshot(symbol, as_of_ms=as_of_ms)
    stages["feature_snapshot"] = features

    regime = stage_regime(
        symbol,
        as_of_ms=as_of_ms,
        scenario=str(case.get("regime_scenario") or "mixed"),
    )
    stages["regime"] = regime

    trust = stage_data_trust(
        case["trust"],
        ai_attempt_override=bool(case.get("ai_attempt_override_trust")),
    )
    stages["data_trust"] = trust

    # Preliminary uncertainty for router context (refined after expert).
    uncertainty = stage_uncertainty(
        case["abstention"],
        ai_confidence=float(case.get("ai_confidence") or 0.8),
    )
    stages["uncertainty"] = uncertainty

    expert = stage_strategy_experts(
        symbol=symbol,
        as_of_ms=as_of_ms,
        regime=regime,
        trust_score=float(trust["trust_score"]),
        cost_bps=float(case.get("execution_cost_bps") or 8.0),
        liquidity=float(case.get("liquidity_score") or 0.5),
        stability=float(case.get("historical_stability") or 0.5),
        uncertainty=float(uncertainty["uncertainty_score"]),
        portfolio_exposure=float(case.get("portfolio_exposure") or 0.0),
        risk_gate_allow=bool(case.get("risk_gate_allow", True)),
        risk_gate_reason=str(case.get("risk_gate_reason") or "PASS"),
        open_position_side=case.get("open_position_side"),
        abstention_verdict=str(uncertainty.get("verdict")),
        trading_unsafe=bool(regime.get("trading_unsafe")),
        formal_state=regime.get("formal_state"),
    )
    stages["strategy_experts"] = expert

    candidate = stage_candidate_score(expert, trust_score=float(trust["trust_score"]))
    stages["candidate_score"] = candidate

    evidence = stage_evidence(expert, regime)
    stages["supporting_evidence"] = {
        "stage": "supporting_evidence",
        "items": evidence["supporting_evidence"],
    }
    stages["contradicting_evidence"] = {
        "stage": "contradicting_evidence",
        "items": evidence["contradicting_evidence"],
    }

    cost = stage_cost_feasibility(float(case.get("execution_cost_bps") or 8.0))
    stages["cost_feasibility"] = cost

    risk = stage_risk_review(
        risk_gate_allow=bool(case.get("risk_gate_allow", True)),
        risk_gate_reason=str(case.get("risk_gate_reason") or "PASS"),
        portfolio_exposure=float(case.get("portfolio_exposure") or 0.0),
        cost_feasible=bool(cost["feasible"]),
        trust_gate=str(trust.get("gate_action") or "BLOCK"),
        abstention_verdict=str(uncertainty.get("verdict") or "BLOCK"),
        ai_attempt_override_risk=bool(case.get("ai_attempt_override_risk")),
    )
    stages["risk_review"] = risk

    final_side = _compose_final_side(
        expert_side=str(expert.get("side") or "WAIT"),
        trust_gate=str(trust.get("gate_action") or "BLOCK"),
        abstention_verdict=str(uncertainty.get("verdict") or "BLOCK"),
        risk=risk,
        cost_feasible=bool(cost["feasible"]),
        candidate=candidate,
    )

    invalidation = [
        *list(risk.get("reasons") or []),
        *[r.get("code") for r in evidence["contradicting_evidence"] if isinstance(r, dict)],
    ]
    if not cost["feasible"]:
        invalidation.append("COST_INFEASIBLE")

    lineage_parts = {
        "universe": universe["lineage"],
        "features": features.get("fingerprint"),
        "regime": _sha(regime.get("probabilities") or {}),
        "trust": trust.get("trust_status"),
        "expert": expert.get("expert_id"),
        "candidate": candidate.get("adjusted_score"),
    }
    decision_id = f"v18d-{symbol}-{as_of_ms}-{_sha(lineage_parts)[:16]}"

    decision: dict[str, Any] = {
        "decision_id": decision_id,
        "decision": final_side,
        "symbol": symbol,
        "market": market,
        "as_of": int(regime.get("as_of") or as_of_ms),
        "data_class": data_class,
        "data_trust": {
            "trust_status": trust.get("trust_status"),
            "trust_score": trust.get("trust_score"),
            "gate_action": trust.get("gate_action"),
            "dominance_applied": trust.get("dominance_applied"),
            "ai_override_applied": trust.get("ai_override_applied"),
        },
        "regime_probabilities": regime.get("probabilities") or {},
        "strategy_expert": expert.get("expert_id"),
        "supporting_evidence": evidence["supporting_evidence"],
        "contradicting_evidence": evidence["contradicting_evidence"],
        "cost_estimate": cost["cost_estimate"],
        "uncertainty": {
            "verdict": uncertainty.get("verdict"),
            "uncertainty_score": uncertainty.get("uncertainty_score"),
            "ai_override_applied": uncertainty.get("ai_override_applied"),
        },
        "risk_status": risk.get("risk_status"),
        "invalidation": invalidation,
        "freshness": {
            "regime_freshness": regime.get("regime_freshness"),
            "data_freshness_sec": (case.get("abstention") or {}).get("data_freshness_sec"),
            "feature_as_of": features.get("as_of"),
        },
        "lineage": lineage_parts,
        "decision_status": _decision_status_for(final_side),
        "actual_ordered": False,
        "actual_filled": False,
        "is_trade_signal": False,
        "exchange_order_id": None,
        "candidate_score": candidate,
        "expert_side_raw": expert.get("side"),
        "ai_confidence": float(case.get("ai_confidence") or 0.0),
    }
    assert_shadow_flags(decision)
    for field in REQUIRED_DECISION_FIELDS:
        if field not in decision:
            raise AssertionError(f"missing_decision_field:{field}")

    memory = _seal_memory(decision, as_of_ms=as_of_ms)
    stages["shadow_decision"] = {
        "stage": "shadow_decision",
        "decision": final_side,
        "memory": memory,
    }
    decision["lineage"]["memory_node_id"] = memory.get("node_id")
    decision["lineage"]["memory_lineage_hash"] = memory.get("lineage_hash")

    return {
        "case_id": case.get("case_id"),
        "stages": stages,
        "decision": decision,
        "live_hooks": live_hooks,
        "pipeline_stages": list(PIPELINE_STAGES),
        "modules_present": tip_module_presence(),
    }


def run_fixture_e2e(*, force_fixture: bool = True) -> dict[str, Any]:
    from backend.nexus_live_opportunity_pipeline.fixtures import fixture_case_catalog

    results = [
        run_symbol_pipeline(case, force_fixture=force_fixture)
        for case in fixture_case_catalog()
    ]
    decisions = [r["decision"] for r in results]
    histogram: dict[str, int] = {k: 0 for k in DECISION_ENUM}
    for d in decisions:
        side = str(d.get("decision"))
        if side in histogram:
            histogram[side] += 1
    actual_ordered_count = sum(1 for d in decisions if d.get("actual_ordered"))
    actual_filled_count = sum(1 for d in decisions if d.get("actual_filled"))
    trade_signal_count = sum(1 for d in decisions if d.get("is_trade_signal"))

    return {
        "schema": SCHEMA,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "case_count": len(results),
        "results": results,
        "decision_histogram": histogram,
        "decision_enum": list(DECISION_ENUM),
        "actual_ordered_count": actual_ordered_count,
        "actual_filled_count": actual_filled_count,
        "trade_signal_count": trade_signal_count,
        "hard_bans": sorted(HARD_BANS),
        "modules_present": tip_module_presence(),
        "live_hooks": results[0]["live_hooks"] if results else resolve_data_class(),
        "pipeline_stages": list(PIPELINE_STAGES),
    }
