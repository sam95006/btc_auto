#!/usr/bin/env python3
"""Stage 4.18-P — provider routing design gate (design only, no routing changes)."""
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

O2_SUMMARY_NAME = "stage4_provider_routing_diagnostics_summary.json"
O3_SUMMARY_NAME = "stage4_controlled_provider_probe_summary.json"

REQUIRED_SAFEGUARDS = [
    "shadow_provider_decision excluded from paper logger",
    "shadow_provider_decision excluded from calibration",
    "shadow_provider_decision excluded from graduation",
    "shadow_provider_decision does not replace actual decision",
    "shadow_provider_decision does not trigger order path",
    "STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED defaults false",
    "STAGE4_BTC_DUAL_PROVIDER_SHADOW defaults false",
    "Stage 4.19 readiness must not use shadow results",
]

DEFAULT_ENV_FLAGS = {
    "STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED": "false",
    "STAGE4_BTC_DUAL_PROVIDER_SHADOW": "false",
    "STAGE4_ORDER_ALLOWED": "false",
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _build_design_options() -> List[Dict[str, Any]]:
    return [
        {
            "option_id": "option_1_status_quo",
            "name": "Status quo — groq,cerebras chain",
            "description": "Maintain current provider chain; Groq primary, Cerebras on rate-limit fallback.",
            "provider_chain": "groq,cerebras",
            "pros": [
                "Minimal code change",
                "Proven in N-R2 for ETH/PEPE valid_watch via Cerebras fallback",
                "No new LLM cost beyond current soak",
            ],
            "cons": [
                "BTC/SOL always consume Groq primary slot per tick",
                "ETH/PEPE receive Cerebras only after groq_rate_limited",
                "Routing asymmetry may persist indefinitely",
            ],
            "risks": [
                "BTC graduation may remain 0 under slot-order bias",
                "valid_watch yield correlates with symbol processing order",
            ],
            "suitable_as_final": False,
            "suitable_as_baseline": True,
        },
        {
            "option_id": "option_2_symbol_balanced_rotation",
            "name": "Symbol-balanced provider rotation",
            "description": (
                "Alternate primary provider per symbol each tick "
                "(odd tick: BTC Groq / ETH Cerebras; even tick: reversed)."
            ),
            "provider_chain": "rotating per symbol per tick",
            "pros": [
                "Eliminates permanent symbol-to-provider binding",
                "BTC and ETH both see Groq and Cerebras over time",
                "Addresses slot-order bias directly",
            ],
            "cons": [
                "Increases Groq rate-limit management complexity",
                "Requires tick-index-aware routing state",
                "Provider result stability needs P1-R1 regression soak",
            ],
            "risks": [
                "Rotation may destabilize ETH path that currently works",
                "Higher operational complexity without shadow validation first",
            ],
            "suitable_as_final": False,
            "suitable_as_gated_experiment": True,
        },
        {
            "option_id": "option_3_btc_dual_provider_shadow",
            "name": "BTC diagnostic dual-provider shadow mode",
            "description": (
                "Primary routing unchanged; BTC additionally runs shadow provider call. "
                "Shadow output is diagnostic-only — never paper/calibration/graduation."
            ),
            "provider_chain": "primary unchanged + BTC shadow secondary",
            "pros": [
                "Safest path to measure ongoing BTC provider divergence",
                "Does not alter actual decision or order path",
                "Builds evidence before any routing experiment",
                "Aligns with O3 controlled probe findings",
            ],
            "cons": [
                "Extra LLM call cost per BTC tick when enabled",
                "Shadow must be strictly isolated to avoid graduation contamination",
            ],
            "risks": [
                "Shadow results could be misused if guards are bypassed",
                "Operator must enforce env flags before any soak",
            ],
            "suitable_as_final": False,
            "suitable_as_p1_implementation": True,
            "env_flags": {
                "STAGE4_BTC_DUAL_PROVIDER_SHADOW": "true (operator only)",
                "STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED": "true (operator only)",
            },
        },
        {
            "option_id": "option_4_cerebras_first_btc",
            "name": "Cerebras-first BTC candidate mode",
            "description": "BTC provider chain = cerebras,groq; other symbols unchanged.",
            "provider_chain": "BTC: cerebras,groq; others: groq,cerebras",
            "pros": [
                "Directly tests whether BTC can produce valid_watch under Cerebras-first",
                "O3 showed Cerebras valid_watch possible on frozen BTC context",
            ],
            "cons": [
                "Material routing change — not suitable without gated experiment",
                "Risk of provider-specific overfitting to O3 sample (1/3 valid_watch)",
                "May increase Cerebras quota pressure",
            ],
            "risks": [
                "Could force BTC watch yield without confirming market edge",
                "Bypasses shadow evidence collection phase",
                "Must not become production default without operator sign-off",
            ],
            "suitable_as_final": False,
            "suitable_as_gated_experiment_only": True,
        },
    ]


def _infer_problem_flags(
    o2: Dict[str, Any],
    o3: Dict[str, Any],
    nr2_provider_by_symbol: Optional[Dict[str, Any]] = None,
) -> Dict[str, bool]:
    counterfactual = o2.get("counterfactual_notes") or {}
    btc_sym = nr2_provider_by_symbol or o2.get("provider_by_symbol") or {}
    btc_never_cerebras = bool(
        counterfactual.get("btc_never_reached_cerebras")
        or (btc_sym.get("BTCUSDT", {}).get("cerebras", 0) == 0 and btc_sym.get("BTCUSDT", {}).get("groq", 0) > 0)
    )
    groq_vw = o2.get("valid_watch_by_provider") or {}
    groq_zero = int(groq_vw.get("groq", 0)) == 0 and int(groq_vw.get("cerebras", 0) or 0) > 0
    cerebras_only = bool(counterfactual.get("cerebras_only_valid_watch_source")) or (
        int(groq_vw.get("groq", 0)) == 0 and int(groq_vw.get("cerebras", 0)) > 0
    )
    o3_divergence = bool(o3.get("provider_divergence_detected"))
    routing_problem = bool(
        o2.get("routing_asymmetry_detected")
        and o2.get("routing_asymmetry_likely_affected_btc")
        and o3_divergence
    )
    return {
        "routing_problem_confirmed": routing_problem,
        "btc_never_reached_cerebras": btc_never_cerebras,
        "groq_zero_valid_watch_observed": groq_zero,
        "cerebras_only_valid_watch_source": cerebras_only,
        "o3_provider_divergence_confirmed": o3_divergence,
    }


def _recommend_option(problem_flags: Dict[str, bool], o3: Dict[str, Any]) -> str:
    if problem_flags.get("routing_problem_confirmed") and problem_flags.get("o3_provider_divergence_confirmed"):
        return "option_3_btc_dual_provider_shadow"
    if problem_flags.get("routing_problem_confirmed"):
        return "option_3_btc_dual_provider_shadow"
    return "option_1_status_quo"


def analyze_provider_routing_design(
    *,
    decisions_dir: Optional[str | Path] = None,
    o2_dir: str | Path,
    o3_dir: str | Path,
    output_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    o2_path = Path(o2_dir)
    o3_path = Path(o3_dir)
    o2 = _read_json(o2_path / O2_SUMMARY_NAME)
    o3 = _read_json(o3_path / O3_SUMMARY_NAME)

    nr2_provider_by_symbol: Dict[str, Any] = {}
    if decisions_dir:
        dec_path = Path(decisions_dir)
        # optional lightweight read from O2 if decisions dir missing
        nr2_provider_by_symbol = o2.get("provider_by_symbol") or {}

    problem_flags = _infer_problem_flags(o2, o3, nr2_provider_by_symbol)
    design_options = _build_design_options()
    recommended = _recommend_option(problem_flags, o3)

    why_not_force = (
        "O3 showed Cerebras valid_watch on only 1/3 BTC contexts; context 2 both providers skip. "
        "Forcing BTC watch would bypass market-edge validation and graduation integrity. "
        "Shadow/diagnostic paths must not promote eligibility."
    )
    why_not_419 = (
        "Stage 4.19 requires BTC + ETH graduation > 0 from non-shadow production decisions. "
        "BTC graduation=0 in N-R2; routing design not yet implemented; operator approval pending."
    )

    p1_recommended = recommended == "option_3_btc_dual_provider_shadow" and problem_flags.get(
        "routing_problem_confirmed"
    )

    summary: Dict[str, Any] = {
        "record_type": "stage4_provider_routing_design",
        "stage_marker": "4.18-P",
        "generated_at_utc": utc_now_iso(),
        "input_decisions_dir": str(decisions_dir) if decisions_dir else None,
        "input_o2_dir": str(o2_path),
        "input_o3_dir": str(o3_path),
        **problem_flags,
        "design_options": design_options,
        "design_options_count": len(design_options),
        "recommended_option": recommended,
        "recommended_option_name": next(
            (o["name"] for o in design_options if o["option_id"] == recommended),
            recommended,
        ),
        "recommended_next_stage": "Stage 4.18-P1" if p1_recommended else "remain_at_gate",
        "why_not_force_btc_watch": why_not_force,
        "why_not_start_419": why_not_419,
        "requires_operator_approval": True,
        "required_safeguards": REQUIRED_SAFEGUARDS,
        "default_env_flags": DEFAULT_ENV_FLAGS,
        "shadow_excluded_from_paper_logger": True,
        "shadow_excluded_from_calibration": True,
        "shadow_excluded_from_graduation": True,
        "provider_routing_experiment_default_off": True,
        "p1_decision": {
            "should_implement_p1": p1_recommended,
            "p1_scope": "diagnostic-only BTC dual-provider shadow mode" if p1_recommended else "",
            "should_run_soak_after_p1": False,
            "should_start_419": False,
        },
        "stage_419_readiness": False,
        "o2_routing_asymmetry_summary": o2.get("routing_asymmetry_summary") or "",
        "o3_recommendation": o3.get("recommendation") or "",
        "o3_groq_valid_watch_count": o3.get("groq_valid_watch_count"),
        "o3_cerebras_valid_watch_count": o3.get("cerebras_valid_watch_count"),
        "design_only": True,
        "routing_changes_applied": False,
        "llm_providers_called": False,
        "order_sent": False,
        "exchange_private_api_called": False,
        "production_touched": False,
        "btc_auto_touched": False,
        "mock_ai_used_count": 0,
        "order_sent_count": 0,
    }

    out = Path(output_dir) if output_dir else Path(o2_path).parent / "stage4_18p_provider_routing_design"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage4_provider_routing_design_summary.json", summary)
    write_json(
        out / "stage4_provider_routing_design_options.json",
        {"design_options": design_options, "recommended_option": recommended},
    )
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-P provider routing design gate")
    parser.add_argument("--decisions-dir", default="")
    parser.add_argument("--o2-dir", required=True)
    parser.add_argument("--o3-dir", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    summary = analyze_provider_routing_design(
        decisions_dir=args.decisions_dir or None,
        o2_dir=args.o2_dir,
        o3_dir=args.o3_dir,
        output_dir=args.output_dir or None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
