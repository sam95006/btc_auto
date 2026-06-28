"""Stage 4 LLM prompt builder for structured trading decisions (dry-run)."""
from __future__ import annotations

import json
from typing import Any, Dict, List

SYSTEM_PROMPT = """You are a Stage 4 trading decision assistant for Bybit demo/testnet research only.
You MUST respond with a single JSON object only. No markdown, no prose outside JSON.
You MUST NOT suggest changing safety caps: max_margin_usd, max_leverage, max_open_positions, stop_loss, max_hold.
You MUST NOT recommend mainnet, real money, production, or ARM.
Allowed final_action values: enter, skip.
Allowed candidate_side values: BUY, SELL, NONE.
Allowed decision_intent values: hard_skip, soft_skip, watch, enter_candidate.
confidence must be a number between 0 and 1.
This is dry-run only — your output will NOT place orders; Risk Supervisor will review.

Confidence calibration:
- 0.00–0.10: hard_skip (missing data / blocked / no edge)
- 0.10–0.30: soft_skip or watch (some signal, insufficient to enter)
- 0.30–0.55: watch or soft_skip (weak edge)
- 0.55–0.75: enter_candidate (needs supervisor; still may skip)
- >0.75: high conviction enter_candidate (still no auto order)

Use decision_intent to explain skip vs watch vs enter_candidate. Do NOT always use confidence=0.0."""

OUTPUT_SCHEMA_HINT = {
    "final_action": "enter|skip",
    "decision_intent": "hard_skip|soft_skip|watch|enter_candidate",
    "symbol": "ETHUSDT",
    "candidate_side": "BUY|SELL|NONE",
    "confidence": 0.0,
    "why_enter": "",
    "why_skip": "",
    "side_reason": "",
    "confidence_reason": "",
    "missing_data": [],
    "edge_factors": [],
    "risk_factors": [],
    "risk_notes": [],
    "patch_awareness": "",
    "uncertainty": "",
    "requires_manual_review": False,
}


def build_decision_prompt(
    *,
    symbol: str,
    market_context: Dict[str, Any],
    account_context: Dict[str, Any],
    retrieved_patches: List[Dict[str, Any]],
    recent_trade_results: List[Dict[str, Any]],
    recent_reflections: List[Dict[str, Any]],
    safety_constraints: Dict[str, Any],
    current_open_positions: int,
) -> List[Dict[str, str]]:
    user_payload = {
        "task": "stage4_dry_run_decision",
        "symbol": symbol.upper(),
        "market_context": market_context,
        "account_context": account_context,
        "retrieved_patches": retrieved_patches,
        "recent_trade_results": recent_trade_results,
        "recent_reflections": recent_reflections,
        "safety_constraints": safety_constraints,
        "current_open_positions": current_open_positions,
        "required_output_schema": OUTPUT_SCHEMA_HINT,
        "instructions": [
            "Classify with decision_intent: hard_skip | soft_skip | watch | enter_candidate.",
            "Use market_context.regime, trend_15m, change_24h_pct, volatility_15m when available.",
            "If data_quality is partial/error, list gaps in missing_data and prefer hard_skip or soft_skip with calibrated confidence.",
            "Recommend enter only if edge is clear and patches do not block reentry.",
            "If active patch action is block_reentry or manual_review_required, use hard_skip.",
            "If uncertain but some signal exists, use watch or soft_skip with confidence 0.10–0.40, not always 0.0.",
        ],
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def prompt_fingerprint(messages: List[Dict[str, str]]) -> str:
    import hashlib

    blob = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
