#!/usr/bin/env python3
"""Stage 4.18-P2B — ETH watchlist follow-up confirmation diagnostics (offline only)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_entry_failure_analyzer import (  # noqa: E402
    _has_entry_trigger,
    _has_invalidation,
    _is_valid_watch_candidate,
    _normalize_side,
)
from tools.research.stage4_paper_readiness import (  # noqa: E402
    parse_entry_trigger,
    parse_invalidation,
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
        row.get("directional_bias")
        or row.get("bias")
        or row.get("candidate_side")
        or ""
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


def _find_followup(watch: Dict[str, Any], eth_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    wid = str(watch.get("decision_id") or "")
    if wid:
        seen = False
        for row in eth_rows:
            if str(row.get("decision_id") or "") == wid:
                seen = True
                continue
            if seen:
                return row
    if watch in eth_rows:
        idx = eth_rows.index(watch)
        if idx + 1 < len(eth_rows):
            return eth_rows[idx + 1]
    return None


def classify_confirmation_failure(
    watch: Dict[str, Any],
    follow: Optional[Dict[str, Any]],
) -> Tuple[str, str, Dict[str, bool]]:
    flags = {
        "needs_eth_prompt_fix": False,
        "needs_eth_schema_fix": False,
        "needs_followup_state_machine_review": False,
        "needs_another_short_sample": False,
    }
    if follow is None:
        return (
            "eth_insufficient_followup_quality",
            "No follow-up ETH tick after valid_watch",
            {**flags, "needs_another_short_sample": True},
        )

    w_intent = _intent(watch)
    f_intent = _intent(follow)
    w_side = _normalize_side(watch.get("candidate_side"))
    f_side = _normalize_side(follow.get("candidate_side"))
    w_bias = _bias(watch)
    f_bias = _bias(follow)
    w_prov = str(watch.get("provider") or "").lower()
    f_prov = str(follow.get("provider") or "").lower()
    w_conf = _conf(watch)
    f_conf = _conf(follow)
    w_mae = _mae(watch)
    f_mae = _mae(follow)
    cap = symbol_mae_watch_cap_pct(ETH)

    w_trig = _has_entry_trigger(parse_entry_trigger(watch.get("entry_trigger")))
    f_trig = _has_entry_trigger(parse_entry_trigger(follow.get("entry_trigger")))
    w_inv = _has_invalidation(parse_invalidation(follow.get("invalidation") or watch.get("invalidation")))

    if str(follow.get("invalidation_hit") or "").lower() in {"true", "1", "yes"}:
        return (
            "eth_invalidation_or_mae_failed",
            "Follow-up marked invalidation_hit",
            {**flags, "needs_eth_prompt_fix": False},
        )
    if f_mae is not None and f_mae > cap:
        return (
            "eth_invalidation_or_mae_failed",
            f"Follow-up MAE {f_mae} above cap {cap}",
            flags,
        )

    if w_prov and f_prov and w_prov != f_prov:
        # Opposite judgment across providers
        if f_intent in {"soft_skip", "hard_skip", "skip"} and w_intent == "watch":
            return (
                "eth_provider_inconsistent",
                f"Watch provider={w_prov} but follow-up provider={f_prov} intent={f_intent}",
                flags,
            )

    if f_intent in {"soft_skip", "hard_skip", "skip"} and f_intent != "watch":
        reason = "eth_followup_intent_not_watch"
        detail = f"Watch intent={w_intent}; follow-up intent={f_intent}"
        # Check direction change as secondary
        if w_side != "NONE" and f_side not in {"NONE", w_side}:
            return (
                "eth_followup_direction_changed",
                f"Side changed {w_side}->{f_side}; follow-up intent={f_intent}",
                flags,
            )
        if w_bias and f_bias and w_bias != f_bias and f_side == "NONE":
            return (
                "eth_followup_direction_changed",
                f"Bias/side collapsed after watch ({w_bias}/{w_side} -> {f_bias}/{f_side})",
                flags,
            )
        return (reason, detail, flags)

    if w_side != "NONE" and f_side not in {"NONE", w_side}:
        return (
            "eth_followup_direction_changed",
            f"candidate_side {w_side} -> {f_side}",
            flags,
        )

    if w_trig and not f_trig and f_intent == "watch":
        return (
            "eth_entry_trigger_not_confirmed",
            "Watch had entry_trigger but follow-up lost/cleared trigger",
            {**flags, "needs_eth_prompt_fix": True, "needs_eth_schema_fix": True},
        )

    if w_conf is not None and f_conf is not None and f_conf + 0.15 < w_conf and f_conf < 0.45:
        return (
            "eth_confidence_dropped",
            f"Confidence dropped {w_conf} -> {f_conf}",
            flags,
        )

    if f_intent in {"watch", "valid_watch"} and w_side == f_side and w_trig:
        return (
            "eth_state_machine_too_strict",
            "Follow-up still watch-aligned but no graduation recorded",
            {**flags, "needs_followup_state_machine_review": True},
        )

    dq = str(follow.get("data_quality") or follow.get("context_quality") or "").lower()
    if dq in {"poor", "bad", "low", "insufficient"}:
        return (
            "eth_insufficient_followup_quality",
            f"Follow-up data_quality={dq}",
            {**flags, "needs_another_short_sample": True},
        )

    return (
        "eth_followup_intent_not_watch",
        f"Default: follow-up intent={f_intent} did not confirm watch",
        flags,
    )


def recommendation_for(reason: str) -> str:
    mapping = {
        "eth_provider_inconsistent": "eth_provider_consistency_review",
        "eth_followup_intent_not_watch": "eth_followup_market_context_or_confirmation_review",
        "eth_followup_direction_changed": "eth_followup_market_context_or_confirmation_review",
        "eth_state_machine_too_strict": "eth_watchlist_state_machine_review_code_only",
        "eth_entry_trigger_not_confirmed": "eth_entry_trigger_prompt_schema_repair",
        "eth_invalidation_or_mae_failed": "eth_mae_invalidation_alignment_review",
        "eth_confidence_dropped": "eth_followup_market_context_or_confirmation_review",
        "eth_insufficient_followup_quality": "eth_followup_market_context_or_confirmation_review",
    }
    return mapping.get(reason, "eth_followup_market_context_or_confirmation_review")


def _btc_success_patterns(btc_rows: List[Dict[str, Any]], btc_grad: int) -> Dict[str, Any]:
    watches = [r for r in btc_rows if _is_valid_watch_candidate(r) or _intent(r) == "watch"]
    patterns: List[Dict[str, Any]] = []
    for w in watches[: max(3, btc_grad or 3)]:
        trig = parse_entry_trigger(w.get("entry_trigger"))
        inv = parse_invalidation(w.get("invalidation"))
        follow = None
        wid = str(w.get("decision_id") or "")
        seen = False
        for row in btc_rows:
            if wid and str(row.get("decision_id") or "") == wid:
                seen = True
                continue
            if seen:
                follow = row
                break
        patterns.append(
            {
                "decision_id": w.get("decision_id"),
                "provider": w.get("provider"),
                "intent": _intent(w),
                "confidence": _conf(w),
                "directional_bias": _bias(w),
                "candidate_side": w.get("candidate_side"),
                "entry_trigger": trig,
                "invalidation": inv,
                "mae_risk_estimate_pct": _mae(w),
                "confirmation_pattern": {
                    "followup_intent": _intent(follow) if follow else None,
                    "followup_provider": follow.get("provider") if follow else None,
                    "followup_side": follow.get("candidate_side") if follow else None,
                    "followup_confidence": _conf(follow) if follow else None,
                },
                "why_graduation_passed": (
                    "Actual-only BTC watch with entry_trigger/MAE within cap and follow-up "
                    "did not collapse to hard no-edge before calibration graduation"
                ),
            }
        )
    return {
        "btc_valid_watch_count": len(watches),
        "btc_graduation_count_reported": btc_grad,
        "patterns": patterns,
        "common_traits": {
            "providers": dict(Counter(str(p.get("provider") or "") for p in patterns)),
            "sides": dict(Counter(str(p.get("candidate_side") or "") for p in patterns)),
            "avg_confidence": (
                round(
                    sum(float(p["confidence"] or 0) for p in patterns) / max(1, len(patterns)),
                    4,
                )
                if patterns
                else None
            ),
        },
    }


def run_diagnostics(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    p2a_dir: str | Path = "",
    analysis_dir: str | Path = "",
) -> Dict[str, Any]:
    inp = Path(input_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    p2a = Path(p2a_dir) if p2a_dir else Path("/data/stage4_18p2a_eth_btc_graduation_alignment")
    analysis = Path(analysis_dir) if analysis_dir else Path("/data/stage4_18p2_r1_analysis")

    p2a_summary = _read_json(p2a / "eth_btc_alignment_summary.json")
    p2_analysis = _read_json(analysis / "stage4_18p2_r1_analysis_summary.json")
    run_summary = _read_json(inp / "stage4_ai_decision_summary.json")

    eth_rows = _actual_rows(inp, ETH)
    btc_rows = _actual_rows(inp, BTC)
    eth_candidates = [r for r in eth_rows if _is_watch_candidate(r)]
    eth_watches = [r for r in eth_rows if _is_valid_watch_candidate(r)]
    # Prefer stricter valid watches; fall back to intent=watch candidates for timeline
    primary_pool = eth_watches or eth_candidates
    # Prefer P2A reported valid_watch count when available
    p2a_vw = int(p2a_summary.get("eth_actual_valid_watch_count") or 0)

    details: List[Dict[str, Any]] = []
    failure_reason = ""
    failure_detail = ""
    flags = {
        "needs_eth_prompt_fix": False,
        "needs_eth_schema_fix": False,
        "needs_followup_state_machine_review": False,
        "needs_another_short_sample": False,
    }

    primary_watch = primary_pool[0] if primary_pool else None
    follow = _find_followup(primary_watch, eth_rows) if primary_watch else None

    watch_fields: Dict[str, Any] = {
        "eth_watch_provider_distribution": {},
        "eth_watch_confidence": {},
        "eth_watch_directional_bias": {},
        "eth_watch_candidate_side": {},
        "eth_watch_entry_trigger_present": False,
        "eth_watch_invalidation_present": False,
        "eth_watch_mae_risk_estimate_pct": None,
        "eth_watch_mae_cap_passed": False,
    }
    follow_fields: Dict[str, Any] = {
        "followup_decision_intent": "",
        "followup_provider": "",
        "followup_confidence": None,
        "followup_directional_bias": "",
        "followup_candidate_side": "",
        "followup_confirmation_passed": False,
        "followup_invalidation_breached": False,
        "followup_mae_breached": False,
    }

    confirmation_failed = 0
    followup_available = 0

    if primary_watch:
        pool = primary_pool
        prov = Counter(str(w.get("provider") or "unknown").lower() for w in pool)
        sides = Counter(str(w.get("candidate_side") or "NONE") for w in pool)
        biases = Counter(_bias(w) or "NONE" for w in pool)
        confs = [_conf(w) for w in pool if _conf(w) is not None]
        mae = _mae(primary_watch)
        cap = symbol_mae_watch_cap_pct(ETH)
        trig = _has_entry_trigger(parse_entry_trigger(primary_watch.get("entry_trigger")))
        inv = _has_invalidation(parse_invalidation(primary_watch.get("invalidation")))
        watch_fields = {
            "eth_watch_provider_distribution": dict(prov),
            "eth_watch_confidence": {
                "min": min(confs) if confs else None,
                "max": max(confs) if confs else None,
                "avg": round(sum(confs) / len(confs), 4) if confs else None,
                "primary": _conf(primary_watch),
            },
            "eth_watch_directional_bias": dict(biases),
            "eth_watch_candidate_side": dict(sides),
            "eth_watch_entry_trigger_present": trig,
            "eth_watch_invalidation_present": inv,
            "eth_watch_mae_risk_estimate_pct": mae,
            "eth_watch_mae_cap_passed": bool(mae is not None and 0 < mae <= cap),
        }
        if follow is not None:
            followup_available = 1
            f_mae = _mae(follow)
            f_cap = symbol_mae_watch_cap_pct(ETH)
            follow_fields = {
                "followup_decision_intent": _intent(follow),
                "followup_provider": str(follow.get("provider") or ""),
                "followup_confidence": _conf(follow),
                "followup_directional_bias": _bias(follow),
                "followup_candidate_side": str(follow.get("candidate_side") or ""),
                "followup_confirmation_passed": False,
                "followup_invalidation_breached": str(follow.get("invalidation_hit") or "").lower()
                in {"true", "1", "yes"},
                "followup_mae_breached": bool(f_mae is not None and f_mae > f_cap),
            }
            failure_reason, failure_detail, flags = classify_confirmation_failure(primary_watch, follow)
            confirmation_failed = 1
            if failure_reason == "eth_state_machine_too_strict":
                follow_fields["followup_confirmation_passed"] = True
                confirmation_failed = 0
        else:
            failure_reason, failure_detail, flags = classify_confirmation_failure(primary_watch, None)
            confirmation_failed = 1

        details.append(
            {
                "record_type": "eth_watch_confirmation_detail",
                "watch": {
                    "decision_id": primary_watch.get("decision_id"),
                    "provider": primary_watch.get("provider"),
                    "intent": _intent(primary_watch),
                    "confidence": _conf(primary_watch),
                    "candidate_side": primary_watch.get("candidate_side"),
                    "directional_bias": _bias(primary_watch),
                    "mae": mae,
                    "entry_trigger": primary_watch.get("entry_trigger"),
                    "invalidation": primary_watch.get("invalidation"),
                    "strict_valid_watch": bool(_is_valid_watch_candidate(primary_watch)),
                },
                "followup": {
                    "decision_id": follow.get("decision_id") if follow else None,
                    "provider": follow.get("provider") if follow else None,
                    "intent": _intent(follow) if follow else None,
                    "confidence": _conf(follow) if follow else None,
                    "candidate_side": follow.get("candidate_side") if follow else None,
                },
                "confirmation_failure_reason": failure_reason,
                "confirmation_failure_detail": failure_detail,
            }
        )

    eth_grad = int(
        p2a_summary.get("eth_actual_graduation_count")
        or p2_analysis.get("eth_actual_graduation_count")
        or 0
    )
    btc_grad = int(
        p2a_summary.get("btc_actual_graduation_count")
        or p2_analysis.get("btc_actual_graduation_count")
        or 0
    )
    btc_patterns = _btc_success_patterns(btc_rows, btc_grad)
    rec = recommendation_for(failure_reason) if failure_reason else "eth_followup_market_context_or_confirmation_review"

    eth_vw_count = max(len(eth_watches), p2a_vw if primary_watch else 0)
    if primary_watch and eth_vw_count == 0 and _intent(primary_watch) == "watch":
        # Intent-level watch observed; keep candidate visibility even if strict schema fails
        eth_vw_count = max(p2a_vw, 1 if p2a_vw else len(eth_candidates))

    summary: Dict[str, Any] = {
        "stage": "4.18-P2B",
        "source_stage": "4.18-P2-R1",
        "generated_at_utc": utc_now_iso(),
        "p2a_output_loaded": bool(p2a_summary),
        "p2_r1_output_loaded": bool(run_summary) or bool(eth_rows),
        "eth_watch_candidate_count": max(len(eth_candidates), p2a_vw),
        "eth_valid_watch_count": eth_vw_count,
        "eth_followup_tick_available_count": followup_available
        or int(p2a_summary.get("eth_followup_tick_available_count") or 0),
        "eth_confirmation_failed_count": confirmation_failed
        or int(p2a_summary.get("eth_confirmation_failed_count") or 0),
        "eth_graduation_count": eth_grad,
        **watch_fields,
        **follow_fields,
        "confirmation_failure_reason": failure_reason or "unknown",
        "confirmation_failure_detail": failure_detail or "",
        "btc_success_comparison_loaded": True,
        "btc_success_patterns": btc_patterns,
        "eth_recovery_recommendation": rec,
        "needs_eth_prompt_fix": bool(flags.get("needs_eth_prompt_fix")),
        "needs_eth_schema_fix": bool(flags.get("needs_eth_schema_fix")),
        "needs_followup_state_machine_review": bool(flags.get("needs_followup_state_machine_review")),
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
        "shadow_used_for_graduation": False,
        "input_dir": str(inp),
        "output_dir": str(out),
        "p2b_verdict": "STAGE_4_18P2B_PASS",
    }

    details_path = out / "eth_watch_confirmation_details.jsonl"
    with details_path.open("w", encoding="utf-8") as fh:
        for row in details:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        for pat in btc_patterns.get("patterns") or []:
            fh.write(
                json.dumps({"record_type": "btc_success_pattern", **pat}, ensure_ascii=False) + "\n"
            )

    report = _render_report(summary)
    (out / "eth_watch_confirmation_report.md").write_text(report, encoding="utf-8")
    write_json(out / "eth_watch_confirmation_summary.json", summary)
    return summary


def _render_report(s: Dict[str, Any]) -> str:
    return f"""# Stage 4.18-P2B ETH Watchlist Confirmation Diagnostics

