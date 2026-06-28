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

Confidence calibration (use decision_intent consistently):
- hard_skip (0.00–0.15): data error, patch block, high risk, no edge
- soft_skip (0.15–0.35): no clear edge, flat or weak context
- watch (0.30–0.55): weak signal worth monitoring, not enough to enter
- enter_candidate (0.55–0.75): preliminary edge, still needs supervisor review

Use market_context.regime, regime_reason, trend_strength, volatility_level, trend_15m, change_24h_pct.
When regime=trend with aligned trend_15m, consider watch or enter_candidate with calibrated confidence.
When regime=range with low trend_strength, prefer soft_skip or watch.
When regime=volatile, prefer watch with moderate confidence or soft_skip if risk high.
If active patch action is block_reentry or manual_review_required, use hard_skip (not enter).
Do NOT always output confidence=0.25 or soft_skip — vary intent when signal exists."""

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
    stage3_context: Dict[str, Any] | None = None,
) -> List[Dict[str, str]]:
    s3 = stage3_context or {}
    user_payload = {
        "task": "stage4_dry_run_decision",
        "symbol": symbol.upper(),
        "market_context": market_context,
        "account_context": account_context,
        "retrieved_patches": retrieved_patches,
        "recent_trade_results": recent_trade_results,
        "recent_reflections": recent_reflections,
        "stage3_context_available": s3.get("stage3_context_available", False),
        "stage3_context_reason": s3.get("stage3_context_reason", "unknown"),
        "safety_constraints": safety_constraints,
        "current_open_positions": current_open_positions,
        "required_output_schema": OUTPUT_SCHEMA_HINT,
        "instructions": [
            "Classify with decision_intent: hard_skip | soft_skip | watch | enter_candidate.",
            "Use regime, regime_reason, trend_strength, range_strength, volatility_level from market_context.",
            "If trend regime with trend_15m aligned and no blocking patch, watch or enter_candidate is valid.",
            "If data_quality or kline_data_quality is partial/error, list gaps in missing_data.",
            "If active patch action is block_reentry or manual_review_required, use hard_skip.",
            "Vary confidence by intent band; avoid defaulting all skips to 0.25.",
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
