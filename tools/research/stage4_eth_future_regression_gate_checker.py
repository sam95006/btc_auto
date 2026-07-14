#!/usr/bin/env python3
"""Stage 4.18-P2H — Passive ETH future regression gate checker (HOLD state).

Code-only / docs-only. Does NOT start soaks, mutate trading state, or auto-start
Stage 4.19. Evaluates a future Stage4 output directory and tells the operator
whether a short regression *may be justified* — never launches it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_eth_watch_reappearance_gate import (  # noqa: E402
    CONF_NEAR_REF_FLOOR,
    ETH,
    _actual_eth,
    _conf,
    aggregate_conditions,
    conditions_ready,
    evaluate_row_conditions,
)
from tools.research.stage4_provider_routing_config import is_shadow_decision_row  # noqa: E402

BACKEND_HOLD_STATE = "HOLD"
HOLD_REASON = "ETH watch conditions not present"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_optional_side_outputs(input_dir: Path) -> Dict[str, Any]:
    """Best-effort presence flags for paper/calibration artifacts (read-only)."""
    names = [
        "hypothetical_entry_log.jsonl",
        "paper_entry_log.jsonl",
        "calibration_summary.json",
        "watchlist_followup_summary.json",
        "stage4_paper_logger_summary.json",
    ]
    found = {n: (input_dir / n).is_file() for n in names}
    return {"side_outputs_present": found, "any_side_output": any(found.values())}


def check_future_output(
    *,
    input_dir: str | Path,
    output_dir: str | Path = "",
    hold_state: str = BACKEND_HOLD_STATE,
) -> Dict[str, Any]:
    """Evaluate future Stage4 output for ETH reappearance; never auto-starts runs."""
    inp = Path(input_dir)
    summary_path = inp / "stage4_ai_decision_summary.json"
    run_sum = _read_json(summary_path)
    eth_rows = _actual_eth(inp) if inp.is_dir() else []
    loaded = bool(run_sum) or bool(eth_rows) or (inp / "ai_decisions.jsonl").is_file()

    conds = aggregate_conditions(eth_rows) if eth_rows else {
        "has_eth_watch_or_valid_watch": False,
        "has_long_buy_bias": False,
        "confidence_near_reference": False,
        "entry_trigger_present": False,
        "invalidation_present": False,
        "mae_cap_passed": False,
        "context_quality_ok": False,
        "regime_not_unknown": False,
    }
    reappeared = bool(eth_rows) and conditions_ready(conds)

    if not loaded:
        reason = "future_output_missing_or_unreadable"
        next_rec = "continue_hold_no_regression"
        may_justify = False
    elif not reappeared:
        reason = HOLD_REASON
        next_rec = "continue_hold_no_regression"
        may_justify = False
    else:
        reason = "ETH watch/valid_watch conditions reappeared in future output"
        next_rec = "operator_may_approve_short_regression"
        may_justify = True

    result: Dict[str, Any] = {
        "stage": "4.18-P2H",
        "generated_at_utc": utc_now_iso(),
        "backend_hold_state": hold_state if not reappeared else "HOLD_READY_FOR_OPERATOR",
        "future_output_loaded": loaded,
        "future_output_dir": str(inp),
        "eth_decision_count": len(eth_rows),
        "eth_watch_conditions": conds,
        "eth_watch_conditions_reappeared": reappeared,
        "operator_approved_short_regression_may_be_justified": may_justify,
        "should_run_30m_now": False,
        "should_run_60m": False,
        "stage_419_readiness": False,
        "should_start_419": False,
        "auto_start_regression": False,
        "auto_start_419": False,
        "routing_permanent_change_supported": False,
        "reason": reason,
        "next_recommendation": next_rec,
        "confidence_floor_reference": CONF_NEAR_REF_FLOOR,
        "symbol": ETH,
        "run_summary_present": bool(run_sum),
        "tick_count": int(run_sum.get("tick_count") or 0),
        "effective_decision_count": int(run_sum.get("effective_decision_count") or 0),
        "side_outputs": _read_optional_side_outputs(inp) if inp.is_dir() else {},
        "offline_only": True,
        "llm_called": False,
        "order_sent": False,
        "exchange_private_api_called": False,
        "trading_state_mutated": False,
        "p2h_verdict": "STAGE_4_18P2H_PASS",
    }

    # Per-row details for audit (actual ETH only)
    details: List[Dict[str, Any]] = []
    for i, row in enumerate(eth_rows):
        if is_shadow_decision_row(row):
            continue
        details.append(
            {
                "record_type": "eth_future_gate_eval",
                "index": i,
                "decision_id": row.get("decision_id"),
                "provider": row.get("provider"),
                "intent": row.get("decision_intent") or row.get("intent"),
                "confidence": _conf(row),
                "conditions": evaluate_row_conditions(row),
            }
        )
    details.append(
        {
            "record_type": "future_gate_classification",
            "eth_watch_conditions_reappeared": reappeared,
            "next_recommendation": next_rec,
            "should_run_30m_now": False,
            "should_run_60m": False,
            "should_start_419": False,
        }
    )

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "eth_future_regression_gate_summary.json", result)
        with (out / "eth_future_regression_gate_details.jsonl").open(
            "w", encoding="utf-8"
        ) as fh:
            for row in details:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        report = f"""# Stage 4.18-P2H Passive Gate Check

Generated: {result['generated_at_utc']}
Input: {inp}

## Hold
- backend_hold_state={result['backend_hold_state']}
- eth_watch_conditions_reappeared={reappeared}
- may_justify_short_regression={may_justify}
- should_run_30m_now=false
- should_run_60m=false
- should_start_419=false
- auto_start_*=false

## Conditions
{json.dumps(conds, indent=2)}

## Recommendation
{next_rec}

## Verdict
STAGE_4_18P2H_PASS
"""
        (out / "eth_future_regression_gate_report.md").write_text(report, encoding="utf-8")
        result["output_dir"] = str(out)

    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Stage 4.18-P2H passive ETH future regression gate checker"
    )
    ap.add_argument("--input-dir", required=True, help="Future Stage4 output directory")
    ap.add_argument("--output-dir", default="", help="Optional gate output directory")
    args = ap.parse_args()
    summary = check_future_output(input_dir=args.input_dir, output_dir=args.output_dir)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
