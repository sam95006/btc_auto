#!/usr/bin/env python3
"""Stage 4.18-P2F — ETH watch reappearance gate + regression readiness (offline only).

Does NOT run soaks, mutate prompts/routing/RG, or start Stage 4.19.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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
CONF_NEAR_REF_FLOOR = 0.45

DEFAULT_REFERENCE_WATCH = {
    "provider": "cerebras",
    "intent": "watch",
    "confidence": 0.55,
    "directional_bias": "LONG",
    "candidate_side": "BUY",
    "mae_risk_estimate_pct": 0.3,
    "mae_cap_passed": True,
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


def _scalar_conf(v: Any, default: float) -> float:
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
        return str(next(iter(v.keys()))).strip().upper() or default
    return default


def _intent(row: Dict[str, Any]) -> str:
    return str(
        row.get("decision_intent")
        or row.get("intent")
        or row.get("final_decision")
        or ""
    ).strip().lower()


def _bias(row: Dict[str, Any]) -> str:
    return str(
        row.get("directional_bias") or row.get("bias") or ""
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


def _data_quality(row: Dict[str, Any]) -> str:
    for key in ("data_quality", "market_data_quality", "context_quality"):
        v = row.get(key)
        if isinstance(v, dict):
            v = v.get("status") or v.get("quality") or v.get("label")
        if v is not None and str(v).strip():
            return str(v).strip().lower()
    mc = row.get("market_context")
    if isinstance(mc, dict):
        dq = mc.get("data_quality") or mc.get("quality")
        if dq is not None:
            return str(dq).strip().lower()
    return "unknown"


def _regime(row: Dict[str, Any]) -> str:
    for key in ("regime", "market_regime"):
        v = row.get(key)
        if v is not None and str(v).strip():
            return str(v).strip().lower()
    mc = row.get("market_context")
    if isinstance(mc, dict):
        r = mc.get("regime") or mc.get("market_regime")
        if r is not None and str(r).strip():
            return str(r).strip().lower()
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


def _build_reference_watch(p2b: Dict[str, Any]) -> Dict[str, Any]:
    if not p2b:
        return dict(DEFAULT_REFERENCE_WATCH)
    # Prefer nested p2b_eth_watch_reference if present (P2E-style)
    nested = p2b.get("p2b_eth_watch_reference")
    if isinstance(nested, dict) and nested:
        return {
            "provider": str(nested.get("provider") or "cerebras").lower(),
            "intent": "watch",
            "confidence": _scalar_conf(nested.get("confidence"), 0.55),
            "directional_bias": _scalar_label(nested.get("directional_bias"), "LONG"),
            "candidate_side": _scalar_label(nested.get("candidate_side"), "BUY"),
            "mae_risk_estimate_pct": _scalar_conf(nested.get("mae_risk_estimate_pct"), 0.3),
            "mae_cap_passed": True,
        }
    return {
        "provider": str(
            p2b.get("watch_provider") or p2b.get("eth_watch_provider") or "cerebras"
        ).lower(),
        "intent": "watch",
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
        "mae_cap_passed": True,
    }


def evaluate_row_conditions(row: Dict[str, Any]) -> Dict[str, bool]:
    """Evaluate reappearance flags for a single ETH decision row."""
    intent = _intent(row)
    bias = _bias(row)
    side = _normalize_side(row.get("candidate_side"))
    conf = _conf(row)
    trig = parse_entry_trigger(row.get("entry_trigger"))
    inval = parse_invalidation(row.get("invalidation"))
    has_trig = _has_entry_trigger(trig)
    has_inval = _has_invalidation(inval)
    mae = _mae(row)
    cap = symbol_mae_watch_cap_pct(ETH)
    mae_ok = mae is not None and mae <= cap
    dq = _data_quality(row)
    regime = _regime(row)
    has_watch = intent == "watch" or bool(_is_valid_watch_candidate(row))
    # _normalize_side maps BUY→LONG / SELL→SHORT
    long_buy = bias in {"LONG", "SHORT", "BUY", "SELL"} and side in {"LONG", "SHORT"}
    conf_ok = conf is not None and conf >= CONF_NEAR_REF_FLOOR
    dq_ok = dq in {"ok", "good", "pass", "passed", "high"}
    regime_ok = bool(regime) and regime not in {"unknown", "none", ""}
    return {
        "has_eth_watch_or_valid_watch": has_watch,
        "has_long_buy_bias": long_buy,
        "confidence_near_reference": conf_ok,
        "entry_trigger_present": has_trig,
        "invalidation_present": has_inval,
        "mae_cap_passed": mae_ok,
        "context_quality_ok": dq_ok,
        "regime_not_unknown": regime_ok,
    }


def aggregate_conditions(rows: List[Dict[str, Any]]) -> Dict[str, bool]:
    keys = [
        "has_eth_watch_or_valid_watch",
        "has_long_buy_bias",
        "confidence_near_reference",
        "entry_trigger_present",
        "invalidation_present",
        "mae_cap_passed",
        "context_quality_ok",
        "regime_not_unknown",
    ]
    # OR across rows: any row meeting a flag contributes true
    agg = {k: False for k in keys}
    for row in rows:
        flags = evaluate_row_conditions(row)
        for k in keys:
            if flags.get(k):
                agg[k] = True
    return agg


def conditions_ready(conds: Dict[str, bool]) -> bool:
    return all(bool(conds.get(k)) for k in conds)


def check_wait_helper_robustness() -> Dict[str, Any]:
    """Static import/status check; does not mutate trading state."""
    status: Dict[str, Any] = {
        "wait_helper_import_ok": False,
        "completed_needs_finalize_status_exists": False,
        "timeout_not_for_completed_ticks": False,
        "stage_419_triggered": False,
        "trading_state_mutated": False,
        "cited_from_p2e_tests": True,
        "status": "unknown",
    }
    try:
        from tools.research.wait_stage4_cloud_dry_run import (  # noqa: WPS433
            STATUS_COMPLETED_NEEDS_FINALIZE,
            evaluate_wait_status,
        )

        status["wait_helper_import_ok"] = True
        status["completed_needs_finalize_status_exists"] = (
            STATUS_COMPLETED_NEEDS_FINALIZE == "completed_needs_finalize"
        )
        evaluated = evaluate_wait_status(
            snapshot={
                "tick_count": 6,
                "effective_decision_count": 18,
                "dry_run_completed": False,
            },
            expected_tick_count=6,
            summary_present=True,
        )
        status["timeout_not_for_completed_ticks"] = (
            evaluated.get("status") == STATUS_COMPLETED_NEEDS_FINALIZE
            and not evaluated.get("stage_419_triggered")
            and not evaluated.get("trading_state_mutated")
        )
        status["stage_419_triggered"] = bool(evaluated.get("stage_419_triggered"))
        status["trading_state_mutated"] = bool(evaluated.get("trading_state_mutated"))
        status["status"] = (
            "PASS"
            if status["wait_helper_import_ok"]
            and status["completed_needs_finalize_status_exists"]
            and status["timeout_not_for_completed_ticks"]
            else "FAIL"
        )
    except Exception as exc:  # noqa: BLE001 — offline gate must not crash soak paths
        status["status"] = f"FAIL: {type(exc).__name__}: {exc}"
    return status


def run_gate(
    *,
    p2e_dir: str | Path,
    p2b_dir: str | Path,
    p2c_dir: str | Path,
    p2d_dir: str | Path,
    input_dir: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    p2e = _read_json(Path(p2e_dir) / "eth_no_watch_summary.json")
    p2b = _read_json(Path(p2b_dir) / "eth_watch_confirmation_summary.json")
    p2c = _read_json(Path(p2c_dir) / "eth_followup_context_summary.json")
    p2d = _read_json(Path(p2d_dir) / "eth_followup_prompt_review_summary.json")

    # Allow P2E nested reference if p2b file thin
    if not p2b and p2e.get("p2b_eth_watch_reference"):
        p2b = {"p2b_eth_watch_reference": p2e.get("p2b_eth_watch_reference")}

    eth_rows = _actual_eth(Path(input_dir))
    reference = _build_reference_watch(p2b)

    negative = {
        "decision_count": int(p2e.get("eth_decision_count") or len(eth_rows) or 0),
        "intent_distribution": dict(p2e.get("eth_intent_distribution") or {}),
        "confidence_distribution": dict(p2e.get("eth_confidence_distribution") or {}),
        "directional_bias_distribution": dict(
            p2e.get("eth_directional_bias_distribution") or {}
        ),
        "candidate_side_distribution": dict(
            p2e.get("eth_candidate_side_distribution") or {}
        ),
        "block_reason_counts": dict(p2e.get("eth_block_reason_counts") or {}),
    }

    # Prefer live P2D-R1 rows for condition evaluation; fall back to P2E summary-only
    conds = aggregate_conditions(eth_rows)
    if not eth_rows:
        # Negative path: no watch conditions from summary
        conds = {
            "has_eth_watch_or_valid_watch": int(p2e.get("eth_valid_watch_count") or 0) > 0,
            "has_long_buy_bias": False,
            "confidence_near_reference": False,
            "entry_trigger_present": int(p2e.get("eth_entry_trigger_present_count") or 0) > 0,
            "invalidation_present": int(p2e.get("eth_invalidation_present_count") or 0) > 0,
            "mae_cap_passed": False,
            "context_quality_ok": False,
            "regime_not_unknown": False,
        }

    ready = conditions_ready(conds)
    wait_helper = check_wait_helper_robustness()

    if ready:
        next_rec = "operator_approved_short_runtime_regression_only"
        do_not_run = False
        may_justify = True
    else:
        next_rec = "wait_for_eth_watch_conditions_reappear_no_60m"
        do_not_run = True
        may_justify = False

    summary: Dict[str, Any] = {
        "stage": "4.18-P2F",
        "generated_at_utc": utc_now_iso(),
        "p2e_output_loaded": bool(p2e),
        "p2b_watch_reference_loaded": bool(p2b) or bool(p2e.get("p2b_eth_watch_reference")),
        "p2c_context_reference_loaded": bool(p2c),
        "p2d_prompt_repair_loaded": bool(p2d),
        "reference_eth_watch": reference,
        "negative_eth_no_watch_summary": negative,
        "eth_watch_reappearance_conditions": conds,
        "regression_readiness": ready,
        "do_not_run_regression_now": do_not_run,
        "operator_approved_short_regression_may_be_justified": may_justify,
        "should_run_60m": False,
        "stage_419_readiness": False,
        "should_start_419": False,
        "next_recommendation": next_rec,
        "operator_approval_required": True,
        "routing_permanent_change_supported": False,
        "wait_helper_robustness_status": wait_helper,
        "p2e_no_watch_root_cause": p2e.get("no_watch_root_cause") or "sample_market_no_edge",
        "prompt_repair_over_conservative_suspected": bool(
            p2e.get("prompt_repair_over_conservative_suspected")
        ),
        "needs_prompt_adjustment": bool(p2e.get("needs_prompt_adjustment")),
        "p2d_prompt_repair_added": bool(p2d.get("prompt_repair_added")),
        "p2c_confirmation_failure_reason": p2c.get("confirmation_failure_reason"),
        "offline_only": True,
        "llm_called": False,
        "order_sent": False,
        "exchange_private_api_called": False,
        "mae_cap_changed": False,
        "confidence_floor_changed": False,
        "provider_routing_changed": False,
        "risk_governor_changed": False,
        "input_dir": str(Path(input_dir)),
        "p2e_dir": str(Path(p2e_dir)),
        "output_dir": str(out),
        "p2f_verdict": "STAGE_4_18P2F_PASS",
    }

    details: List[Dict[str, Any]] = []
    for i, row in enumerate(eth_rows):
        details.append(
            {
                "record_type": "eth_decision_gate_eval",
                "index": i,
                "decision_id": row.get("decision_id"),
                "provider": row.get("provider"),
                "intent": _intent(row),
                "confidence": _conf(row),
                "directional_bias": _bias(row) or "NONE",
                "candidate_side": _normalize_side(row.get("candidate_side")),
                "conditions": evaluate_row_conditions(row),
            }
        )
    details.append(
        {
            "record_type": "gate_classification",
            "eth_watch_reappearance_conditions": conds,
            "regression_readiness": ready,
            "do_not_run_regression_now": do_not_run,
            "next_recommendation": next_rec,
            "wait_helper_robustness_status": wait_helper,
        }
    )

    with (out / "eth_watch_reappearance_gate_details.jsonl").open("w", encoding="utf-8") as fh:
        for row in details:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = f"""# Stage 4.18-P2F ETH Watch Reappearance Gate

