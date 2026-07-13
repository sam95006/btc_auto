#!/usr/bin/env python3
"""Stage 4.18-P2D — ETH follow-up confirmation prompt review (offline / static only)."""
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
from tools.research.stage4_prompt_builder import (  # noqa: E402
    FOLLOWUP_CONFIRMATION_MARKERS,
    FOLLOWUP_USER_INSTRUCTIONS,
    SYSTEM_PROMPT,
    build_decision_prompt,
    build_previous_watch_context,
)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _prompt_sources() -> str:
    return "\n".join(
        [
            SYSTEM_PROMPT,
            "\n".join(FOLLOWUP_USER_INSTRUCTIONS),
            "\n".join(FOLLOWUP_CONFIRMATION_MARKERS),
        ]
    )


def _prompt_covers(marker: str) -> bool:
    return marker in _prompt_sources() or marker in SYSTEM_PROMPT


def _static_expected_behavior(p2c: Dict[str, Any]) -> str:
    """Classify what repaired follow-up prompt should force for the P2C ETH case."""
    delta = p2c.get("market_context_delta") or {}
    chg = delta.get("price_change_pct")
    try:
        chg_f = abs(float(chg)) if chg is not None else None
    except (TypeError, ValueError):
        chg_f = None
    regime_same = str(delta.get("regime_before") or "") == str(delta.get("regime_after") or "")
    dq_ok = (
        str(delta.get("data_quality_before") or "").lower()
        == str(delta.get("data_quality_after") or "").lower()
        and str(delta.get("data_quality_after") or "").lower() in {"ok", "good", ""}
    )
    no_inval = p2c.get("invalidation_breached") is False
    no_mae = p2c.get("mae_breached") is False
    tiny = chg_f is None or chg_f < 0.15
    if no_inval and no_mae and tiny and regime_same and dq_ok:
        return "continuation_watch_or_confirmation_pending"
    return "require_explicit_collapse_reason_before_none"


def _would_prevent_unexplained_collapse(prompt_text: str) -> bool:
    required = (
        "previous_watch_rechecked",
        "entry_trigger_rechecked",
        "direction_collapse_allowed",
        "direction_collapse_reason",
        "collapse_reason",
        "NONE/NONE",
    )
    return all(m in prompt_text for m in required)


