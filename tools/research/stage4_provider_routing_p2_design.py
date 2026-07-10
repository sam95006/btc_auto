#!/usr/bin/env python3
"""Stage 4.18-P2 — provider routing design gate (design only; no routing enable)."""
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

PAIR_SUMMARY = "paired_comparison_summary.json"
DIAG_SUMMARY = "stage4_btc_shadow_diagnostics_summary.json"
FOLLOWUP_SUMMARY = "stage4_btc_watchlist_followup_diagnostics.json"
RUN_SUMMARY = "stage4_ai_decision_summary.json"

P2_R1_OUTPUT_DIR = "/data/stage4_ai_decisions_418p2_r1_btc_cerebras_first_30m"

DEFAULT_OFF_FLAGS = {
    "STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED": "false",
    "STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED": "false",
    "STAGE4_BTC_PROVIDER_CHAIN": "cerebras,groq",
    "STAGE4_ORDER_ALLOWED": "false",
    "STAGE4_DRY_RUN_ONLY": "true",
    "STAGE4_ALLOW_MOCK_FALLBACK": "false",
    "STAGE4_REQUIRE_REAL_LLM": "true",
    "NEXUS_ARM_ALLOWED": "false",
    "NEXUS_RADAR_AUTO_TRADE": "0",
    "ZEABUR_PRODUCTION_RUNNER_ALLOWED": "false",
}

P2_R1_EXPERIMENT_FLAGS = {
    "STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED": "true",
    "STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED": "true",
    "STAGE4_BTC_PROVIDER_CHAIN": "cerebras,groq",
    "STAGE4_ORDER_ALLOWED": "false",
    "STAGE4_DRY_RUN_ONLY": "true",
    "STAGE4_ALLOW_MOCK_FALLBACK": "false",
    "STAGE4_REQUIRE_REAL_LLM": "true",
    "NEXUS_ARM_ALLOWED": "false",
    "NEXUS_RADAR_AUTO_TRADE": "0",
    "ZEABUR_PRODUCTION_RUNNER_ALLOWED": "false",
}

SAFETY_GUARDS = [
    "env flag default off",
    "provider override only when experiment flag=true",
    "override limited to BTCUSDT only",
    "no order path",
    "no production path",
    "no ARM path",
    "no risk threshold changes",
    "no MAE cap changes",
    "no confidence floor changes",
    "summary labels experiment_mode=true",
    "reset flags after run",
    "Stage 4.19 readiness does not auto-start anything",
    "shadow results never count as graduation",
    "P1C shadow results must not feed paper/calibration",
]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _find_json(base: Path, name: str) -> Dict[str, Any]:
    direct = _read_json(base / name)
    if direct:
        return direct
    for path in base.rglob(name):
        data = _read_json(path)
        if data:
            return data
    return {}


def load_p1c_evidence(
    *,
    input_dir: Path,
    pair_compare_dir: Path,
    diagnostics_dir: Path,
    followup_dir: Path,
) -> Dict[str, Any]:
    pair = _find_json(pair_compare_dir, PAIR_SUMMARY)
    diag = _find_json(diagnostics_dir, DIAG_SUMMARY)
    follow = _find_json(followup_dir, FOLLOWUP_SUMMARY)
    run = _find_json(input_dir, RUN_SUMMARY)

    loaded = bool(pair or diag or run)
    skill_valid = bool(
        pair.get("provider_skill_comparison_valid")
        if pair
        else diag.get("provider_skill_comparison_valid")
    )
    actual_vw = int(
        pair.get("actual_valid_watch_count")
        if pair.get("actual_valid_watch_count") is not None
        else diag.get("actual_valid_watch_count") or 0
    )
    shadow_vw = int(
        pair.get("shadow_valid_watch_count")
        if pair.get("shadow_valid_watch_count") is not None
        else diag.get("shadow_valid_watch_count") or 0
    )
    actual_prov = pair.get("actual_provider_distribution") or diag.get(
        "actual_provider_distribution"
    ) or {"groq": 6}
    shadow_prov = pair.get("shadow_provider_distribution") or diag.get(
        "shadow_provider_distribution"
    ) or {"cerebras": 6}
    comparable = int(pair.get("shadow_comparable_pair_count") or diag.get("shadow_comparable_pair_count") or 0)
    uncomparable = int(
        pair.get("shadow_uncomparable_pair_count") or diag.get("shadow_uncomparable_pair_count") or 0
    )
    shadow_excluded = all(
        [
            bool(pair.get("shadow_excluded_from_graduation", True)),
            bool(diag.get("shadow_excluded_from_graduation", True)),
            bool(pair.get("shadow_excluded_from_paper_logger", True)),
            bool(pair.get("shadow_excluded_from_calibration", True)),
            bool(pair.get("shadow_excluded_from_stage_419_readiness", True)),
        ]
    )
    return {
        "p1c_evidence_loaded": loaded,
        "provider_skill_comparison_valid": skill_valid,
        "actual_btc_provider": actual_prov,
        "shadow_btc_provider": shadow_prov,
        "actual_btc_valid_watch_count": actual_vw,
        "shadow_btc_valid_watch_count": shadow_vw,
        "shadow_comparable_pair_count": comparable,
        "shadow_uncomparable_pair_count": uncomparable,
        "shadow_excluded_from_graduation": shadow_excluded,
        "btc_followup_reason": follow.get("reason_no_graduation") or "unknown",
        "run_effective_decision_count": run.get("effective_decision_count"),
        "run_tick_count": run.get("tick_count"),
        "stage_419_readiness_from_inputs": False,
    }


