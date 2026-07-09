#!/usr/bin/env python3
"""Stage 4.18-P1 — BTC dual-provider shadow runner (diagnostic only, default off)."""
from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.research.stage3_learning_loop import append_jsonl
from tools.research.stage4_context_summary import (
    summarize_patches,
    summarize_reflections,
    summarize_trades,
)
from tools.research.stage4_decision_schema import parse_llm_decision
from tools.research.stage4_paper_entry_failure_analyzer import (
    _has_entry_trigger,
    _has_invalidation,
    _is_valid_watch_candidate,
)
from tools.research.stage4_paper_readiness import (
    apply_schema_level_enforcement,
    assess_decision_quality,
    enrich_proposal_paper_fields,
    parse_entry_trigger,
    parse_invalidation,
)
from tools.research.stage4_prompt_builder import build_decision_prompt, prompt_fingerprint
from tools.research.stage4_provider_routing_config import (
    BTC_SYMBOL,
    SHADOW_JSONL_FILENAME,
    is_btc_shadow_mode_active,
    shadow_provider_for,
)
from tools.research.stage4_risk_supervisor import safety_constraints_from_env
from tools.research.stage4_schema_repair import attempt_schema_safe_repair


def _intent_bucket(intent: str) -> str:
    i = str(intent or "").lower()
    if i == "watch":
        return "watch"
    if i in {"soft_skip", "soft-skip"}:
        return "soft_skip"
    if i in {"hard_skip", "hard-skip"}:
        return "hard_skip"
    return i or "unknown"


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _stage3_from_actual(actual: Dict[str, Any]) -> Dict[str, Any]:
    summary = actual.get("stage3_context_summary") or {}
    return {
        "stage3_context_available": bool(
            actual.get("stage3_context_available", summary.get("stage3_context_available", False))
        ),
        "stage3_context_reason": str(
            actual.get("stage3_context_reason") or summary.get("stage3_context_reason") or "unknown"
        ),
        "recent_trade_results": actual.get("recent_trade_results") or summary.get("recent_trade_results") or [],
        "recent_reflections": actual.get("recent_reflections") or summary.get("recent_reflections") or [],
        "recent_trade_results_count": int(actual.get("recent_trade_results_count") or 0),
        "recent_reflections_count": int(actual.get("recent_reflections_count") or 0),
        "active_patches_count": int(actual.get("active_patches_count") or 0),
        "active_patches": summary.get("active_patches") or summarize_patches(
            actual.get("retrieved_patches") or [], limit=5
        ),
    }


def build_messages_from_actual(actual: Dict[str, Any]) -> Tuple[List[Dict[str, str]], str]:
    symbol = str(actual.get("symbol") or BTC_SYMBOL).upper()
    patches = actual.get("retrieved_patches") or []
    s3 = _stage3_from_actual(actual)
    recent_trades = actual.get("recent_trade_results") or []
    recent_reflections = actual.get("recent_reflections") or []
    messages = build_decision_prompt(
        symbol=symbol,
        market_context=actual.get("market_context") or {},
        account_context=actual.get("account_context") or {},
        retrieved_patches=summarize_patches(patches, limit=3),
        recent_trade_results=summarize_trades(recent_trades, limit=3),
        recent_reflections=summarize_reflections(recent_reflections, limit=3),
        safety_constraints=safety_constraints_from_env(),
        current_open_positions=int(actual.get("current_open_positions") or 0),
        stage3_context=s3,
    )
    return messages, prompt_fingerprint(messages)