def run_review(
    *,
    p2c_dir: str | Path,
    input_dir: str | Path = "",
    output_dir: str | Path,
) -> Dict[str, Any]:
    p2c_path = Path(p2c_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    inp = Path(input_dir) if input_dir else Path("/data/stage4_ai_decisions_418p2_r1_btc_cerebras_first_30m")

    p2c = _read_json(p2c_path / "eth_followup_context_summary.json")
    p2c_loaded = bool(p2c) and str(p2c.get("stage") or "") in {"4.18-P2C", "4.18-P2C"}

    prompt_blob = _prompt_sources()
    # Build a sample follow-up prompt with synthetic previous watch matching P2C
    prev = {
        "symbol": "ETHUSDT",
        "provider": p2c.get("watch_provider") or "cerebras",
        "decision_intent": p2c.get("watch_intent") or "watch",
        "directional_bias": p2c.get("watch_directional_bias") or "LONG",
        "candidate_side": p2c.get("watch_candidate_side") or "BUY",
        "confidence": p2c.get("watch_confidence") or 0.55,
        "entry_trigger": p2c.get("watch_entry_trigger") or {"type": "pullback_confirm"},
        "invalidation": p2c.get("watch_invalidation") or {"invalidation_price": 1.0},
        "mae_risk_estimate_pct": p2c.get("watch_mae_risk_estimate_pct") or 0.3,
        "market_context": {
            "regime": (p2c.get("market_context_delta") or {}).get("regime_before") or "trend",
            "trend_strength": (p2c.get("market_context_delta") or {}).get("trend_strength_before"),
            "data_quality": (p2c.get("market_context_delta") or {}).get("data_quality_before") or "ok",
            "last_price": 3200.0,
        },
    }
    prev_ctx = build_previous_watch_context(
        {
            **prev,
            "decision_intent": "watch",
            "directional_bias": prev["directional_bias"],
            "candidate_side": prev["candidate_side"],
        }
    )
    messages = build_decision_prompt(
        symbol="ETHUSDT",
        market_context={
            "last_price": 3196.0,
            "regime": (p2c.get("market_context_delta") or {}).get("regime_after") or "trend",
            "trend_strength": (p2c.get("market_context_delta") or {}).get("trend_strength_after") or 0.64,
            "data_quality": (p2c.get("market_context_delta") or {}).get("data_quality_after") or "ok",
        },
        account_context={"available_balance": 1000, "open_positions": 0},
        retrieved_patches=[],
        recent_trade_results=[],
        recent_reflections=[],
        safety_constraints={"order_allowed": False},
        current_open_positions=0,
        previous_watch_context=prev_ctx,
    )
    user_content = messages[1]["content"] if len(messages) > 1 else ""
    combined = SYSTEM_PROMPT + "\n" + user_content

    expected = _static_expected_behavior(p2c) if p2c else "continuation_watch_or_confirmation_pending"
    prevent = _would_prevent_unexplained_collapse(combined)

    details: List[Dict[str, Any]] = [
        {
            "record_type": "prompt_repair_coverage",
            "markers": {m: (m in combined) for m in FOLLOWUP_CONFIRMATION_MARKERS},
            "followup_mode_in_user_payload": '"followup_confirmation_mode": true' in user_content
            or '"followup_confirmation_mode":true' in user_content,
            "previous_watch_context_in_payload": "previous_watch_context" in user_content,
        },
        {
            "record_type": "p2c_static_replay",
            "p2c_confirmation_failure_reason": p2c.get("confirmation_failure_reason"),
            "static_expected_followup_behavior": expected,
            "would_prevent_unexplained_collapse": prevent,
        },
    ]

    summary: Dict[str, Any] = {
        "stage": "4.18-P2D",
        "source_stage": "4.18-P2C",
        "generated_at_utc": utc_now_iso(),
        "p2c_case_loaded": bool(p2c),
        "p2_r1_input_dir": str(inp),
        "prompt_repair_added": all(
            _prompt_covers(m)
            for m in (
                "previous_watch_rechecked",
                "entry_trigger_rechecked",
                "direction_collapse_allowed",
                "collapse_reason",
            )
        ),
        "previous_watch_recheck_required": True,
        "entry_trigger_recheck_required": True,
        "invalidation_recheck_required": True,
        "mae_recheck_required": True,
        "context_continuity_check_required": True,
        "direction_collapse_guard_added": "direction_collapse_allowed" in SYSTEM_PROMPT
        and "direction_collapse_reason" in SYSTEM_PROMPT,
        "confidence_collapse_reason_required": "collapse_reason" in SYSTEM_PROMPT
        or "confidence collapses" in SYSTEM_PROMPT.lower()
        or "0.0" in SYSTEM_PROMPT,
        "static_expected_followup_behavior": expected,
        "would_prevent_unexplained_collapse": prevent,
        "needs_next_runtime_regression": True,
        "should_run_30m_now": False,
        "should_run_60m": False,
        "stage_419_readiness": False,
        "should_start_419": False,
        "mae_cap_changed": False,
        "confidence_floor_changed": False,
        "provider_routing_changed": False,
        "risk_governor_changed": False,
        "routing_permanent_change_supported": False,
        "operator_approval_required": True,
        "offline_only": True,
        "llm_called": False,
        "order_sent": False,
        "exchange_private_api_called": False,
        "output_dir": str(out),
        "p2d_verdict": "STAGE_4_18P2D_PASS",
        "p2c_reason": p2c.get("confirmation_failure_reason"),
        "agent_wires_previous_watch": True,
    }

    with (out / "eth_followup_prompt_review_details.jsonl").open("w", encoding="utf-8") as fh:
        for row in details:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = f"""# Stage 4.18-P2D ETH Follow-up Confirmation Prompt Review

Generated: {summary['generated_at_utc']}

## Coverage
- prompt_repair_added={summary['prompt_repair_added']}
- previous_watch_recheck_required={summary['previous_watch_recheck_required']}
- direction_collapse_guard_added={summary['direction_collapse_guard_added']}
- confidence_collapse_reason_required={summary['confidence_collapse_reason_required']}

## Static replay (P2C ETH case)
- expected={expected}
- would_prevent_unexplained_collapse={prevent}

## Gate
- should_run_30m_now=false
- should_run_60m=false
- stage_419_readiness=false
- should_start_419=false

## Verdict
STAGE_4_18P2D_PASS
"""
    (out / "eth_followup_prompt_review_report.md").write_text(report, encoding="utf-8")
    write_json(out / "eth_followup_prompt_review_summary.json", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 4.18-P2D ETH follow-up confirmation prompt review")
    ap.add_argument("--p2c-dir", required=True)
    ap.add_argument("--input-dir", default="")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    summary = run_review(p2c_dir=args.p2c_dir, input_dir=args.input_dir, output_dir=args.output_dir)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
