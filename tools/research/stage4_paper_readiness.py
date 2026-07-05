"""Stage 4.18-C paper-readiness fields and decision quality assessment."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

VALID_DIRECTIONAL_BIAS = frozenset({"LONG", "SHORT", "NONE"})
VALID_ENTRY_TRIGGER_TYPES = frozenset(
    {"price_breakout", "pullback_confirm", "momentum_confirm", "none"}
)

PAPER_READINESS_METRIC_KEYS = (
    "directional_bias_present_count",
    "directional_bias_none_count",
    "enter_candidate_missing_side_count",
    "watch_with_directional_bias_count",
    "paper_ready_watch_count",
    "paper_ready_enter_candidate_count",
    "decision_quality_incomplete_count",
    "mae_risk_estimate_present_count",
    "entry_trigger_present_count",
    "invalidation_present_count",
)


def _as_float(raw: Any, default: float = 0.0) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _non_empty_str(raw: Any) -> str:
    return str(raw or "").strip()


def _side_to_bias(side: str) -> str:
    s = str(side or "NONE").strip().upper()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return "NONE"


def _normalize_directional_bias(raw: Any) -> str:
    bias = str(raw or "NONE").strip().upper()
    if bias in {"BUY"}:
        return "LONG"
    if bias in {"SELL"}:
        return "SHORT"
    return bias if bias in VALID_DIRECTIONAL_BIAS else "NONE"


def parse_entry_trigger(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "type": "none",
            "trigger_price": 0.0,
            "trigger_condition": "",
        }
    trigger_type = str(raw.get("type") or "none").strip().lower()
    if trigger_type not in VALID_ENTRY_TRIGGER_TYPES:
        trigger_type = "none"
    return {
        "type": trigger_type,
        "trigger_price": round(_as_float(raw.get("trigger_price")), 6),
        "trigger_condition": _non_empty_str(raw.get("trigger_condition")),
    }


def parse_invalidation(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "invalidation_price": 0.0,
            "invalidation_reason": "",
            "max_adverse_move_pct": 0.0,
        }
    return {
        "invalidation_price": round(_as_float(raw.get("invalidation_price")), 6),
        "invalidation_reason": _non_empty_str(raw.get("invalidation_reason")),
        "max_adverse_move_pct": round(_as_float(raw.get("max_adverse_move_pct")), 6),
    }


def default_paper_readiness_block(
    *,
    eligible_for_watchlist: bool = False,
    eligible_for_hypothetical_entry: bool = False,
    block_reason: str = "",
) -> Dict[str, Any]:
    return {
        "eligible_for_watchlist": eligible_for_watchlist,
        "eligible_for_hypothetical_entry": eligible_for_hypothetical_entry,
        "block_reason": block_reason,
    }


def extract_paper_fields_from_raw(raw: Dict[str, Any], *, proposal: Dict[str, Any]) -> Dict[str, Any]:
    """Extract optional paper-readiness fields from LLM JSON into proposal shape."""
    side = str(proposal.get("candidate_side") or "NONE").upper()
    bias = _normalize_directional_bias(raw.get("directional_bias"))
    if bias == "NONE":
        bias = _side_to_bias(side)

    entry_trigger = parse_entry_trigger(raw.get("entry_trigger"))
    invalidation = parse_invalidation(raw.get("invalidation"))
    paper_readiness_raw = raw.get("paper_readiness")
    paper_readiness = (
        default_paper_readiness_block()
        if not isinstance(paper_readiness_raw, dict)
        else {
            "eligible_for_watchlist": bool(paper_readiness_raw.get("eligible_for_watchlist")),
            "eligible_for_hypothetical_entry": bool(
                paper_readiness_raw.get("eligible_for_hypothetical_entry")
            ),
            "block_reason": _non_empty_str(paper_readiness_raw.get("block_reason")),
        }
    )

    return {
        "directional_bias": bias,
        "side_confidence": round(_as_float(raw.get("side_confidence")), 4),
        "watch_followup_required": bool(raw.get("watch_followup_required")),
        "watch_confirmation_reason": _non_empty_str(raw.get("watch_confirmation_reason")),
        "entry_trigger": entry_trigger,
        "invalidation": invalidation,
        "mae_risk_estimate_pct": round(_as_float(raw.get("mae_risk_estimate_pct")), 6),
        "mfe_potential_estimate_pct": round(_as_float(raw.get("mfe_potential_estimate_pct")), 6),
        "risk_reward_estimate": round(_as_float(raw.get("risk_reward_estimate")), 6),
        "paper_readiness": paper_readiness,
    }


def default_paper_field_defaults() -> Dict[str, Any]:
    return {
        "directional_bias": "NONE",
        "side_confidence": 0.0,
        "watch_followup_required": False,
        "watch_confirmation_reason": "",
        "entry_trigger": parse_entry_trigger(None),
        "invalidation": parse_invalidation(None),
        "mae_risk_estimate_pct": 0.0,
        "mfe_potential_estimate_pct": 0.0,
        "risk_reward_estimate": 0.0,
        "paper_readiness": default_paper_readiness_block(),
    }


def assess_decision_quality(proposal: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Return (decision_quality_incomplete, paper_readiness, incomplete_reasons).

    Missing directional paper fields mark incomplete — not parse_error.
    """
    intent = str(proposal.get("decision_intent") or "").lower()
    side = str(proposal.get("candidate_side") or "NONE").upper()
    bias = _normalize_directional_bias(proposal.get("directional_bias"))
    reasons: List[str] = []

    entry_trigger = parse_entry_trigger(proposal.get("entry_trigger"))
    invalidation = parse_invalidation(proposal.get("invalidation"))
    mae = _as_float(proposal.get("mae_risk_estimate_pct"))
    rr = _as_float(proposal.get("risk_reward_estimate"))
    watch_reason = _non_empty_str(proposal.get("watch_confirmation_reason"))

    if intent == "watch":
        if bias == "NONE":
            reasons.append("watch_missing_directional_bias")
        if not watch_reason:
            reasons.append("watch_missing_confirmation_reason")
        if not invalidation.get("invalidation_reason") and invalidation.get("invalidation_price", 0) <= 0:
            reasons.append("watch_missing_invalidation")
        if mae <= 0:
            reasons.append("watch_missing_mae_risk_estimate")
        eligible = not reasons
        block = ";".join(reasons) if reasons else ""
        paper_readiness = default_paper_readiness_block(
            eligible_for_watchlist=eligible,
            eligible_for_hypothetical_entry=False,
            block_reason=block or ("ok" if eligible else "watch_not_paper_ready"),
        )
        return bool(reasons), paper_readiness, reasons

    if intent == "enter_candidate":
        if side == "NONE":
            reasons.append("enter_candidate_missing_candidate_side")
        if bias == "NONE":
            reasons.append("enter_candidate_missing_directional_bias")
        if entry_trigger.get("type") == "none" or not entry_trigger.get("trigger_condition"):
            reasons.append("enter_candidate_missing_entry_trigger")
        if not invalidation.get("invalidation_reason") and invalidation.get("invalidation_price", 0) <= 0:
            reasons.append("enter_candidate_missing_invalidation")
        if mae <= 0:
            reasons.append("enter_candidate_missing_mae_risk_estimate")
        if rr <= 0:
            reasons.append("enter_candidate_missing_risk_reward_estimate")
        eligible = not reasons
        block = ";".join(reasons) if reasons else ""
        paper_readiness = default_paper_readiness_block(
            eligible_for_watchlist=False,
            eligible_for_hypothetical_entry=eligible,
            block_reason=block or ("ok" if eligible else "enter_not_paper_ready"),
        )
        return bool(reasons), paper_readiness, reasons

    paper_readiness = default_paper_readiness_block(
        eligible_for_watchlist=False,
        eligible_for_hypothetical_entry=False,
        block_reason="skip_intent",
    )
    return False, paper_readiness, []