def _proposal_from_llm(result: Dict[str, Any], *, symbol: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    schema_meta: Dict[str, Any] = {}
    parsed = result.get("parsed") or {}
    proposal, ok, err = parse_llm_decision(parsed, symbol=symbol)
    if not ok and result.get("status") == "ok":
        repaired, schema_meta = attempt_schema_safe_repair(parsed, symbol=symbol, parse_error=err)
        if repaired is not None:
            proposal = repaired
            ok = True
    if not ok or result.get("status") != "ok":
        proposal["parse_error"] = True
        proposal["why_skip"] = err or result.get("error") or "shadow_llm_failed"
        return proposal, schema_meta
    return enrich_proposal_paper_fields(proposal, proposal), schema_meta


def default_shadow_llm_fn(
    provider: str,
    messages: List[Dict[str, str]],
    *,
    symbol: str,
    prompt_hash: str,
) -> Dict[str, Any]:
    from tools.research.stage4_llm_client import Stage4LLMClient
    from tools.research.stage4_provider_chain import model_for_provider

    client = Stage4LLMClient(
        provider=provider,
        model=model_for_provider(provider, is_primary=(provider == "groq")),
        load_env=True,
    )
    if not client.availability().get("real_llm_available"):
        return {
            "status": "error",
            "error_type": "llm_unavailable",
            "error": "missing_api_key",
            "parsed": {},
        }
    prev = os.environ.get("STAGE4_ORDER_ALLOWED")
    os.environ["STAGE4_ORDER_ALLOWED"] = "false"
    try:
        return client.complete_json(
            messages,
            prompt_hash=prompt_hash,
            symbol=symbol,
            use_rate_gate=False,
            call_kind="shadow_probe",
        )
    finally:
        if prev is None:
            os.environ.pop("STAGE4_ORDER_ALLOWED", None)
        else:
            os.environ["STAGE4_ORDER_ALLOWED"] = prev


def build_shadow_row(
    *,
    actual_decision: Dict[str, Any],
    shadow_proposal: Dict[str, Any],
    shadow_provider: str,
    tick_index: int,
    llm_error: str = "",
) -> Dict[str, Any]:
    symbol = str(actual_decision.get("symbol") or BTC_SYMBOL).upper()
    actual_provider = str(actual_decision.get("provider") or "unknown").lower()
    enforced = apply_schema_level_enforcement(
        {
            "symbol": symbol,
            "decision_intent": shadow_proposal.get("decision_intent"),
            "candidate_side": shadow_proposal.get("candidate_side"),
            "directional_bias": shadow_proposal.get("directional_bias"),
            "confidence": shadow_proposal.get("confidence"),
            "entry_trigger": shadow_proposal.get("entry_trigger"),
            "invalidation": shadow_proposal.get("invalidation"),
            "mae_risk_estimate_pct": shadow_proposal.get("mae_risk_estimate_pct"),
            "watch_confirmation_reason": shadow_proposal.get("watch_confirmation_reason"),
            "parse_error": bool(shadow_proposal.get("parse_error") or llm_error),
        }
    )
    _, paper_readiness, _ = assess_decision_quality(enforced)
    trigger = parse_entry_trigger(enforced.get("entry_trigger"))
    inv = parse_invalidation(enforced.get("invalidation"))
    shadow_intent = _intent_bucket(str(enforced.get("decision_intent") or ""))
    actual_intent = _intent_bucket(str(actual_decision.get("decision_intent") or ""))
    divergence = (
        shadow_intent != actual_intent
        or str(enforced.get("directional_bias") or "NONE")
        != str(actual_decision.get("directional_bias") or "NONE")
    )
    return {
        "record_type": "btc_shadow_provider_decision",
        "shadow_decision_id": str(uuid.uuid4()),
        "source_decision_id": actual_decision.get("decision_id"),
        "source_tick_index": tick_index,
        "symbol": symbol,
        "actual_provider": actual_provider,
        "shadow_provider": shadow_provider,
        "actual_decision_intent": actual_intent,
        "actual_confidence": actual_decision.get("confidence"),
        "actual_directional_bias": actual_decision.get("directional_bias"),
        "actual_candidate_side": actual_decision.get("candidate_side"),
        "shadow_decision_intent": shadow_intent,
        "shadow_confidence": enforced.get("confidence"),
        "shadow_directional_bias": enforced.get("directional_bias"),
        "shadow_candidate_side": enforced.get("candidate_side"),
        "shadow_entry_trigger_present": _has_entry_trigger(trigger),
        "shadow_invalidation_present": _has_invalidation(inv),
        "shadow_mae_risk_estimate_pct": enforced.get("mae_risk_estimate_pct"),
        "shadow_paper_readiness_eligible": bool(paper_readiness.get("eligible_for_watchlist")),
        "shadow_would_be_valid_watch_under_current_rules": _is_valid_watch_candidate(enforced),
        "provider_divergence_detected": divergence,
        "shadow_diagnostic_only": True,
        "shadow_excluded_from_paper_logger": True,
        "shadow_excluded_from_calibration": True,
        "shadow_excluded_from_graduation": True,
        "shadow_excluded_from_stage_419_readiness": True,
        "order_sent": False,
        "llm_error": llm_error or None,
        "parse_error": bool(enforced.get("parse_error") or llm_error),
    }


def run_btc_shadow_for_actual(
    *,
    actual_decision: Dict[str, Any],
    tick_index: int,
    llm_fn: Callable[..., Dict[str, Any]] | None = None,
) -> Optional[Dict[str, Any]]:
    if not is_btc_shadow_mode_active():
        return None
    symbol = str(actual_decision.get("symbol") or "").upper()
    if symbol != BTC_SYMBOL:
        return None
    if actual_decision.get("parse_error"):
        return None
    actual_provider = str(actual_decision.get("provider") or "groq").lower()
    shadow_provider = shadow_provider_for(actual_provider)
    messages, prompt_hash = build_messages_from_actual(actual_decision)
    runner = llm_fn or default_shadow_llm_fn
    result = runner(shadow_provider, messages, symbol=symbol, prompt_hash=prompt_hash)
    llm_error = ""
    if result.get("status") != "ok":
        llm_error = str(result.get("error_type") or result.get("error") or "provider_error")
    proposal, _ = _proposal_from_llm(result, symbol=symbol)
    return build_shadow_row(
        actual_decision=actual_decision,
        shadow_proposal=proposal,
        shadow_provider=shadow_provider,
        tick_index=tick_index,
        llm_error=llm_error,
    )


def append_shadow_decision(output_dir: Path, row: Dict[str, Any]) -> None:
    append_jsonl(output_dir / SHADOW_JSONL_FILENAME, row)


def aggregate_shadow_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        from tools.research.stage4_provider_routing_config import empty_shadow_run_summary

        return empty_shadow_run_summary()
    prov_dist = Counter(str(r.get("shadow_provider") or "unknown") for r in rows)
    valid_watch = sum(1 for r in rows if r.get("shadow_would_be_valid_watch_under_current_rules"))
    divergence = sum(1 for r in rows if r.get("provider_divergence_detected"))
    soft_skip = sum(1 for r in rows if _intent_bucket(str(r.get("shadow_decision_intent") or "")) == "soft_skip")
    return {
        "btc_shadow_mode_enabled": True,
        "btc_shadow_decision_count": len(rows),
        "btc_shadow_provider_distribution": dict(prov_dist),
        "btc_shadow_valid_watch_count": valid_watch,
        "btc_shadow_soft_skip_count": soft_skip,
        "btc_shadow_divergence_count": divergence,
        "btc_shadow_excluded_from_paper_logger": True,
        "btc_shadow_excluded_from_calibration": True,
        "btc_shadow_excluded_from_graduation": True,
        "btc_shadow_excluded_from_stage_419_readiness": True,
    }


def maybe_run_and_write_btc_shadow(
    *,
    output_dir: Path,
    actual_decision: Dict[str, Any],
    tick_index: int,
    llm_fn: Callable[..., Dict[str, Any]] | None = None,
) -> Optional[Dict[str, Any]]:
    row = run_btc_shadow_for_actual(
        actual_decision=actual_decision,
        tick_index=tick_index,
        llm_fn=llm_fn,
    )
    if row is None:
        return None
    append_shadow_decision(output_dir, row)
    return row
