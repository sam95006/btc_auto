#!/usr/bin/env python3
"""Stage 4.18-P2E — ETH no-watch diagnostics (offline only)."""
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

ETH = "ETHUSDT"
P2B_WATCH_REF = {
    "provider": "cerebras",
    "confidence": 0.55,
    "directional_bias": "LONG",
    "candidate_side": "BUY",
    "mae_risk_estimate_pct": 0.3,
}


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


def _block_reason(row: Dict[str, Any]) -> str:
    pr = row.get("paper_readiness")
    if isinstance(pr, dict) and pr.get("block_reason"):
        return str(pr.get("block_reason"))
    for key in ("block_reason", "why_skip", "skip_reason", "veto_reason"):
        val = row.get(key)
        if val:
            return str(val)[:120]
    intent = _intent(row)
    if intent in {"soft_skip", "hard_skip", "skip"}:
        return intent
    return "unknown"


def _actual_eth(input_dir: Path) -> List[Dict[str, Any]]:
    rows = _read_jsonl(input_dir / "ai_decisions.jsonl")
    out: List[Dict[str, Any]] = []
    for row in rows:
        if is_shadow_decision_row(row):
            continue
        if str(row.get("symbol") or "").upper() != ETH:
            continue
        out.append(row)
    return out


def _conf_bucket(c: Optional[float]) -> str:
    if c is None:
        return "unknown"
    if c < 0.2:
        return "lt_0.20"
    if c < 0.35:
        return "0.20_0.35"
    if c < 0.45:
        return "0.35_0.45"
    if c < 0.55:
        return "0.45_0.55"
    return "gte_0.55"


def classify_no_watch(
    *,
    eth_rows: List[Dict[str, Any]],
    stats: Dict[str, Any],
    p2b: Dict[str, Any],
    p2d_prompt: Dict[str, Any],
) -> Tuple[str, Dict[str, bool], str]:
    """Return (root_cause, flags, next_condition)."""
    flags = {
        "prompt_repair_over_conservative_suspected": False,
        "sample_market_no_edge_suspected": False,
        "needs_prompt_adjustment": False,
        "needs_another_short_regression": True,
    }
    n = len(eth_rows) or 1
    skip_n = sum(1 for r in eth_rows if _intent(r) in {"soft_skip", "hard_skip", "skip"})
    direction_n = sum(
        1
        for r in eth_rows
        if _normalize_side(r.get("candidate_side")) != "NONE"
        or _bias(r) in {"LONG", "SHORT", "BUY", "SELL"}
    )
    low_conf = sum(1 for r in eth_rows if (_conf(r) or 0) < 0.40)
    trigger_present = int(stats.get("eth_entry_trigger_present_count") or 0)
    inval_present = int(stats.get("eth_invalidation_present_count") or 0)
    mae_above = int(stats.get("eth_mae_above_cap_count") or 0)
    prov = stats.get("eth_provider_distribution") or {}
    p2b_prov = str((p2b.get("watch_provider") or p2b.get("eth_watch_provider") or "cerebras")).lower()

    # MAE above cap dominates when any
    if mae_above > 0 and mae_above >= max(1, direction_n):
        flags["needs_another_short_regression"] = True
        return (
            "mae_above_cap",
            flags,
            "operator_approved_short_regression_after_eth_mae_alignment_review_no_cap_change",
        )

    # Direction present but missing trigger/invalidation
    if direction_n > 0 and (trigger_present == 0 or inval_present == 0):
        return (
            "entry_trigger_or_invalidation_missing",
            flags,
            "operator_approved_short_regression_after_eth_entry_trigger_invalidation_output_review",
        )

    # Direction present but confidence low
    if direction_n > 0 and low_conf >= direction_n:
        return (
            "confidence_below_watch_threshold",
            flags,
            "operator_approved_short_regression_after_confidence_distribution_review_no_threshold_change",
        )

    # Provider shift vs P2B cerebras-first watch
    cerebras = int(prov.get("cerebras") or 0)
    if cerebras == 0 and p2b_prov == "cerebras" and skip_n == len(eth_rows):
        return (
            "provider_output_shift",
            flags,
            "operator_approved_short_regression_after_eth_provider_stability_diagnostics",
        )

    # Prompt repair over-conservative: P2D after repair, fields would look watchable
    # but nothing watched AND prompt repair loaded — only if directions/sides resembled P2B
    p2d_present = bool(p2d_prompt.get("prompt_repair_added"))
    similar_to_p2b_fields = (
        direction_n > 0
        and trigger_present > 0
        and inval_present > 0
        and mae_above == 0
        and int(stats.get("eth_valid_watch_count") or 0) == 0
    )
    if p2d_present and similar_to_p2b_fields:
        flags["prompt_repair_over_conservative_suspected"] = True
        flags["needs_prompt_adjustment"] = True
        return (
            "prompt_repair_over_conservative",
            flags,
            "review_p2d_prompt_for_watch_suppression_code_only_then_operator_approved_short_regression",
        )

    # Default: skip-heavy, low conf, no direction → market/sample no edge
    if skip_n / n >= 0.8 and direction_n == 0 and low_conf >= max(1, int(0.6 * n)):
        flags["sample_market_no_edge_suspected"] = True
        flags["needs_prompt_adjustment"] = False
        return (
            "sample_market_no_edge",
            flags,
            "wait_for_next_operator_approved_short_regression_when_eth_watch_conditions_reappear",
        )

    if direction_n == 0:
        flags["sample_market_no_edge_suspected"] = True
        return (
            "sample_market_no_edge",
            flags,
            "wait_for_next_operator_approved_short_regression_when_eth_watch_conditions_reappear",
        )

    flags["sample_market_no_edge_suspected"] = True
    return (
        "sample_market_no_edge",
        flags,
        "wait_for_next_operator_approved_short_regression_when_eth_watch_conditions_reappear",
    )