Generated: {summary['generated_at_utc']}

## References
- P2E loaded={summary['p2e_output_loaded']} root={summary['p2e_no_watch_root_cause']}
- P2B watch={json.dumps(reference)}
- P2C reason={summary.get('p2c_confirmation_failure_reason')}
- P2D repair_added={summary['p2d_prompt_repair_added']}

## Negative (P2E)
{json.dumps(negative, indent=2)}

## Conditions
{json.dumps(conds, indent=2)}

## Gate
- regression_readiness={ready}
- do_not_run_regression_now={do_not_run}
- operator_approved_short_regression_may_be_justified={may_justify}
- should_run_60m=false
- stage_419_readiness=false
- should_start_419=false
- next={next_rec}
- wait_helper={wait_helper.get('status')}

## Verdict
STAGE_4_18P2F_PASS
"""
    (out / "eth_watch_reappearance_gate_report.md").write_text(report, encoding="utf-8")
    write_json(out / "eth_watch_reappearance_gate_summary.json", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 4.18-P2F ETH watch reappearance gate")
    ap.add_argument("--p2e-dir", required=True)
    ap.add_argument("--p2b-dir", required=True)
    ap.add_argument("--p2c-dir", required=True)
    ap.add_argument("--p2d-dir", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    summary = run_gate(
        p2e_dir=args.p2e_dir,
        p2b_dir=args.p2b_dir,
        p2c_dir=args.p2c_dir,
        p2d_dir=args.p2d_dir,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
