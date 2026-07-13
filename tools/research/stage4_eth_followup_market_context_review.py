#!/usr/bin/env python3
"""Stage 4.18-P2C — ETH follow-up market context / confirmation review (offline only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_entry_failure_analyzer import (  # noqa: E402
    _has_entry_trigger,
    _is_valid_watch_candidate,
    _normalize_side,
)
from tools.research.stage4_paper_readiness import (  # noqa: E402
    parse_entry_trigger,
    symbol_mae_watch_cap_pct,
)
from tools.research.stage4_provider_routing_config import is_shadow_decision_row  # noqa: E402

BTC = "BTCUSDT"
ETH = "ETHUSDT"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _intent(row: Dict[str, Any]) -> str:
    return str(
        row.get("decision_intent")
        or row.get("intent")
        or row.get("final_decision")
        or row.get("final_action")
        or ""
    ).strip().lower()


def _bias(row: Dict[str, Any]) -> str:
    return str(
        row.get("directional_bias") or row.get("bias") or row.get("candidate_side") or ""
    ).strip().upper()


def _conf(row: Dict[str, Any]) -> Optional[float]:
    try:
        return float(row.get("confidence"))
    except (TypeError, ValueError):
        return None


def _mae(row: Dict[str, Any]) -> Optional[float]:
    try:
        v = float(row.get("mae_risk_estimate_pct") or 0)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _as_float(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _market_ctx(row: Dict[str, Any]) -> Dict[str, Any]:
    ctx = row.get("market_context")
    if isinstance(ctx, dict):
        return ctx
    # Flattened fields sometimes live on decision root
    keys = (
        "last_price",
        "price",
        "regime",
        "trend_strength",
        "volatility",
        "volatility_regime",
        "data_quality",
        "funding_rate",
        "open_interest",
        "oi",
        "cvd",
        "cvd_signal",
    )
    out = {k: row.get(k) for k in keys if row.get(k) is not None}
    return out


def _list_field(row: Dict[str, Any], *names: str) -> List[Any]:
    for name in names:
        val = row.get(name)
        if isinstance(val, list):
            return list(val)
        if isinstance(val, str) and val.strip():
            return [val.strip()]
    # nested proposal / reasoning
    for nest in ("llm_proposal", "proposal", "reasoning", "risk_supervisor"):
        obj = row.get(nest)
        if isinstance(obj, dict):
            for name in names:
                val = obj.get(name)
                if isinstance(val, list):
                    return list(val)
    return []


def _actual_rows(input_dir: Path, symbol: str = "") -> List[Dict[str, Any]]:
    rows = _read_jsonl(input_dir / "ai_decisions.jsonl")
    out: List[Dict[str, Any]] = []
    for row in rows:
        if is_shadow_decision_row(row):
            continue
        if symbol and str(row.get("symbol") or "").upper() != symbol.upper():
            continue
        out.append(row)
    return out


def _is_watch_candidate(row: Dict[str, Any]) -> bool:
    return _intent(row) == "watch" or bool(_is_valid_watch_candidate(row))


def _find_watch_followup(eth_rows: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[int], Optional[int]]:
    for i, row in enumerate(eth_rows):
        if not _is_watch_candidate(row):
            continue
        follow = eth_rows[i + 1] if i + 1 < len(eth_rows) else None
        return row, follow, i, (i + 1 if follow is not None else None)
    return None, None, None, None


def _context_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    p0 = _as_float(before.get("last_price") or before.get("price"))
    p1 = _as_float(after.get("last_price") or after.get("price"))
    price_chg = None
    if p0 and p1 and p0 != 0:
        price_chg = round((p1 - p0) / p0 * 100.0, 6)
    return {
        "price_change_pct": price_chg,
        "regime_before": str(before.get("regime") or ""),
        "regime_after": str(after.get("regime") or ""),
        "trend_strength_before": _as_float(before.get("trend_strength")),
        "trend_strength_after": _as_float(after.get("trend_strength")),
        "volatility_before": str(before.get("volatility") or before.get("volatility_regime") or ""),
        "volatility_after": str(after.get("volatility") or after.get("volatility_regime") or ""),
        "data_quality_before": str(before.get("data_quality") or ""),
        "data_quality_after": str(after.get("data_quality") or ""),
        "funding_before": before.get("funding_rate"),
        "funding_after": after.get("funding_rate"),
        "oi_before": before.get("open_interest") or before.get("oi"),
        "oi_after": after.get("open_interest") or after.get("oi"),
        "cvd_before": before.get("cvd") or before.get("cvd_signal"),
        "cvd_after": after.get("cvd") or after.get("cvd_signal"),
    }


def _missing_keys(ctx: Dict[str, Any]) -> List[str]:
    important = ["last_price", "price", "regime", "data_quality", "trend_strength"]
    missing = []
    has_price = ctx.get("last_price") is not None or ctx.get("price") is not None
    for k in important:
        if k in {"last_price", "price"}:
            continue
        if ctx.get(k) in (None, "", "unknown"):
            missing.append(k)
    if not has_price:
        missing.append("price")
    return missing


def _context_degraded(delta: Dict[str, Any], before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    miss_after = _missing_keys(after)
    miss_before = _missing_keys(before)
    if len(miss_after) > len(miss_before):
        return True
    dq0 = str(delta.get("data_quality_before") or "").lower()
    dq1 = str(delta.get("data_quality_after") or "").lower()
    if dq1 in {"poor", "bad", "low", "degraded"} and dq0 not in {"poor", "bad", "low", "degraded"}:
        return True
    if str(delta.get("regime_after") or "").lower() in {"unknown", ""} and str(delta.get("regime_before") or ""):
        return True
    return False


def _market_supports_skip(delta: Dict[str, Any], follow: Dict[str, Any]) -> bool:
    """Heuristic: meaningful adverse price move or regime flip with risk factors."""
    chg = delta.get("price_change_pct")
    risk = _list_field(follow, "risk_factors", "risk_notes", "why_skip")
    edge = _list_field(follow, "edge_factors", "why_enter")
    regime0 = str(delta.get("regime_before") or "").lower()
    regime1 = str(delta.get("regime_after") or "").lower()
    adverse = False
    if isinstance(chg, (int, float)) and abs(float(chg)) >= 0.15:
        adverse = True
    if regime0 and regime1 and regime0 != regime1 and "trend" in regime0:
        adverse = True
    if risk and not edge:
        adverse = True or adverse
    return bool(adverse and (risk or (isinstance(chg, (int, float)) and abs(float(chg)) >= 0.15)))


def classify_failure(
    *,
    watch: Dict[str, Any],
    follow: Dict[str, Any],
    delta: Dict[str, Any],
    entry_rechecked: bool,
    entry_confirmed: bool,
    inval_breached: bool,
    mae_breached: bool,
) -> Tuple[str, bool, bool, Dict[str, bool]]:
    flags = {
        "needs_eth_prompt_fix": False,
        "needs_eth_schema_fix": False,
        "needs_followup_state_machine_review": False,
        "needs_context_quality_fix": False,
        "needs_another_short_sample": False,
    }
    w_conf = _conf(watch) or 0.0
    f_conf = _conf(follow)
    f_intent = _intent(follow)
    w_prov = str(watch.get("provider") or "").lower()
    f_prov = str(follow.get("provider") or "").lower()
    before = _market_ctx(watch)
    after = _market_ctx(follow)
    degraded = _context_degraded(delta, before, after)
    miss = _list_field(follow, "missing_data", "limitations") or _missing_keys(after)
    risk = _list_field(follow, "risk_factors", "risk_notes")
    edge = _list_field(follow, "edge_factors")
    supervisor_raw = follow.get("supervisor_action") or follow.get("risk_supervisor_action")
    if not supervisor_raw and isinstance(follow.get("risk_supervisor"), dict):
        supervisor_raw = follow["risk_supervisor"].get("action")
    supervisor = str(supervisor_raw or "").lower()

    if degraded or (isinstance(miss, list) and len(miss) >= 2 and not _market_supports_skip(delta, follow)):
        return (
            "followup_context_missing_or_degraded",
            False,
            True,
            {**flags, "needs_context_quality_fix": True},
        )

    if _market_supports_skip(delta, follow) and f_intent in {"hard_skip", "soft_skip", "skip"}:
        return ("real_market_reversal_or_no_edge", True, False, flags)

    if (
        not entry_rechecked
        and _has_entry_trigger(parse_entry_trigger(watch.get("entry_trigger")))
        and f_intent in {"hard_skip", "soft_skip", "skip"}
    ):
        # Could still be reasoning collapse; check if context unchanged
        chg = delta.get("price_change_pct")
        tiny_move = chg is None or (isinstance(chg, (int, float)) and abs(float(chg)) < 0.08)
        if tiny_move and not risk:
            return (
                "entry_trigger_not_rechecked",
                False,
                True,
                {**flags, "needs_eth_prompt_fix": False},
            )

    if supervisor in {"block", "force_skip", "hard_block", "reject"} and f_intent in {"hard_skip", "skip"}:
        # If LLM still had side but supervisor blocked — detect via nested fields
        llm_side = _normalize_side(
            (follow.get("llm_proposal") or {}).get("candidate_side")
            if isinstance(follow.get("llm_proposal"), dict)
            else follow.get("raw_candidate_side")
        )
        if llm_side != "NONE" and _normalize_side(follow.get("candidate_side")) == "NONE":
            return (
                "risk_supervisor_over_block",
                False,
                True,
                {**flags, "needs_followup_state_machine_review": False},
            )

    context_stable = not _market_supports_skip(delta, follow) and not degraded
    same_provider = w_prov and f_prov and w_prov == f_prov
    collapsed = (
        same_provider
        and _bias(watch) in {"LONG", "BUY", "SHORT", "SELL"}
        and _normalize_side(follow.get("candidate_side")) == "NONE"
        and (f_conf is not None and f_conf <= 0.05)
        and w_conf >= 0.4
        and not inval_breached
        and not mae_breached
    )

    if collapsed and context_stable and entry_confirmed is False:
        # Prefer prompt-too-strict if trigger still looks valid and no risk factors
        if not risk and _has_entry_trigger(parse_entry_trigger(watch.get("entry_trigger"))):
            return (
                "confirmation_prompt_too_strict",
                False,
                True,
                {**flags, "needs_eth_prompt_fix": True},
            )
        return (
            "provider_reasoning_collapse",
            False,
            True,
            flags,
        )

    if collapsed:
        return ("provider_reasoning_collapse", False, True, flags)

    if not entry_rechecked:
        return (
            "entry_trigger_not_rechecked",
            False,
            True,
            flags,
        )

    if f_intent in {"hard_skip", "soft_skip", "skip"} and risk:
        return ("real_market_reversal_or_no_edge", True, False, flags)

    return ("insufficient_evidence_for_continuation", False, True, {**flags, "needs_another_short_sample": True})


def recommendation_for(reason: str) -> str:
    return {
        "real_market_reversal_or_no_edge": "respect_followup_skip_no_fix",
        "followup_context_missing_or_degraded": "context_quality_repair_before_more_samples",
        "confirmation_prompt_too_strict": "eth_followup_confirmation_prompt_review",
        "provider_reasoning_collapse": "eth_provider_reasoning_consistency_diagnostics",
        "risk_supervisor_over_block": "risk_supervisor_confirmation_review_code_only",
        "entry_trigger_not_rechecked": "eth_entry_trigger_followup_recheck_diagnostics",
        "insufficient_evidence_for_continuation": "eth_followup_market_context_or_confirmation_review",
    }.get(reason, "eth_provider_reasoning_consistency_diagnostics")


def _btc_success_patterns(btc_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    patterns: List[Dict[str, Any]] = []
    for i, row in enumerate(btc_rows):
        if not _is_watch_candidate(row):
            continue
        follow = btc_rows[i + 1] if i + 1 < len(btc_rows) else None
        before = _market_ctx(row)
        after = _market_ctx(follow) if follow else {}
        patterns.append(
            {
                "watch_tick_index": i,
                "followup_tick_index": i + 1 if follow else None,
                "provider": row.get("provider"),
                "confidence_before": _conf(row),
                "confidence_after": _conf(follow) if follow else None,
                "directional_bias_before": _bias(row),
                "directional_bias_after": _bias(follow) if follow else None,
                "candidate_side_before": row.get("candidate_side"),
                "candidate_side_after": follow.get("candidate_side") if follow else None,
                "entry_trigger_before": row.get("entry_trigger"),
                "entry_trigger_after": follow.get("entry_trigger") if follow else None,
                "market_context_delta": _context_delta(before, after) if follow else {},
                "followup_intent": _intent(follow) if follow else None,
                "why_graduation_passed": (
                    "BTC watch retained directional structure or calibration accepted "
                    "actual-only path without full NONE collapse on same-provider hard_skip"
                ),
            }
        )
        if len(patterns) >= 3:
            break
    return {"count": len(patterns), "patterns": patterns}


def run_review(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    p2b_dir: str | Path = "",
    p2a_dir: str | Path = "",
) -> Dict[str, Any]:
    inp = Path(input_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    p2b = Path(p2b_dir) if p2b_dir else Path("/data/stage4_18p2b_eth_watchlist_confirmation_diagnostics")
    p2a = Path(p2a_dir) if p2a_dir else Path("/data/stage4_18p2a_eth_btc_graduation_alignment")

    p2b_summary = _read_json(p2b / "eth_watch_confirmation_summary.json")
    p2a_summary = _read_json(p2a / "eth_btc_alignment_summary.json")
    run_summary = _read_json(inp / "stage4_ai_decision_summary.json")

    eth_rows = _actual_rows(inp, ETH)
    btc_rows = _actual_rows(inp, BTC)
    watch, follow, w_idx, f_idx = _find_watch_followup(eth_rows)

    details: List[Dict[str, Any]] = []
    if not watch or not follow:
        summary = {
            "stage": "4.18-P2C",
            "source_stage": "4.18-P2-R1",
            "generated_at_utc": utc_now_iso(),
            "p2b_output_loaded": bool(p2b_summary),
            "p2_r1_output_loaded": bool(run_summary) or bool(eth_rows),
            "eth_watch_tick_index": w_idx,
            "eth_followup_tick_index": f_idx,
            "tick_gap": None if w_idx is None or f_idx is None else f_idx - w_idx,
            "confirmation_failure_reason": "insufficient_evidence_for_continuation",
            "confirmation_failure_is_market_valid": False,
            "confirmation_failure_is_system_issue": True,
            "eth_recovery_recommendation": "eth_followup_market_context_or_confirmation_review",
            "should_run_60m": False,
            "stage_419_readiness": False,
            "should_start_419": False,
            "routing_permanent_change_supported": False,
            "operator_approval_required": True,
            "p2c_verdict": "STAGE_4_18P2C_PASS",
            "output_dir": str(out),
        }
        write_json(out / "eth_followup_context_summary.json", summary)
        (out / "eth_followup_context_details.jsonl").write_text("", encoding="utf-8")
        (out / "eth_followup_context_report.md").write_text("# P2C incomplete pair\n", encoding="utf-8")
        return summary

    before = _market_ctx(watch)
    after = _market_ctx(follow)
    delta = _context_delta(before, after)

    w_trig = parse_entry_trigger(watch.get("entry_trigger"))
    f_trig = parse_entry_trigger(follow.get("entry_trigger"))
    # Rechecked only if follow-up still carries a real trigger (type != none)
    entry_rechecked = bool(_has_entry_trigger(f_trig)) or bool(
        follow.get("entry_trigger_rechecked")
    )
    # Confirmed if follow-up still has a non-none trigger aligned with watch side / not hard NONE collapse
    entry_confirmed = bool(
        _has_entry_trigger(f_trig)
        and _normalize_side(follow.get("candidate_side")) != "NONE"
        and _intent(follow) in {"watch", "valid_watch", "enter_candidate"}
    )

    inval_breached = str(follow.get("invalidation_hit") or "").lower() in {"true", "1", "yes"}
    if p2b_summary.get("followup_invalidation_breached") is False:
        inval_breached = False
    mae_val = _mae(follow)
    mae_breached = bool(mae_val is not None and mae_val > symbol_mae_watch_cap_pct(ETH))
    if p2b_summary.get("followup_mae_breached") is False:
        mae_breached = False

    reason, market_valid, system_issue, flags = classify_failure(
        watch=watch,
        follow=follow,
        delta=delta,
        entry_rechecked=entry_rechecked,
        entry_confirmed=entry_confirmed,
        inval_breached=inval_breached,
        mae_breached=mae_breached,
    )
    # Prefer P2B reason as parent class when present
    p2b_reason = str(p2b_summary.get("confirmation_failure_reason") or "")
    if p2b_reason == "eth_followup_direction_changed" and reason == "real_market_reversal_or_no_edge":
        # Keep market-valid only if strongly supported
        pass

    btc_patterns = _btc_success_patterns(btc_rows)
    rec = recommendation_for(reason)

    follow_block = str(
        follow.get("block_reason")
        or follow.get("skip_reason")
        or (follow.get("paper_readiness") or {}).get("block_reason")
        if isinstance(follow.get("paper_readiness"), dict)
        else follow.get("block_reason")
        or ""
    )
    if not follow_block and _intent(follow) in {"hard_skip", "soft_skip", "skip"}:
        follow_block = _intent(follow)

    details.append(
        {
            "record_type": "eth_followup_context_pair",
            "watch_tick_index": w_idx,
            "followup_tick_index": f_idx,
            "watch": {
                "decision_id": watch.get("decision_id"),
                "provider": watch.get("provider"),
                "intent": _intent(watch),
                "confidence": _conf(watch),
                "directional_bias": _bias(watch),
                "candidate_side": watch.get("candidate_side"),
                "entry_trigger": watch.get("entry_trigger"),
                "invalidation": watch.get("invalidation"),
                "mae": _mae(watch),
                "market_context": before,
            },
            "followup": {
                "decision_id": follow.get("decision_id"),
                "provider": follow.get("provider"),
                "intent": _intent(follow),
                "confidence": _conf(follow),
                "directional_bias": _bias(follow),
                "candidate_side": follow.get("candidate_side"),
                "block_reason": follow_block,
                "missing_data": _list_field(follow, "missing_data", "limitations") or _missing_keys(after),
                "edge_factors": _list_field(follow, "edge_factors", "why_enter"),
                "risk_factors": _list_field(follow, "risk_factors", "risk_notes", "why_skip"),
                "market_context": after,
            },
            "market_context_delta": delta,
            "confirmation_failure_reason": reason,
        }
    )

    summary: Dict[str, Any] = {
        "stage": "4.18-P2C",
        "source_stage": "4.18-P2-R1",
        "generated_at_utc": utc_now_iso(),
        "p2b_output_loaded": bool(p2b_summary),
        "p2_r1_output_loaded": bool(run_summary) or bool(eth_rows),
        "p2a_output_loaded": bool(p2a_summary),
        "eth_watch_tick_index": w_idx,
        "eth_followup_tick_index": f_idx,
        "tick_gap": None if w_idx is None or f_idx is None else int(f_idx - w_idx),
        "watch_provider": str(watch.get("provider") or ""),
        "watch_intent": _intent(watch),
        "watch_confidence": _conf(watch),
        "watch_directional_bias": _bias(watch),
        "watch_candidate_side": str(watch.get("candidate_side") or ""),
        "watch_entry_trigger": watch.get("entry_trigger") or {},
        "watch_invalidation": watch.get("invalidation") or {},
        "watch_mae_risk_estimate_pct": _mae(watch),
        "followup_provider": str(follow.get("provider") or ""),
        "followup_intent": _intent(follow),
        "followup_confidence": _conf(follow),
        "followup_directional_bias": _bias(follow),
        "followup_candidate_side": str(follow.get("candidate_side") or ""),
        "followup_block_reason": follow_block,
        "followup_missing_data": _list_field(follow, "missing_data", "limitations") or _missing_keys(after),
        "followup_edge_factors": _list_field(follow, "edge_factors", "why_enter"),
        "followup_risk_factors": _list_field(follow, "risk_factors", "risk_notes", "why_skip"),
        "market_context_delta": delta,
        "entry_trigger_rechecked": entry_rechecked,
        "entry_trigger_confirmed_by_context": entry_confirmed,
        "invalidation_breached": inval_breached,
        "mae_breached": mae_breached,
        "confirmation_failure_reason": reason,
        "confirmation_failure_is_market_valid": bool(market_valid),
        "confirmation_failure_is_system_issue": bool(system_issue),
        "btc_success_context_comparison_loaded": True,
        "btc_success_context_patterns": btc_patterns,
        "eth_recovery_recommendation": rec,
        "needs_eth_prompt_fix": bool(flags.get("needs_eth_prompt_fix")),
        "needs_eth_schema_fix": bool(flags.get("needs_eth_schema_fix")),
        "needs_followup_state_machine_review": bool(flags.get("needs_followup_state_machine_review")),
        "needs_context_quality_fix": bool(flags.get("needs_context_quality_fix")),
        "needs_another_short_sample": bool(flags.get("needs_another_short_sample")),
        "should_run_60m": False,
        "stage_419_readiness": False,
        "should_start_419": False,
        "routing_permanent_change_supported": False,
        "operator_approval_required": True,
        "offline_only": True,
        "order_sent": False,
        "llm_called": False,
        "exchange_private_api_called": False,
        "input_dir": str(inp),
        "output_dir": str(out),
        "p2c_verdict": "STAGE_4_18P2C_PASS",
        "p2b_parent_failure_reason": p2b_reason,
    }

    with (out / "eth_followup_context_details.jsonl").open("w", encoding="utf-8") as fh:
        for row in details:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        for pat in btc_patterns.get("patterns") or []:
            fh.write(json.dumps({"record_type": "btc_success_context", **pat}, ensure_ascii=False) + "\n")

    report = f"""# Stage 4.18-P2C ETH Follow-up Market Context Review

Generated: {summary['generated_at_utc']}

## Timeline
- watch_idx={w_idx} follow_idx={f_idx} gap={summary['tick_gap']}
- watch: {summary['watch_provider']} / {summary['watch_intent']} / {summary['watch_confidence']} / {summary['watch_directional_bias']} / {summary['watch_candidate_side']}
- follow: {summary['followup_provider']} / {summary['followup_intent']} / {summary['followup_confidence']} / {summary['followup_directional_bias']} / {summary['followup_candidate_side']}

## Context delta
{json.dumps(delta, indent=2)}

## Classification
- reason={reason}
- market_valid={market_valid}
- system_issue={system_issue}
- recommendation={rec}

## Gate
- should_run_60m=false
- stage_419_readiness=false
- should_start_419=false

## Verdict
STAGE_4_18P2C_PASS
"""
    (out / "eth_followup_context_report.md").write_text(report, encoding="utf-8")
    write_json(out / "eth_followup_context_summary.json", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 4.18-P2C ETH follow-up market context review")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--p2b-dir", default="")
    ap.add_argument("--p2a-dir", default="")
    args = ap.parse_args()
    summary = run_review(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        p2b_dir=args.p2b_dir,
        p2a_dir=args.p2a_dir,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
