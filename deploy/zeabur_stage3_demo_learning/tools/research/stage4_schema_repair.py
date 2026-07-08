"""Stage 4 provider schema mismatch repair — safe-skip-only defaults (Stage 4.18-N)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

ALLOWED_REPAIR_ACTIONS = frozenset(
    {
        "normalize_empty_object_containers",
        "trim_strings",
        "fill_missing_nested_dict_shells",
        "normalize_candidate_side_casing",
        "normalize_directional_bias_casing",
        "normalize_entry_trigger_type_casing",
        "normalize_empty_string_to_null",
    }
)

FORBIDDEN_REPAIR_ACTIONS = frozenset(
    {
        "auto_set_candidate_side_from_bias",
        "synthesize_entry_trigger_to_pass",
        "deflate_mae_to_pass_cap",
        "promote_to_eligible_watchlist",
        "convert_soft_skip_into_watch",
        "convert_watch_into_enter_candidate",
        "create_missing_invalidation_price",
        "create_missing_mae_value",
    }
)

ENTRY_TRIGGER_SHELL = {
    "type": "none",
    "trigger_price": 0,
    "trigger_condition": "",
}

INVALIDATION_SHELL = {
    "invalidation_price": 0,
    "invalidation_reason": "",
    "max_adverse_move_pct": 0.0,
}


def _normalize_side_casing(raw: Any) -> str:
    side = str(raw or "NONE").strip().upper()
    if side in {"BUY", "SELL", "NONE"}:
        return side
    if side in {"LONG"}:
        return "BUY"
    if side in {"SHORT"}:
        return "SELL"
    return side


def _normalize_bias_casing(raw: Any) -> str:
    bias = str(raw or "NONE").strip().upper()
    if bias in {"LONG", "SHORT", "NONE"}:
        return bias
    if bias == "BUY":
        return "LONG"
    if bias == "SELL":
        return "SHORT"
    return bias


def _normalize_trigger_type_casing(raw: Any) -> str:
    val = str(raw or "none").strip().lower()
    allowed = {
        "none",
        "price_breakout",
        "pullback_confirm",
        "momentum_confirm",
    }
    return val if val in allowed else val


def _trim_strings_in_place(obj: Any) -> List[str]:
    actions: List[str] = []
    if isinstance(obj, dict):
        for key, val in list(obj.items()):
            if isinstance(val, str):
                trimmed = val.strip()
                if trimmed != val:
                    obj[key] = trimmed
                    actions.append("trim_strings")
            elif isinstance(val, (dict, list)):
                actions.extend(_trim_strings_in_place(val))
    elif isinstance(obj, list):
        for item in obj:
            actions.extend(_trim_strings_in_place(item))
    return actions


def _would_promote_eligibility(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    from tools.research.stage4_paper_entry_failure_analyzer import _is_valid_watch_candidate
    from tools.research.stage4_paper_readiness import apply_schema_level_enforcement

    b = apply_schema_level_enforcement(dict(before))
    a = apply_schema_level_enforcement(dict(after))
    return not _is_valid_watch_candidate(b) and _is_valid_watch_candidate(a)


def _detect_forbidden_repair_needs(raw: Dict[str, Any]) -> List[str]:
    forbidden: List[str] = []
    intent = str(raw.get("decision_intent") or "").lower()
    if intent not in {"watch", "enter_candidate"}:
        return forbidden
    bias = _normalize_bias_casing(raw.get("directional_bias"))
    side = _normalize_side_casing(raw.get("candidate_side"))
    if bias in {"LONG", "SHORT"} and side == "NONE":
        forbidden.append("auto_set_candidate_side_from_bias")
    trigger = raw.get("entry_trigger")
    if isinstance(trigger, dict):
        ttype = str(trigger.get("type") or "none").lower()
        cond = str(trigger.get("trigger_condition") or "").strip()
        if ttype == "none" or not cond:
            forbidden.append("synthesize_entry_trigger_to_pass")
    elif trigger is None:
        forbidden.append("synthesize_entry_trigger_to_pass")
    try:
        mae = float(raw.get("mae_risk_estimate_pct") or 0)
    except (TypeError, ValueError):
        mae = 0.0
    inv = raw.get("invalidation") if isinstance(raw.get("invalidation"), dict) else {}
    try:
        cap = float(inv.get("max_adverse_move_pct") or 0)
    except (TypeError, ValueError):
        cap = 0.0
    if mae > 0 and cap > 0 and mae > cap:
        forbidden.append("deflate_mae_to_pass_cap")
    return forbidden


def apply_cosmetic_field_normalization(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Cosmetic-only normalization; never synthesize side/trigger/MAE to pass gates."""
    patched = dict(raw)
    actions: List[str] = []
    forbidden_detected = _detect_forbidden_repair_needs(patched)

    if "candidate_side" in patched:
        new_side = _normalize_side_casing(patched.get("candidate_side"))
        if new_side != patched.get("candidate_side"):
            patched["candidate_side"] = new_side
            actions.append("normalize_candidate_side_casing")
    if "directional_bias" in patched:
        new_bias = _normalize_bias_casing(patched.get("directional_bias"))
        if new_bias != patched.get("directional_bias"):
            patched["directional_bias"] = new_bias
            actions.append("normalize_directional_bias_casing")

    trigger = patched.get("entry_trigger")
    if trigger is None:
        patched["entry_trigger"] = dict(ENTRY_TRIGGER_SHELL)
        actions.append("fill_missing_nested_dict_shells")
    elif isinstance(trigger, dict):
        trigger_copy = dict(trigger)
        if not trigger_copy:
            trigger_copy = dict(ENTRY_TRIGGER_SHELL)
            actions.append("normalize_empty_object_containers")
        new_type = _normalize_trigger_type_casing(trigger_copy.get("type"))
        if new_type != trigger_copy.get("type"):
            trigger_copy["type"] = new_type
            actions.append("normalize_entry_trigger_type_casing")
        patched["entry_trigger"] = trigger_copy

    inv = patched.get("invalidation")
    if inv is None:
        patched["invalidation"] = dict(INVALIDATION_SHELL)
        actions.append("fill_missing_nested_dict_shells")
    elif isinstance(inv, dict) and not inv:
        patched["invalidation"] = dict(INVALIDATION_SHELL)
        actions.append("normalize_empty_object_containers")

    trim_actions = _trim_strings_in_place(patched)
    actions.extend(trim_actions)

    before_enforced = dict(raw)
    promoted = _would_promote_eligibility(before_enforced, patched)
    if promoted:
        forbidden_detected.append("promote_to_eligible_watchlist")

    meta = {
        "schema_repair_applied": bool(actions),
        "schema_repair_safe_only": not forbidden_detected and not promoted,
        "schema_repair_actions": sorted(set(actions)),
        "schema_repair_forbidden_actions_detected": sorted(set(forbidden_detected)),
        "schema_repair_promoted_eligibility": promoted,
    }
    return patched, meta


