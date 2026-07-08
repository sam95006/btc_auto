"""Stage 4 LLM decision output schema and parsing."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

LLM_DECISION_FIELDS = (
    "final_action",
    "symbol",
    "candidate_side",
    "confidence",
    "why_enter",
    "why_skip",
    "side_reason",
    "confidence_reason",
    "risk_notes",
    "patch_awareness",
    "uncertainty",
    "requires_manual_review",
)

VALID_ACTIONS = frozenset({"enter", "skip"})
VALID_INTENT_ACTIONS = frozenset({"watch", "enter_candidate", "hard_skip", "soft_skip"})
VALID_SIDES = frozenset({"BUY", "SELL", "NONE"})
VALID_INTENTS = frozenset({"hard_skip", "soft_skip", "watch", "enter_candidate"})
OPTIONAL_LLM_FIELDS = (
    "decision_intent",
    "missing_data",
    "edge_factors",
    "risk_factors",
    "directional_bias",
    "side_confidence",
    "watch_followup_required",
    "watch_confirmation_reason",
    "entry_trigger",
    "invalidation",
    "mae_risk_estimate_pct",
    "mfe_potential_estimate_pct",
    "risk_reward_estimate",
    "paper_readiness",
)


def _as_float(raw: Any, default: float = 0.0) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _as_list(raw: Any) -> List[Any]:
    return list(raw) if isinstance(raw, list) else []


def parse_llm_decision(raw: Dict[str, Any], *, symbol: str) -> Tuple[Dict[str, Any], bool, str]:
    """Return (proposal, parse_ok, parse_error)."""
    if not raw or not isinstance(raw, dict):
        return skip_proposal(symbol, "empty_llm_response", "empty_llm_response"), False, "empty_llm_response"

    missing = [f for f in LLM_DECISION_FIELDS if f not in raw]
    if missing:
        err = f"missing_fields:{','.join(missing)}"
        return skip_proposal(symbol, err, "missing_fields"), False, err

    action = str(raw.get("final_action") or "skip").strip().lower()
    intent_raw = str(raw.get("decision_intent") or "").strip().lower()
    if action in VALID_INTENT_ACTIONS and action not in VALID_ACTIONS:
        if not intent_raw:
            intent_raw = action
        action = "skip"
    if action not in VALID_ACTIONS:
        err = f"invalid_final_action:{action}"
        return skip_proposal(symbol, err, "invalid_final_action"), False, err

    side = str(raw.get("candidate_side") or "NONE").strip().upper()
    if side not in VALID_SIDES:
        err = f"invalid_candidate_side:{side}"
        return skip_proposal(symbol, err, "invalid_candidate_side"), False, err

    conf = _as_float(raw.get("confidence"))
    if conf < 0 or conf > 1:
        return skip_proposal(symbol, "confidence_out_of_range", "confidence_out_of_range"), False, "confidence_out_of_range"

    sym = str(raw.get("symbol") or symbol).upper()
    intent = intent_raw or str(raw.get("decision_intent") or "").strip().lower()
    if intent and intent not in VALID_INTENTS:
        intent = "hard_skip" if action == "skip" and conf <= 0.1 else "soft_skip"
    elif not intent:
        if action == "enter":
            intent = "enter_candidate"
        elif conf <= 0.1:
            intent = "hard_skip"
        elif conf <= 0.3:
            intent = "soft_skip"
        elif conf <= 0.55:
            intent = "watch"
        else:
            intent = "soft_skip"

    proposal = {
        "final_action": action,
        "decision_intent": intent,
        "symbol": sym,
        "candidate_side": side,
        "confidence": round(conf, 4),
        "why_enter": str(raw.get("why_enter") or ""),
        "why_skip": str(raw.get("why_skip") or ""),
        "side_reason": str(raw.get("side_reason") or ""),
        "confidence_reason": str(raw.get("confidence_reason") or ""),
        "missing_data": [str(x) for x in _as_list(raw.get("missing_data"))],
        "edge_factors": [str(x) for x in _as_list(raw.get("edge_factors"))],
        "risk_factors": [str(x) for x in _as_list(raw.get("risk_factors"))],
        "risk_notes": [str(x) for x in _as_list(raw.get("risk_notes"))],
        "patch_awareness": str(raw.get("patch_awareness") or ""),
        "uncertainty": str(raw.get("uncertainty") or ""),
        "requires_manual_review": bool(raw.get("requires_manual_review")),
        "position_size_suggestion": 0.0,
    }
    if action == "enter" and side != "NONE":
        from tools.research.bybit_demo_learning_common import MAX_MARGIN_USD

        proposal["position_size_suggestion"] = round(min(MAX_MARGIN_USD, MAX_MARGIN_USD * conf), 4)
    from tools.research.stage4_paper_readiness import apply_schema_level_enforcement, enrich_proposal_paper_fields

    enriched = enrich_proposal_paper_fields(proposal, raw)
    return apply_schema_level_enforcement(enriched), True, ""


def skip_proposal(symbol: str, reason: str, parse_error_type: str = "parse_error") -> Dict[str, Any]:
    return {
        "final_action": "skip",
        "symbol": symbol.upper(),
        "candidate_side": "NONE",
        "confidence": 0.0,
        "why_enter": "",
        "why_skip": reason,
        "side_reason": "",
        "confidence_reason": "Parse or validation failed; forced skip.",
        "risk_notes": ["parse_error"],
        "patch_awareness": "",
        "uncertainty": reason,
        "requires_manual_review": True,
        "position_size_suggestion": 0.0,
        "parse_error": True,
        "parse_error_type": parse_error_type,
        "raw_content_empty": parse_error_type in {"empty_llm_response", "content_empty"},
        "order_sent": False,
    }