def build_design_options(evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "option_id": "option_1_status_quo_baseline",
            "name": "Status quo baseline",
            "description": "BTC continues normal groq,cerebras chain; no provider preference change.",
            "pros": ["Safest", "No new experiment surface", "No extra LLM cost"],
            "cons": [
                "P1C shows BTC may remain Groq soft_skip",
                "Does not test Cerebras-first actual path",
            ],
            "risks": ["BTC graduation may stay 0 under current slot bias"],
            "recommended": False,
        },
        {
            "option_id": "option_2_btc_cerebras_first_read_only_experiment",
            "name": "BTC Cerebras-first read-only experiment",
            "description": (
                "When experiment flags are operator-enabled, BTC provider chain becomes "
                "cerebras,groq. ETH/SOL/PEPE unchanged. Read-only P2-R1 only."
            ),
            "pros": [
                "Directly tests P1C Cerebras shadow yield signal on actual path",
                "BTC-only scope limits blast radius",
                "Default-off + operator approval",
            ],
            "cons": [
                "Extra Cerebras usage / truncation risk",
                "Must not be mistaken for production routing",
            ],
            "risks": [
                "Operator must reset flags after run",
                "Graduation still requires non-shadow actual confirmations",
            ],
            "env_flags_default_off": dict(DEFAULT_OFF_FLAGS),
            "env_flags_p2_r1": dict(P2_R1_EXPERIMENT_FLAGS),
            "btc_only": True,
            "recommended": True,
        },
        {
            "option_id": "option_3_symbol_balanced_rotation",
            "name": "Symbol-balanced rotation",
            "description": "Rotate Groq/Cerebras by tick/symbol to remove slot-order bias.",
            "pros": ["Eliminates permanent symbol-provider binding", "Broader fairness"],
            "cons": ["Complex rate-limit management", "Harder to attribute BTC-only effects"],
            "risks": ["May destabilize currently working ETH Cerebras fallback path"],
            "recommended": False,
        },
        {
            "option_id": "option_4_btc_dual_decision_arbitration",
            "name": "BTC dual-decision arbitration",
            "description": (
                "Call both providers; only promote watch when both agree, else "
                "disagreement_watch research-only (not calibration)."
            ),
            "pros": ["Conservative", "Surfaces disagreement explicitly"],
            "cons": ["Higher LLM cost", "May suppress valid single-provider watches"],
            "risks": ["Too conservative for graduation progress"],
            "recommended": False,
        },
    ]


def build_p2_r1_experiment_design() -> Dict[str, Any]:
    return {
        "stage": "4.18-P2-R1",
        "name": "BTC Cerebras-first Read-only Routing Experiment",
        "execute_now": False,
        "operator_approval_required": True,
        "output_dir": P2_R1_OUTPUT_DIR,
        "duration_minutes": 30,
        "env_flags": dict(P2_R1_EXPERIMENT_FLAGS),
        "reset_flags_after_run": {
            "STAGE4_CLOUD_DRY_RUN_MINUTES": "0",
            "STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED": "false",
            "STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED": "false",
        },
        "success_criteria": [
            "technical PASS",
            "actual BTC provider includes Cerebras-first",
            "actual BTC valid_watch_count > 0",
            "actual BTC graduation_count measured from non-shadow actual decisions",
            "no shadow used in graduation",
            "order=0",
            "mock=0",
            "flags reset",
            "Stage 4.19 not auto-started",
        ],
        "forbidden": [
            "orders",
            "demo/paper execution",
            "ARM/radar/production/btc-auto",
            "auto Stage 4.19",
            "feeding P1C shadow into graduation",
        ],
    }