def probe_schema_repair_on_decisions(decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Offline classification of cosmetic repair vs forbidden needs (does not mutate inputs)."""
    applied = 0
    safe_only = 0
    forbidden_count = 0
    promoted_count = 0
    rows: List[Dict[str, Any]] = []

    for raw in decisions:
        if raw.get("parse_error"):
            continue
        _, meta = apply_cosmetic_field_normalization(dict(raw))
        if meta.get("schema_repair_applied"):
            applied += 1
        if meta.get("schema_repair_safe_only"):
            safe_only += 1
        if meta.get("schema_repair_forbidden_actions_detected"):
            forbidden_count += 1
        if meta.get("schema_repair_promoted_eligibility"):
            promoted_count += 1
        rows.append(
            {
                "decision_id": raw.get("decision_id"),
                "symbol": raw.get("symbol"),
                "provider": raw.get("provider"),
                **meta,
            }
        )

    return {
        "record_type": "stage4_schema_repair_probe",
        "stage_marker": "4.18-N",
        "decision_count": len(decisions),
        "schema_repair_applied_count": applied,
        "schema_repair_safe_only_count": safe_only,
        "schema_repair_forbidden_action_count": forbidden_count,
        "schema_repair_promoted_eligibility_count": promoted_count,
        "repair_policy": {
            "allowed_repairs": sorted(ALLOWED_REPAIR_ACTIONS),
            "forbidden_repairs": sorted(FORBIDDEN_REPAIR_ACTIONS),
        },
        "rows": rows,
        "offline_only": True,
        "order_sent": False,
        "exchange_private_api_called": False,
    }


def build_schema_repair_aggregate_metrics(decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    probe = probe_schema_repair_on_decisions(decisions)
    return {
        "schema_repair_applied_count": probe["schema_repair_applied_count"],
        "schema_repair_safe_only_count": probe["schema_repair_safe_only_count"],
        "schema_repair_forbidden_action_count": probe["schema_repair_forbidden_action_count"],
        "schema_repair_promoted_eligibility_count": probe["schema_repair_promoted_eligibility_count"],
    }


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
    "ALLOWED_REPAIR_ACTIONS",
    "FORBIDDEN_REPAIR_ACTIONS",
    "apply_cosmetic_field_normalization",
    "attempt_schema_safe_repair",
    "build_schema_mismatch_summary",
    "build_schema_repair_aggregate_metrics",
    "probe_schema_repair_on_decisions",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-N offline schema repair probe (read-only)")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    inp = Path(args.input_dir)
    rows: List[Dict[str, Any]] = []
    path = inp / "ai_decisions.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    summary = probe_schema_repair_on_decisions(rows)
    out = Path(args.output_dir) if args.output_dir else inp / "stage4_schema_repair_probe"
    out.mkdir(parents=True, exist_ok=True)
    from tools.research.bybit_demo_learning_common import write_json

    write_json(out / "stage4_schema_repair_probe_summary.json", summary)
    summary["output_dir"] = str(out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
