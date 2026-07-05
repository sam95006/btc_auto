"""Stage 4 provider schema mismatch repair — safe-skip-only defaults."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from tools.research.stage4_decision_schema import (
    LLM_DECISION_FIELDS,
    VALID_ACTIONS,
    VALID_INTENT_ACTIONS,
    VALID_SIDES,
    parse_llm_decision,
)
from tools.research.stage4_paper_readiness import (
    default_paper_field_defaults,
    enrich_proposal_paper_fields,
)

NON_DIRECTIONAL_DEFAULTS: Dict[str, Any] = {
    "requires_manual_review": False,
    "risk_notes": [],
    "patch_awareness": "",
    "uncertainty": "medium",
    "why_enter": "",
    "why_skip": "",
    "side_reason": "",
    "confidence_reason": "",
    "missing_data": [],
    "edge_factors": [],
    "risk_factors": [],
    **{
        k: v
        for k, v in default_paper_field_defaults().items()
        if k
        in {
            "side_confidence",
            "watch_followup_required",
            "watch_confirmation_reason",
            "mfe_potential_estimate_pct",
        }
    },
    "directional_bias": "NONE",
    "mae_risk_estimate_pct": 0.0,
    "risk_reward_estimate": 0.0,
    "entry_trigger": default_paper_field_defaults()["entry_trigger"],
    "invalidation": default_paper_field_defaults()["invalidation"],
    "paper_readiness": default_paper_field_defaults()["paper_readiness"],
}

REPAIRABLE_ERROR_PREFIXES = (
    "missing_fields:",
    "confidence_out_of_range",
    "invalid_final_action:",
    "invalid_candidate_side:",
)

TRADE_INTENT_VALUES = frozenset({"enter", "buy", "sell", "long", "short"})


def _is_repairable_parse_error(parse_error: str) -> bool:
    err = str(parse_error or "").strip().lower()
    if not err:
        return False
    return any(err.startswith(prefix) for prefix in REPAIRABLE_ERROR_PREFIXES) or err in {
        "confidence_out_of_range",
        "missing_fields",
    }


def _raw_is_skip_safe(raw: Dict[str, Any]) -> bool:
    """True when repaired output must not create enter/long/short intent."""
    action = str(raw.get("final_action") or "skip").strip().lower()
    if action in TRADE_INTENT_VALUES or action == "enter":
        return False
    if action in VALID_INTENT_ACTIONS:
        if action == "enter_candidate":
            return False
        return True
    if action not in VALID_ACTIONS:
        return False
    side = str(raw.get("candidate_side") or "NONE").strip().upper()
    if side not in VALID_SIDES:
        return False
    if action == "skip" and side == "NONE":
        return True
    if action == "skip" and side in {"BUY", "SELL"}:
        intent = str(raw.get("decision_intent") or "").strip().lower()
        return intent not in {"enter_candidate"} and action != "enter"
    return action == "skip"


def _missing_field_names(raw: Dict[str, Any]) -> List[str]:
    return [f for f in LLM_DECISION_FIELDS if f not in raw]


def _apply_cosmetic_defaults(raw: Dict[str, Any], *, symbol: str) -> Dict[str, Any]:
    patched = dict(raw)
    for field in _missing_field_names(patched):
        if field in NON_DIRECTIONAL_DEFAULTS:
            patched[field] = NON_DIRECTIONAL_DEFAULTS[field]
        elif field == "symbol":
            patched[field] = symbol.upper()
        elif field == "confidence":
            patched[field] = 0.0
        elif field == "candidate_side":
            patched[field] = "NONE"
        elif field == "final_action":
            patched[field] = "skip"
    for key, value in NON_DIRECTIONAL_DEFAULTS.items():
        if key not in patched:
            patched[key] = value
    if not str(patched.get("symbol") or "").strip():
        patched["symbol"] = symbol.upper()
    return patched


def _apply_safe_skip_defaults(raw: Dict[str, Any], *, symbol: str) -> Dict[str, Any]:
    patched = dict(raw)
    patched.update(
        {
            "final_action": "skip",
            "decision_intent": "hard_skip",
            "symbol": symbol.upper(),
            "candidate_side": "NONE",
            "confidence": 0.0,
            "why_enter": "",
            "why_skip": str(patched.get("why_skip") or "schema_default_safe_skip"),
            "side_reason": "",
            "confidence_reason": "Schema repair forced safe skip.",
            "risk_notes": ["provider_schema_mismatch_repaired_to_safe_skip"],
            "patch_awareness": str(patched.get("patch_awareness") or ""),
            "uncertainty": "high",
            "requires_manual_review": False,
            "missing_data": [],
            "edge_factors": [],
            "risk_factors": [],
        }
    )
    for field in LLM_DECISION_FIELDS:
        if field not in patched:
            patched[field] = NON_DIRECTIONAL_DEFAULTS.get(field, "")
    return patched


def attempt_schema_safe_repair(
    raw: Dict[str, Any],
    *,
    symbol: str,
    parse_error: str,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Attempt safe schema repair for near-valid provider JSON.

    Returns (proposal, meta). proposal is None when repair fails.
    """
    meta: Dict[str, Any] = {
        "schema_mismatch_repair_attempted": True,
        "schema_repaired": False,
        "schema_repair_mode": None,
        "schema_repair_parse_error": parse_error,
        "near_valid_json": bool(raw and isinstance(raw, dict)),
    }
    if not raw or not isinstance(raw, dict):
        meta["schema_mismatch_repair_fail"] = True
        return None, meta
    if not _is_repairable_parse_error(parse_error):
        meta["schema_mismatch_repair_fail"] = True
        return None, meta

    missing = _missing_field_names(raw)
    meta["schema_mismatch_missing_fields"] = missing
    meta["schema_mismatch_invalid_fields"] = []
    if parse_error.startswith("invalid_final_action:"):
        meta["schema_mismatch_invalid_fields"].append(parse_error.split(":", 1)[-1])
    if parse_error.startswith("invalid_candidate_side:"):
        meta["schema_mismatch_invalid_fields"].append(parse_error.split(":", 1)[-1])

    skip_safe = _raw_is_skip_safe(raw)
    meta["schema_mismatch_skip_safe"] = skip_safe

    if skip_safe and parse_error.startswith("missing_fields:"):
        patched = _apply_cosmetic_defaults(raw, symbol=symbol)
        meta["schema_repair_mode"] = "cosmetic_defaults"
    else:
        patched = _apply_safe_skip_defaults(raw, symbol=symbol)
        meta["schema_repair_mode"] = "safe_skip_defaults"
        meta["schema_mismatch_safe_skip_count"] = 1

    proposal, ok, err = parse_llm_decision(patched, symbol=symbol)
    if not ok:
        meta["schema_mismatch_repair_fail"] = True
        meta["schema_repair_residual_error"] = err
        return None, meta

    if meta["schema_repair_mode"] == "safe_skip_defaults":
        proposal["decision_intent"] = "hard_skip"
        proposal["confidence"] = 0.0
        proposal["final_action"] = "skip"
        proposal["candidate_side"] = "NONE"
        proposal["position_size_suggestion"] = 0.0
        if "provider_schema_mismatch_repaired_to_safe_skip" not in (proposal.get("risk_notes") or []):
            proposal["risk_notes"] = list(proposal.get("risk_notes") or []) + [
                "provider_schema_mismatch_repaired_to_safe_skip"
            ]

    proposal["schema_repaired"] = True
    proposal["schema_repair_mode"] = meta["schema_repair_mode"]
    proposal["schema_mismatch_repair_attempted"] = True
    proposal["parse_error"] = False
    proposal["parse_error_type"] = None
    proposal = enrich_proposal_paper_fields(proposal, patched)
    meta["schema_repaired"] = True
    meta["schema_mismatch_repair_success"] = True
    return proposal, meta