def run_diagnostics(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    analysis_dir: str | Path = "",
    p2b_dir: str | Path = "",
    p2c_dir: str | Path = "",
    p2d_dir: str | Path = "",
) -> Dict[str, Any]:
    inp = Path(input_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    analysis = _read_json(Path(analysis_dir) / "stage4_18p2d_r1_analysis_summary.json") if analysis_dir else {}
    if not analysis and analysis_dir:
        analysis = _read_json(Path(analysis_dir) / "eth_no_watch_summary.json")

    p2b = {}
    if p2b_dir:
        p2b = _read_json(Path(p2b_dir) / "eth_watch_confirmation_summary.json")
    p2c = {}
    if p2c_dir:
        p2c = _read_json(Path(p2c_dir) / "eth_followup_context_summary.json")
    p2d = {}
    if p2d_dir:
        p2d = _read_json(Path(p2d_dir) / "eth_followup_prompt_review_summary.json")

    run_sum = _read_json(inp / "stage4_ai_decision_summary.json")
    eth_rows = _actual_eth(inp)

    intent_c: Counter[str] = Counter()
    prov_c: Counter[str] = Counter()
    bias_c: Counter[str] = Counter()
    side_c: Counter[str] = Counter()
    conf_c: Counter[str] = Counter()
    block_c: Counter[str] = Counter()
    missing_c: Counter[str] = Counter()

    entry_present = 0
    inval_present = 0
    mae_above = 0
    valid_watch = 0
    details: List[Dict[str, Any]] = []
    cap = symbol_mae_watch_cap_pct(ETH)

    for i, row in enumerate(eth_rows):
        intent = _intent(row)
        intent_c[intent or "unknown"] += 1
        prov_c[str(row.get("provider") or "unknown").lower()] += 1
        bias = _bias(row) or "NONE"
        bias_c[bias] += 1
        side = _normalize_side(row.get("candidate_side"))
        side_c[side] += 1
        conf = _conf(row)
        conf_c[_conf_bucket(conf)] += 1
        block_c[_block_reason(row)] += 1

        trig = parse_entry_trigger(row.get("entry_trigger"))
        inval = parse_invalidation(row.get("invalidation"))
        has_trig = _has_entry_trigger(trig)
        has_inval = _has_invalidation(inval)
        if has_trig:
            entry_present += 1
        else:
            missing_c["entry_trigger"] += 1
        if has_inval:
            inval_present += 1
        else:
            missing_c["invalidation"] += 1
        if side == "NONE" and intent in {"watch", "enter_candidate"}:
            missing_c["candidate_side"] += 1
        if bias in {"", "NONE"} and intent in {"watch", "enter_candidate"}:
            missing_c["directional_bias"] += 1

        mae = _mae(row)
        if mae is not None and mae > cap:
            mae_above += 1

        is_vw = bool(_is_valid_watch_candidate(row)) or intent == "watch" and has_trig and has_inval and side != "NONE"
        if bool(_is_valid_watch_candidate(row)):
            valid_watch += 1

        details.append(
            {
                "record_type": "eth_decision",
                "index": i,
                "decision_id": row.get("decision_id"),
                "provider": row.get("provider"),
                "intent": intent,
                "confidence": conf,
                "directional_bias": bias,
                "candidate_side": side,
                "block_reason": _block_reason(row),
                "entry_trigger_present": has_trig,
                "invalidation_present": has_inval,
                "mae_risk_estimate_pct": mae,
                "mae_above_cap": bool(mae is not None and mae > cap),
                "is_valid_watch_candidate": bool(_is_valid_watch_candidate(row)),
                "previous_watch_context_injected": bool(row.get("previous_watch_context_injected")),
                "edge_factors": row.get("edge_factors") or [],
                "risk_factors": row.get("risk_factors") or [],
                "why_skip": str(row.get("why_skip") or "")[:200],
            }
        )

    stats = {
        "eth_entry_trigger_present_count": entry_present,
        "eth_invalidation_present_count": inval_present,
        "eth_mae_above_cap_count": mae_above,
        "eth_valid_watch_count": valid_watch,
        "eth_provider_distribution": dict(prov_c),
    }
    root_cause, flags, next_cond = classify_no_watch(
        eth_rows=eth_rows, stats=stats, p2b=p2b or {"watch_provider": "cerebras"}, p2d_prompt=p2d
    )

    # Prefer analysis graduation/watch counts when present
    eth_grad = int(
        analysis.get("eth_actual_graduation_count")
        or analysis.get("eth_graduation_count")
        or 0
    )
    eth_wl = int(analysis.get("eth_watchlist_count") or 0)
    if analysis.get("eth_actual_valid_watch_count") is not None:
        valid_watch = int(analysis.get("eth_actual_valid_watch_count") or 0)

    def _scalar_conf(v: Any, default: float = 0.55) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict):
            for k in ("primary", "avg", "max", "min", "value"):
                if v.get(k) is not None:
                    try:
                        return float(v[k])
                    except (TypeError, ValueError):
                        continue
        return default

    def _scalar_label(v: Any, default: str) -> str:
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
        if isinstance(v, dict) and v:
            # e.g. {"LONG": 1} → LONG
            return str(next(iter(v.keys()))).strip().upper() or default
        return default

    p2b_ref = dict(P2B_WATCH_REF)
    if p2b:
        p2b_ref = {
            "provider": str(
                p2b.get("watch_provider") or p2b.get("eth_watch_provider") or "cerebras"
            ).lower(),
            "confidence": _scalar_conf(
                p2b.get("watch_confidence") or p2b.get("eth_watch_confidence"), 0.55
            ),
            "directional_bias": _scalar_label(
                p2b.get("watch_directional_bias") or p2b.get("eth_watch_directional_bias"),
                "LONG",
            ),
            "candidate_side": _scalar_label(
                p2b.get("watch_candidate_side") or p2b.get("eth_watch_candidate_side"),
                "BUY",
            ),
            "mae_risk_estimate_pct": _scalar_conf(
                p2b.get("watch_mae_risk_estimate_pct")
                or p2b.get("eth_watch_mae_risk_estimate_pct"),
                0.3,
            ),
        }

    summary: Dict[str, Any] = {
        "stage": "4.18-P2E",
        "source_stage": "4.18-P2D-R1",
        "generated_at_utc": utc_now_iso(),
        "p2d_r1_output_loaded": bool(run_sum) or bool(eth_rows),
        "p2b_case_loaded": bool(p2b),
        "p2c_case_loaded": bool(p2c),
        "p2d_prompt_repair_loaded": bool(p2d),
        "eth_decision_count": len(eth_rows),
        "eth_provider_distribution": dict(prov_c),
        "eth_intent_distribution": dict(intent_c),
        "eth_confidence_distribution": dict(conf_c),
        "eth_directional_bias_distribution": dict(bias_c),
        "eth_candidate_side_distribution": dict(side_c),
        "eth_block_reason_counts": dict(block_c),
        "eth_missing_field_counts": dict(missing_c),
        "eth_entry_trigger_present_count": entry_present,
        "eth_invalidation_present_count": inval_present,
        "eth_mae_above_cap_count": mae_above,
        "eth_valid_watch_count": valid_watch,
        "eth_watchlist_count": eth_wl,
        "eth_graduation_count": eth_grad,
        "p2b_eth_watch_reference": p2b_ref,
        "p2c_confirmation_failure_reason": p2c.get("confirmation_failure_reason"),
        "p2d_prompt_repair_added": bool(p2d.get("prompt_repair_added")),
        "no_watch_root_cause": root_cause,
        "prompt_repair_over_conservative_suspected": bool(
            flags.get("prompt_repair_over_conservative_suspected")
        ),
        "sample_market_no_edge_suspected": bool(flags.get("sample_market_no_edge_suspected")),
        "needs_prompt_adjustment": bool(flags.get("needs_prompt_adjustment")),
        "needs_another_short_regression": bool(flags.get("needs_another_short_regression")),
        "should_run_60m": False,
        "stage_419_readiness": False,
        "should_start_419": False,
        "next_runtime_regression_condition": next_cond,
        "operator_approval_required": True,
        "routing_permanent_change_supported": False,
        "offline_only": True,
        "llm_called": False,
        "order_sent": False,
        "exchange_private_api_called": False,
        "mae_cap_changed": False,
        "confidence_floor_changed": False,
        "input_dir": str(inp),
        "output_dir": str(out),
        "p2e_verdict": "STAGE_4_18P2E_PASS",
    }

    with (out / "eth_no_watch_details.jsonl").open("w", encoding="utf-8") as fh:
        for row in details:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.write(
            json.dumps(
                {
                    "record_type": "classification",
                    "no_watch_root_cause": root_cause,
                    "flags": flags,
                    "next_runtime_regression_condition": next_cond,
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    report = f"""# Stage 4.18-P2E ETH No-Watch Diagnostics

Generated: {summary['generated_at_utc']}

## Recap
P2D-R1 had ETH valid_watch=0 / followup_cases=0 so prompt repair was not runtime-validated.

## ETH sample
- decisions={summary['eth_decision_count']}
- providers={summary['eth_provider_distribution']}
- intents={summary['eth_intent_distribution']}
- conf={summary['eth_confidence_distribution']}
- bias={summary['eth_directional_bias_distribution']}
- side={summary['eth_candidate_side_distribution']}
- entry_trigger_present={entry_present} invalidation_present={inval_present} mae_above_cap={mae_above}
- valid_watch={valid_watch} graduation={eth_grad}

## P2B reference watch
{json.dumps(p2b_ref, indent=2)}

## Root cause
- no_watch_root_cause={root_cause}
- prompt_repair_over_conservative_suspected={flags.get('prompt_repair_over_conservative_suspected')}
- sample_market_no_edge_suspected={flags.get('sample_market_no_edge_suspected')}

## Gate
- should_run_60m=false
- stage_419_readiness=false
- should_start_419=false
- next={next_cond}

## Verdict
STAGE_4_18P2E_PASS
"""
    (out / "eth_no_watch_report.md").write_text(report, encoding="utf-8")
    write_json(out / "eth_no_watch_summary.json", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 4.18-P2E ETH no-watch diagnostics")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--analysis-dir", default="")
    ap.add_argument("--p2b-dir", default="")
    ap.add_argument("--p2c-dir", default="")
    ap.add_argument("--p2d-dir", default="")
    args = ap.parse_args()
    summary = run_diagnostics(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        analysis_dir=args.analysis_dir,
        p2b_dir=args.p2b_dir,
        p2c_dir=args.p2c_dir,
        p2d_dir=args.p2d_dir,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