Generated: {s.get('generated_at_utc')}

## Recap
- P2-R1 loaded: {s.get('p2_r1_output_loaded')}
- P2A loaded: {s.get('p2a_output_loaded')}
- ETH valid_watch={s.get('eth_valid_watch_count')} confirmation_failed={s.get('eth_confirmation_failed_count')} graduation={s.get('eth_graduation_count')}

## ETH watch
- providers={s.get('eth_watch_provider_distribution')}
- confidence={s.get('eth_watch_confidence')}
- side={s.get('eth_watch_candidate_side')} bias={s.get('eth_watch_directional_bias')}
- trigger={s.get('eth_watch_entry_trigger_present')} invalidation={s.get('eth_watch_invalidation_present')}
- mae={s.get('eth_watch_mae_risk_estimate_pct')} mae_cap_passed={s.get('eth_watch_mae_cap_passed')}

## Follow-up
- intent={s.get('followup_decision_intent')} provider={s.get('followup_provider')}
- conf={s.get('followup_confidence')} side={s.get('followup_candidate_side')} bias={s.get('followup_directional_bias')}
- confirmed={s.get('followup_confirmation_passed')} inval_breach={s.get('followup_invalidation_breached')} mae_breach={s.get('followup_mae_breached')}

## Failure
- reason={s.get('confirmation_failure_reason')}
- detail={s.get('confirmation_failure_detail')}
- recommendation={s.get('eth_recovery_recommendation')}

## Gate
- should_run_60m={s.get('should_run_60m')}
- stage_419_readiness={s.get('stage_419_readiness')}
- should_start_419={s.get('should_start_419')}
- routing_permanent_change_supported={s.get('routing_permanent_change_supported')}

## Verdict
{s.get('p2b_verdict')}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 4.18-P2B ETH watch confirmation diagnostics")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--p2a-dir", default="")
    ap.add_argument("--analysis-dir", default="")
    args = ap.parse_args()
    summary = run_diagnostics(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        p2a_dir=args.p2a_dir,
        analysis_dir=args.analysis_dir,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