def build_schema_mismatch_summary(decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate schema mismatch repair metrics for dry-run summary."""
    by_symbol: Dict[str, int] = {}
    by_provider: Dict[str, int] = {}
    repair_attempt = 0
    repair_success = 0
    repair_fail = 0
    safe_skip = 0
    mismatch_count = 0

    for decision in decisions:
        attempted = bool(decision.get("schema_mismatch_repair_attempted"))
        repaired = bool(decision.get("schema_repaired"))
        parse_type = str(decision.get("parse_error_type") or "")
        if parse_type == "provider_schema_mismatch" or attempted:
            mismatch_count += 1
            sym = str(decision.get("symbol") or "unknown").upper()
            prov = str(decision.get("provider") or "unknown").lower()
            if decision.get("parse_error"):
                by_symbol[sym] = int(by_symbol.get(sym) or 0) + 1
                by_provider[prov] = int(by_provider.get(prov) or 0) + 1
        if attempted:
            repair_attempt += 1
        if repaired:
            repair_success += 1
            if decision.get("schema_repair_mode") == "safe_skip_defaults":
                safe_skip += 1
        elif attempted:
            repair_fail += 1

    return {
        "schema_mismatch_count": mismatch_count,
        "schema_mismatch_repair_attempt_count": repair_attempt,
        "schema_mismatch_repair_success_count": repair_success,
        "schema_mismatch_repair_fail_count": repair_fail,
        "schema_mismatch_safe_skip_count": safe_skip,
        "schema_mismatch_count_by_symbol": by_symbol,
        "schema_mismatch_count_by_provider": by_provider,
    }


__all__ = [
    "attempt_schema_safe_repair",
    "build_schema_mismatch_summary",
]