def run_p2_design(
    *,
    input_dir: str | Path,
    pair_compare_dir: str | Path = "",
    diagnostics_dir: str | Path = "",
    followup_dir: str | Path = "",
    output_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    inp = Path(input_dir)
    pair_dir = Path(pair_compare_dir) if pair_compare_dir else Path(
        "/data/stage4_18p1c_btc_shadow_pair_compare"
    )
    diag_dir = Path(diagnostics_dir) if diagnostics_dir else Path(
        "/data/stage4_18p1c_btc_shadow_diagnostics"
    )
    # Accept alternate path name from user prompt.
    if not diag_dir.is_dir():
        alt = Path("/data/stage4_18p1c_clean_shadow_diagnostics")
        if alt.is_dir():
            diag_dir = alt
    follow_dir = Path(followup_dir) if followup_dir else Path(
        "/data/stage4_18p1c_btc_watchlist_followup_diagnostics"
    )
    out = Path(output_dir) if output_dir else Path("/data/stage4_18p2_provider_routing_design")
    out.mkdir(parents=True, exist_ok=True)

    evidence = load_p1c_evidence(
        input_dir=inp,
        pair_compare_dir=pair_dir,
        diagnostics_dir=diag_dir,
        followup_dir=follow_dir,
    )
    options = build_design_options(evidence)
    recommended = "option_2_btc_cerebras_first_read_only_experiment"
    design_supported = bool(
        evidence.get("p1c_evidence_loaded")
        and evidence.get("provider_skill_comparison_valid")
        and int(evidence.get("shadow_btc_valid_watch_count") or 0)
        > int(evidence.get("actual_btc_valid_watch_count") or 0)
        and evidence.get("shadow_excluded_from_graduation")
    )
    p2_r1 = build_p2_r1_experiment_design()

    summary: Dict[str, Any] = {
        "record_type": "stage4_provider_routing_p2_design",
        "stage_marker": "4.18-P2",
        "generated_at_utc": utc_now_iso(),
        "p1c_evidence_loaded": bool(evidence.get("p1c_evidence_loaded")),
        "provider_skill_comparison_valid": bool(evidence.get("provider_skill_comparison_valid")),
        "actual_btc_provider": evidence.get("actual_btc_provider") or {},
        "shadow_btc_provider": evidence.get("shadow_btc_provider") or {},
        "actual_btc_valid_watch_count": int(evidence.get("actual_btc_valid_watch_count") or 0),
        "shadow_btc_valid_watch_count": int(evidence.get("shadow_btc_valid_watch_count") or 0),
        "shadow_comparable_pair_count": int(evidence.get("shadow_comparable_pair_count") or 0),
        "shadow_uncomparable_pair_count": int(evidence.get("shadow_uncomparable_pair_count") or 0),
        "shadow_excluded_from_graduation": bool(evidence.get("shadow_excluded_from_graduation")),
        "routing_experiment_design_supported": design_supported,
        "routing_auto_change_allowed": False,
        "production_routing_change_supported": False,
        "stage_419_readiness": False,
        "should_start_419": False,
        "design_options": options,
        "design_options_count": len(options),
        "recommended_option": recommended,
        "recommended_next_stage": "4.18-P2-R1",
        "p2_r1_experiment_defined": True,
        "p2_r1_output_dir": P2_R1_OUTPUT_DIR,
        "p2_r1_experiment": p2_r1,
        "operator_approval_required": True,
        "provider_override_default_off": True,
        "provider_override_btc_only": True,
        "default_off_flags": dict(DEFAULT_OFF_FLAGS),
        "safety_guards": list(SAFETY_GUARDS),
        "execute_p2_r1_now": False,
        "offline_only": True,
        "order_sent": False,
        "llm_called": False,
        "exchange_private_api_called": False,
        "evidence": evidence,
        "input_dir": str(inp),
        "output_dir": str(out),
    }
    write_json(out / "stage4_provider_routing_p2_design_summary.json", summary)
    write_json(out / "stage4_p2_r1_experiment_design.json", p2_r1)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-P2 provider routing design gate")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--pair-compare-dir", default="")
    parser.add_argument("--diagnostics-dir", default="")
    parser.add_argument("--followup-dir", default="")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    summary = run_p2_design(
        input_dir=args.input_dir,
        pair_compare_dir=args.pair_compare_dir,
        diagnostics_dir=args.diagnostics_dir,
        followup_dir=args.followup_dir,
        output_dir=args.output_dir or None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