def enrich_proposal_paper_fields(
    proposal: Dict[str, Any],
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge paper fields and set decision_quality_incomplete on proposal."""
    merged = dict(proposal)
    defaults = default_paper_field_defaults()
    if raw and isinstance(raw, dict):
        defaults.update(extract_paper_fields_from_raw(raw, proposal=merged))
    for key, value in defaults.items():
        if key not in merged:
            merged[key] = value

    incomplete, paper_readiness, _reasons = assess_decision_quality(merged)
    merged["paper_readiness"] = paper_readiness
    merged["decision_quality_incomplete"] = incomplete
    return merged


def infer_decision_quality_incomplete(decision: Dict[str, Any]) -> bool:
    if "decision_quality_incomplete" in decision:
        return bool(decision.get("decision_quality_incomplete"))
    intent = str(decision.get("decision_intent") or "").lower()
    if intent not in {"watch", "enter_candidate"}:
        return False
    incomplete, _, _ = assess_decision_quality(decision)
    return incomplete


def build_paper_readiness_metrics(decisions: List[Dict[str, Any]]) -> Dict[str, int]:
    metrics = {key: 0 for key in PAPER_READINESS_METRIC_KEYS}
    for decision in decisions:
        if decision.get("parse_error") or decision.get("is_mock_ai"):
            continue
        bias = _normalize_directional_bias(decision.get("directional_bias"))
        intent = str(decision.get("decision_intent") or "").lower()
        side = str(decision.get("candidate_side") or "NONE").upper()

        if bias != "NONE":
            metrics["directional_bias_present_count"] += 1
        else:
            metrics["directional_bias_none_count"] += 1

        if intent == "enter_candidate" and side == "NONE":
            metrics["enter_candidate_missing_side_count"] += 1

        if intent == "watch" and bias != "NONE":
            metrics["watch_with_directional_bias_count"] += 1

        if _as_float(decision.get("mae_risk_estimate_pct")) > 0:
            metrics["mae_risk_estimate_present_count"] += 1

        trigger = parse_entry_trigger(decision.get("entry_trigger"))
        if trigger.get("type") != "none" or trigger.get("trigger_condition"):
            metrics["entry_trigger_present_count"] += 1

        inv = parse_invalidation(decision.get("invalidation"))
        if inv.get("invalidation_reason") or inv.get("invalidation_price", 0) > 0:
            metrics["invalidation_present_count"] += 1

        if infer_decision_quality_incomplete(decision):
            metrics["decision_quality_incomplete_count"] += 1
            continue

        pr = decision.get("paper_readiness") or {}
        if intent == "watch" and pr.get("eligible_for_watchlist"):
            metrics["paper_ready_watch_count"] += 1
        if intent == "enter_candidate" and pr.get("eligible_for_hypothetical_entry"):
            metrics["paper_ready_enter_candidate_count"] += 1

    return metrics


__all__ = [
    "VALID_DIRECTIONAL_BIAS",
    "VALID_ENTRY_TRIGGER_TYPES",
    "PAPER_READINESS_METRIC_KEYS",
    "assess_decision_quality",
    "build_paper_readiness_metrics",
    "default_paper_field_defaults",
    "enrich_proposal_paper_fields",
    "infer_decision_quality_incomplete",
    "parse_entry_trigger",
    "parse_invalidation",
]
