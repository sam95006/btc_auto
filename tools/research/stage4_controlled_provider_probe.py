#!/usr/bin/env python3
"""Stage 4.18-O3 — controlled Groq-vs-Cerebras BTC provider probe (diagnostic only)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_context_summary import (  # noqa: E402
    summarize_patches,
    summarize_reflections,
    summarize_trades,
)
from tools.research.stage4_decision_schema import parse_llm_decision  # noqa: E402
from tools.research.stage4_paper_entry_failure_analyzer import (  # noqa: E402
    _has_entry_trigger,
    _has_invalidation,
    _is_valid_watch_candidate,
)
from tools.research.stage4_paper_readiness import (  # noqa: E402
    apply_schema_level_enforcement,
    assess_decision_quality,
    enrich_proposal_paper_fields,
    parse_entry_trigger,
    parse_invalidation,
)
from tools.research.stage4_prompt_builder import build_decision_prompt, prompt_fingerprint  # noqa: E402
from tools.research.stage4_risk_supervisor import safety_constraints_from_env  # noqa: E402
from tools.research.stage4_schema_repair import attempt_schema_safe_repair  # noqa: E402

BTC_SYMBOL = "BTCUSDT"
DEFAULT_PROVIDERS = ("groq", "cerebras")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _intent_bucket(intent: str) -> str:
    i = intent.lower()
    if i == "watch":
        return "watch"
    if i in {"soft_skip", "soft-skip"}:
        return "soft_skip"
    if i in {"hard_skip", "hard-skip"}:
        return "hard_skip"
    if i == "enter_candidate":
        return "enter_candidate"
    return i or "unknown"


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _distribution(values: List[Any]) -> Dict[str, int]:
    return dict(Counter(str(v) for v in values))


def _stage3_context_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    summary = row.get("stage3_context_summary") or {}
    patches = row.get("retrieved_patches") or []
    recent_trades = row.get("recent_trade_results") or summary.get("recent_trade_results") or []
    recent_reflections = row.get("recent_reflections") or summary.get("recent_reflections") or []
    return {
        "stage3_context_available": bool(
            row.get("stage3_context_available", summary.get("stage3_context_available", False))
        ),
        "stage3_context_reason": str(
            row.get("stage3_context_reason") or summary.get("stage3_context_reason") or "unknown"
        ),
        "recent_trade_results_count": int(
            row.get("recent_trade_results_count") or summary.get("recent_trade_results_count") or len(recent_trades)
        ),
        "recent_reflections_count": int(
            row.get("recent_reflections_count") or summary.get("recent_reflections_count") or len(recent_reflections)
        ),
        "active_patches_count": int(
            row.get("active_patches_count") or summary.get("active_patches_count") or len(patches)
        ),
        "recent_trade_results": recent_trades,
        "recent_reflections": recent_reflections,
        "active_patches": summary.get("active_patches") or summarize_patches(patches, limit=5),
    }


def select_btc_contexts(
    btc_rows: List[Dict[str, Any]],
    *,
    max_contexts: int = 3,
) -> List[Dict[str, Any]]:
    valid = [r for r in btc_rows if not r.get("parse_error")]
    if not valid:
        return []

    def _conf(row: Dict[str, Any]) -> float:
        return _safe_float(row.get("confidence"))

    soft_skips = [
        r for r in valid if _intent_bucket(str(r.get("decision_intent") or "")) == "soft_skip"
    ]
    low_pool = soft_skips or valid
    low_ctx = min(low_pool, key=lambda r: abs(_conf(r) - 0.20))
    high_ctx = max(valid, key=_conf)
    recent_ctx = valid[-1]

    selected: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _add(row: Dict[str, Any]) -> None:
        did = str(row.get("decision_id") or id(row))
        if did in seen_ids:
            return
        seen_ids.add(did)
        selected.append(row)

    _add(low_ctx)
    _add(high_ctx)
    _add(recent_ctx)
    if len(selected) < max_contexts:
        for row in reversed(valid):
            _add(row)
            if len(selected) >= max_contexts:
                break
    return selected[:max_contexts]


def build_context_record(row: Dict[str, Any]) -> Dict[str, Any]:
    s3 = _stage3_context_from_row(row)
    return {
        "source_decision_id": row.get("decision_id"),
        "symbol": str(row.get("symbol") or BTC_SYMBOL).upper(),
        "tick_index": row.get("tick_index"),
        "created_at_utc": row.get("created_at_utc"),
        "original_provider": row.get("provider"),
        "market_context": row.get("market_context") or {},
        "stage3_context_summary": s3,
        "account_context": row.get("account_context") or {},
        "retrieved_patches": row.get("retrieved_patches") or [],
        "recent_trade_results": row.get("recent_trade_results") or s3.get("recent_trade_results") or [],
        "recent_reflections": row.get("recent_reflections") or s3.get("recent_reflections") or [],
        "original_decision": {
            "decision_intent": row.get("decision_intent"),
            "confidence": row.get("confidence"),
            "directional_bias": row.get("directional_bias"),
            "candidate_side": row.get("candidate_side"),
            "why_skip": row.get("why_skip"),
            "why_enter": row.get("why_enter"),
            "edge_factors": row.get("edge_factors") or [],
            "risk_factors": row.get("risk_factors") or [],
            "regime": row.get("regime"),
        },
    }


def build_probe_messages(context: Dict[str, Any], *, symbol: str) -> Tuple[List[Dict[str, str]], str]:
    patches = context.get("retrieved_patches") or []
    s3 = context.get("stage3_context_summary") or _stage3_context_from_row(context)
    recent_trades = context.get("recent_trade_results") or []
    recent_reflections = context.get("recent_reflections") or []
    messages = build_decision_prompt(
        symbol=symbol,
        market_context=context.get("market_context") or {},
        account_context=context.get("account_context") or {},
        retrieved_patches=summarize_patches(patches, limit=3),
        recent_trade_results=summarize_trades(recent_trades, limit=3),
        recent_reflections=summarize_reflections(recent_reflections, limit=3),
        safety_constraints=safety_constraints_from_env(),
        current_open_positions=int(context.get("current_open_positions") or 0),
        stage3_context=s3,
    )
    return messages, prompt_fingerprint(messages)


def _proposal_from_llm_result(
    result: Dict[str, Any],
    *,
    symbol: str,
    provider: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    schema_repair_meta: Dict[str, Any] = {}
    parsed = result.get("parsed") or {}
    proposal, ok, err = parse_llm_decision(parsed, symbol=symbol)
    if not ok and result.get("status") == "ok":
        repaired, schema_repair_meta = attempt_schema_safe_repair(parsed, symbol=symbol, parse_error=err)
        if repaired is not None:
            proposal = repaired
            ok = True
            err = ""
    if not ok or result.get("status") != "ok":
        proposal["parse_error"] = True
        proposal["parse_error_type"] = result.get("error_type") or err or "llm_parse_failed"
        proposal["why_skip"] = err or result.get("error") or "llm_probe_failed"
        return proposal, schema_repair_meta
    proposal = enrich_proposal_paper_fields(proposal, proposal)
    return proposal, schema_repair_meta


def _probe_row_from_proposal(
    *,
    probe_id: str,
    source_decision_id: str,
    symbol: str,
    provider: str,
    proposal: Dict[str, Any],
    schema_repair_meta: Dict[str, Any],
    llm_error: str = "",
) -> Dict[str, Any]:
    decision_shape = {
        "symbol": symbol,
        "decision_intent": proposal.get("decision_intent"),
        "candidate_side": proposal.get("candidate_side"),
        "directional_bias": proposal.get("directional_bias"),
        "confidence": proposal.get("confidence"),
        "entry_trigger": proposal.get("entry_trigger"),
        "invalidation": proposal.get("invalidation"),
        "mae_risk_estimate_pct": proposal.get("mae_risk_estimate_pct"),
        "watch_confirmation_reason": proposal.get("watch_confirmation_reason"),
        "parse_error": bool(proposal.get("parse_error") or llm_error),
    }
    enforced = apply_schema_level_enforcement(decision_shape)
    incomplete, paper_readiness, _ = assess_decision_quality(enforced)
    trigger = parse_entry_trigger(enforced.get("entry_trigger"))
    inv = parse_invalidation(enforced.get("invalidation"))
    intent = _intent_bucket(str(enforced.get("decision_intent") or ""))
    return {
        "probe_id": probe_id,
        "source_decision_id": source_decision_id,
        "symbol": symbol,
        "provider": provider,
        "decision_intent": intent,
        "confidence": _safe_float(enforced.get("confidence")) if enforced.get("confidence") is not None else None,
        "directional_bias": enforced.get("directional_bias"),
        "candidate_side": enforced.get("candidate_side"),
        "entry_trigger_present": _has_entry_trigger(trigger),
        "invalidation_present": _has_invalidation(inv),
        "mae_risk_estimate_pct": enforced.get("mae_risk_estimate_pct"),
        "paper_readiness_eligible": bool(paper_readiness.get("eligible_for_watchlist")),
        "block_reason": str(paper_readiness.get("block_reason") or ("parse_error" if llm_error else "ok")),
        "would_be_valid_watch_under_current_rules": _is_valid_watch_candidate(enforced),
        "schema_repair_promoted_eligibility": bool(
            schema_repair_meta.get("schema_repair_promoted_eligibility")
        ),
        "parse_error": bool(enforced.get("parse_error") or llm_error),
        "llm_error": llm_error or None,
        "order_sent": False,
        "diagnostic_only": True,
        "decision_quality_incomplete": incomplete,
    }


def default_llm_probe_fn(
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
    avail = client.availability()
    if not avail.get("real_llm_available"):
        return {
            "status": "error",
            "error_type": "llm_unavailable",
            "error": str(avail.get("reason") or "missing_api_key"),
            "provider": provider,
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
            call_kind="probe",
        )
    finally:
        if prev is None:
            os.environ.pop("STAGE4_ORDER_ALLOWED", None)
        else:
            os.environ["STAGE4_ORDER_ALLOWED"] = prev


def run_single_provider_probe(
    *,
    context: Dict[str, Any],
    provider: str,
    symbol: str,
    probe_fn: Callable[..., Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    source_id = str(context.get("source_decision_id") or "")
    probe_id = str(uuid.uuid4())
    messages, prompt_hash = build_probe_messages(context, symbol=symbol)
    runner = probe_fn or default_llm_probe_fn
    result = runner(provider, messages, symbol=symbol, prompt_hash=prompt_hash)
    llm_error = ""
    if result.get("status") != "ok":
        llm_error = str(result.get("error_type") or result.get("error") or "provider_error")
    proposal, schema_meta = _proposal_from_llm_result(result, symbol=symbol, provider=provider)
    row = _probe_row_from_proposal(
        probe_id=probe_id,
        source_decision_id=source_id,
        symbol=symbol,
        provider=provider,
        proposal=proposal,
        schema_repair_meta=schema_meta,
        llm_error=llm_error,
    )
    row["prompt_hash"] = prompt_hash
    row["llm_status"] = result.get("status")
    row["model_name"] = result.get("model")
    return row


def _infer_recommendation(
    probe_rows: List[Dict[str, Any]],
) -> Tuple[str, str, bool, bool, bool]:
    """Return recommendation, proposed_next_stage, divergence, cerebras_watch_possible, groq_over_conservative."""
    by_source: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for row in probe_rows:
        by_source[str(row.get("source_decision_id"))][str(row.get("provider"))] = row

    divergent = False
    cerebras_watch_possible = False
    groq_over_conservative = False

    for _, prov_map in by_source.items():
        groq = prov_map.get("groq")
        cerebras = prov_map.get("cerebras")
        if not groq or not cerebras:
            continue
        if groq.get("decision_intent") != cerebras.get("decision_intent"):
            divergent = True
        if groq.get("directional_bias") != cerebras.get("directional_bias"):
            divergent = True
        groq_skip = _intent_bucket(str(groq.get("decision_intent") or "")) in {"soft_skip", "hard_skip"}
        cerebras_watch = bool(cerebras.get("would_be_valid_watch_under_current_rules")) or _intent_bucket(
            str(cerebras.get("decision_intent") or "")
        ) == "watch"
        if groq_skip and cerebras_watch:
            groq_over_conservative = True
        if cerebras.get("would_be_valid_watch_under_current_rules") or _intent_bucket(
            str(cerebras.get("decision_intent") or "")
        ) == "watch":
            cerebras_watch_possible = True

    groq_rows = [r for r in probe_rows if r.get("provider") == "groq" and not r.get("parse_error")]
    cerebras_rows = [r for r in probe_rows if r.get("provider") == "cerebras" and not r.get("parse_error")]
    invalid_count = sum(1 for r in probe_rows if r.get("parse_error"))
    groq_vw = sum(1 for r in groq_rows if r.get("would_be_valid_watch_under_current_rules"))
    cerebras_vw = sum(1 for r in cerebras_rows if r.get("would_be_valid_watch_under_current_rules"))
    groq_all_skip = bool(groq_rows) and all(
        _intent_bucket(str(r.get("decision_intent") or "")) in {"soft_skip", "hard_skip"} for r in groq_rows
    )
    cerebras_all_skip = bool(cerebras_rows) and all(
        _intent_bucket(str(r.get("decision_intent") or "")) in {"soft_skip", "hard_skip"} for r in cerebras_rows
    )

    if invalid_count >= max(1, len(probe_rows) // 2):
        return (
            "provider_schema_still_unstable_for_btc",
            "Stage 4.18-N2 provider schema hardening",
            divergent,
            cerebras_watch_possible,
            groq_over_conservative,
        )

    if groq_all_skip and cerebras_all_skip and cerebras_vw == 0 and groq_vw == 0:
        return (
            "btc_no_edge_confirmed_by_both_providers",
            "remain_at_gate_or_wait_new_market_sample",
            divergent,
            False,
            False,
        )

    if cerebras_vw > 0 and groq_all_skip:
        return (
            "provider_routing_affects_btc_watch_yield",
            "Stage 4.18-P provider routing design gate",
            True,
            True,
            True,
        )

    cerebras_watch_invalid = any(
        r.get("provider") == "cerebras"
        and _intent_bucket(str(r.get("decision_intent") or "")) == "watch"
        and not r.get("would_be_valid_watch_under_current_rules")
        for r in probe_rows
    )
    if cerebras_watch_invalid or (
        cerebras_watch_possible and cerebras_vw == 0 and not cerebras_all_skip
    ):
        return (
            "btc_prompt_contract_needs_provider_specific_refinement",
            "Stage 4.18-O4 BTC provider-specific prompt iteration",
            divergent,
            cerebras_watch_possible,
            groq_over_conservative,
        )

    if groq_over_conservative and divergent:
        return (
            "provider_routing_affects_btc_watch_yield",
            "Stage 4.18-P provider routing design gate",
            True,
            cerebras_watch_possible,
            True,
        )

    return (
        "do_not_force_btc_watch",
        "remain_at_gate",
        divergent,
        cerebras_watch_possible,
        groq_over_conservative,
    )


def analyze_probe_summary(probe_rows: List[Dict[str, Any]], *, context_count: int) -> Dict[str, Any]:
    groq_rows = [r for r in probe_rows if r.get("provider") == "groq"]
    cerebras_rows = [r for r in probe_rows if r.get("provider") == "cerebras"]

    def _intent_counts(rows: List[Dict[str, Any]], intent: str) -> int:
        return sum(1 for r in rows if _intent_bucket(str(r.get("decision_intent") or "")) == intent)

    groq_vw = sum(1 for r in groq_rows if r.get("would_be_valid_watch_under_current_rules"))
    cerebras_vw = sum(1 for r in cerebras_rows if r.get("would_be_valid_watch_under_current_rules"))

    rec, next_stage, divergence, cerebras_possible, groq_conservative = _infer_recommendation(probe_rows)

    return {
        "probe_context_count": context_count,
        "provider_probe_count": len(probe_rows),
        "groq_probe_count": len(groq_rows),
        "cerebras_probe_count": len(cerebras_rows),
        "groq_valid_watch_count": groq_vw,
        "cerebras_valid_watch_count": cerebras_vw,
        "groq_soft_skip_count": _intent_counts(groq_rows, "soft_skip"),
        "cerebras_soft_skip_count": _intent_counts(cerebras_rows, "soft_skip"),
        "groq_avg_confidence": _avg(
            [_safe_float(r.get("confidence")) for r in groq_rows if r.get("confidence") is not None]
        ),
        "cerebras_avg_confidence": _avg(
            [_safe_float(r.get("confidence")) for r in cerebras_rows if r.get("confidence") is not None]
        ),
        "groq_directional_bias_distribution": _distribution(
            [str(r.get("directional_bias") or "NONE") for r in groq_rows]
        ),
        "cerebras_directional_bias_distribution": _distribution(
            [str(r.get("directional_bias") or "NONE") for r in cerebras_rows]
        ),
        "provider_divergence_detected": divergence,
        "cerebras_btc_watch_possible": cerebras_possible,
        "groq_btc_over_conservative_possible": groq_conservative,
        "should_change_provider_routing": False,
        "should_force_btc_watch": False,
        "should_change_rg_thresholds": False,
        "stage_419_readiness": False,
        "recommendation": rec,
        "proposed_next_stage": next_stage,
    }


def run_controlled_provider_probe(
    *,
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    symbol: str = BTC_SYMBOL,
    providers: Optional[List[str]] = None,
    max_contexts: int = 3,
    dry_run_only: bool = False,
    diagnostic_only: bool = True,
    probe_fn: Callable[..., Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    sym = symbol.upper()
    inp = Path(input_dir)
    decisions = _read_jsonl(inp / "ai_decisions.jsonl")
    btc_rows = [d for d in decisions if str(d.get("symbol") or "").upper() == sym and not d.get("parse_error")]
    contexts_raw = select_btc_contexts(btc_rows, max_contexts=max_contexts)
    contexts = [build_context_record(r) for r in contexts_raw]
    provider_list = [p.strip().lower() for p in (providers or list(DEFAULT_PROVIDERS)) if p.strip()]

    probe_rows: List[Dict[str, Any]] = []
    if not dry_run_only:
        for ctx in contexts:
            for provider in provider_list:
                probe_rows.append(
                    run_single_provider_probe(
                        context=ctx,
                        provider=provider,
                        symbol=sym,
                        probe_fn=probe_fn,
                    )
                )

    metrics = analyze_probe_summary(probe_rows, context_count=len(contexts))
    summary: Dict[str, Any] = {
        "record_type": "stage4_controlled_provider_probe",
        "stage_marker": "4.18-O3",
        "generated_at_utc": utc_now_iso(),
        "input_dir": str(inp),
        "symbol": sym,
        "providers": provider_list,
        "max_contexts": max_contexts,
        "dry_run_only": dry_run_only,
        "diagnostic_only": diagnostic_only,
        "selected_contexts": contexts,
        **metrics,
        "offline_only": dry_run_only,
        "llm_providers_called": not dry_run_only,
        "mock_ai_used_count": 0,
        "order_sent_count": 0,
        "order_sent": False,
        "exchange_private_api_called": False,
        "production_touched": False,
        "btc_auto_touched": False,
        "paper_events_written": False,
        "calibration_written": False,
        "ai_decisions_appended": False,
    }

    out = Path(output_dir) if output_dir else inp / "stage4_18o3_controlled_provider_probe"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage4_controlled_provider_probe_summary.json", summary)
    write_json(out / "stage4_controlled_provider_probe_contexts.json", {"contexts": contexts})
    with (out / "stage4_controlled_provider_probe_results.jsonl").open("w", encoding="utf-8") as fh:
        for row in probe_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-O3 controlled BTC provider probe")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--symbol", default=BTC_SYMBOL)
    parser.add_argument("--providers", default="groq,cerebras")
    parser.add_argument("--max-contexts", type=int, default=3)
    parser.add_argument("--dry-run-only", action="store_true")
    parser.add_argument("--diagnostic-only", action="store_true", default=True)
    args = parser.parse_args()
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    summary = run_controlled_provider_probe(
        input_dir=args.input_dir,
        output_dir=args.output_dir or None,
        symbol=args.symbol,
        providers=providers,
        max_contexts=args.max_contexts,
        dry_run_only=args.dry_run_only,
        diagnostic_only=args.diagnostic_only,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
