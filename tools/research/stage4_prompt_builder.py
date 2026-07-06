"""Stage 4 LLM prompt builder for structured trading decisions (dry-run)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

SYSTEM_PROMPT = """You are a Stage 4 trading decision assistant for Bybit demo/testnet research only.
Respond with a single JSON object only. No markdown or prose outside JSON.
Do NOT suggest changing safety caps or recommend mainnet, real money, production, or ARM.
Allowed final_action: enter, skip. Use decision_intent for watch/enter_candidate while final_action stays skip.
Allowed candidate_side: BUY, SELL, NONE. Allowed decision_intent: hard_skip, soft_skip, watch, enter_candidate.
Allowed directional_bias: LONG, SHORT, NONE (maps from candidate_side: BUY=LONG, SELL=SHORT).
confidence is 0-1. Dry-run only — output will NOT place orders; Risk Supervisor will review.
Use market_context.regime, trend_15m, trend_strength, volatility_level, change_24h_pct.
If patch action is block_reentry or manual_review_required, use hard_skip. Vary confidence by intent band.
Paper-readiness rules (Stage 4.18-C):
- watch: MUST include directional_bias (not NONE), watch_confirmation_reason, invalidation, mae_risk_estimate_pct.
- enter_candidate: MUST include candidate_side (not NONE), directional_bias (not NONE), entry_trigger, invalidation, mae_risk_estimate_pct, risk_reward_estimate.
- If direction is unclear, use soft_skip or hard_skip — never enter_candidate with NONE side.
- watch cannot become entry in the same tick; describe follow-up conditions only.

MAE estimate calibration (Stage 4.18-F / 4.18-H / 4.18-I) — mae_risk_estimate_pct is a PERCENT number, not a ratio:
- 0.25 means 0.25% adverse move, NOT 25% and NOT 0.0025.
- MAE is NOT a forecast of future max volatility, NOT ATR, and NOT 24h range. It is the acceptable adverse move from reference price to invalidation if this watch/candidate were taken.
- Tie MAE to entry_trigger + invalidation: use the distance to invalidation as the MAE estimate, not whole-session volatility.
- BTC/ETH watch survival target: <= 0.28%. Graduation target: <= 0.35%. If estimated MAE > 0.35%, use soft_skip/hard_skip — NOT paper-ready watch.
- SOL cap 0.25%: if MAE > 0.25%, usually soft_skip. Do NOT use SOL short-term chop as MAE.
- PEPE cap 0.20%: usually watchlist-only or skip; do NOT lower risk estimate just to pass cap.
- ETH: if no direction, skip is correct. If direction is clear, MUST output directional_bias, entry_trigger, invalidation, mae_risk_estimate_pct (do not hard_skip with missing paper fields when bias exists).
- Do NOT underestimate MAE to pass caps. If uncertain, skip. If MAE too high: paper_readiness.eligible_for_watchlist=false, block_reason=mae_risk_too_high.
- mae_risk_estimate_pct MUST be <= invalidation.max_adverse_move_pct (same percent units).

ETH MAE alignment (Stage 4.18-I):
- If directional_bias=LONG/SHORT and decision_intent=watch, do NOT use whole 15m volatility as MAE.
- mae_risk_estimate_pct MUST equal the percent distance (invalidation distance) from reference_price (last_price) to invalidation_price.
- If ETH MAE > 0.35%, use soft_skip or hard_skip — NOT a paper-ready watch.
- If ETH MAE is 0.28–0.35%, watch is allowed with watch_followup_required=true, entry_trigger, invalidation, block_reason=null.
- Do NOT force enter_candidate on ETH; output paper-ready watch only when direction is clear.

BTC graduation recovery (Stage 4.18-I):
- Do not over-skip BTC watches that meet paper criteria.
- If BTC directional_bias is LONG/SHORT, candidate_side is set, MAE <= 0.35%, confidence >= 0.40: allow paper-ready watch.
- If BTC MAE > 0.35%, skip — never deflate MAE to pass cap.

SOL / PEPE conservative line (Stage 4.18-I):
- Do NOT lower MAE on SOL/PEPE to chase graduation.
- SOL MAE > 0.25% or PEPE MAE > 0.20%: soft_skip or watchlist-only — not paper-ready watch.
- PEPE in high volatility: prefer soft_skip."""

SCHEMA_FIELD_NAMES = (
    "final_action",
    "decision_intent",
    "symbol",
    "candidate_side",
    "confidence",
    "why_enter",
    "why_skip",
    "side_reason",
    "confidence_reason",
    "missing_data",
    "edge_factors",
    "risk_factors",
    "risk_notes",
    "patch_awareness",
    "uncertainty",
    "requires_manual_review",
    "directional_bias",
    "side_confidence",
    "watch_followup_required",
    "watch_confirmation_reason",
    "entry_trigger",
    "invalidation",
    "mae_risk_estimate_pct",
    "mfe_potential_estimate_pct",
    "risk_reward_estimate",
    "paper_readiness",
)


def context_item_limit(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return default


def slim_market_context(market_context: Dict[str, Any]) -> Dict[str, Any]:
    """Drop duplicate/low-signal market fields to reduce prompt tokens."""
    keep = (
        "symbol",
        "last_price",
        "change_24h_pct",
        "regime",
        "regime_reason",
        "trend_15m",
        "trend_strength",
        "range_strength",
        "volatility_level",
        "volatility_15m",
        "spread_bps",
        "data_quality",
        "kline_data_quality",
        "data_limitations",
    )
    slim = {k: market_context[k] for k in keep if k in market_context}
    if "symbol" not in slim and market_context.get("symbol"):
        slim["symbol"] = market_context.get("symbol")
    return slim


def slim_account_context(account_context: Dict[str, Any]) -> Dict[str, Any]:
    keep = (
        "available_balance",
        "total_equity",
        "open_positions",
        "balance_read_ok",
    )
    return {k: account_context[k] for k in keep if k in account_context}


OUTPUT_SCHEMA_HINT = {
    "fields": list(SCHEMA_FIELD_NAMES),
    "final_action": "enter|skip",
    "decision_intent": "hard_skip|soft_skip|watch|enter_candidate",
    "candidate_side": "BUY|SELL|NONE",
    "directional_bias": "LONG|SHORT|NONE",
    "entry_trigger": {
        "type": "price_breakout|pullback_confirm|momentum_confirm|none",
        "trigger_price": "number",
        "trigger_condition": "string",
    },
    "invalidation": {
        "invalidation_price": "number",
        "invalidation_reason": "string",
        "max_adverse_move_pct": "number (percent, same units as mae_risk_estimate_pct)",
    },
    "mae_risk_estimate_pct": "number (percent, e.g. 0.25 = 0.25%)",
    "paper_readiness": {
        "eligible_for_watchlist": "bool",
        "eligible_for_hypothetical_entry": "bool",
        "block_reason": "string",
    },
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
        "market_context": slim_market_context(market_context),
        "account_context": slim_account_context(account_context),
        "retrieved_patches": retrieved_patches[: context_item_limit("STAGE4_CONTEXT_PATCH_LIMIT", 3)],
        "recent_trade_results": recent_trade_results[: context_item_limit("STAGE4_CONTEXT_TRADE_LIMIT", 3)],
        "recent_reflections": recent_reflections[: context_item_limit("STAGE4_CONTEXT_REFLECTION_LIMIT", 3)],
        "stage3_context_available": s3.get("stage3_context_available", False),
        "stage3_context_reason": s3.get("stage3_context_reason", "unknown"),
        "safety_constraints": safety_constraints,
        "current_open_positions": current_open_positions,
        "required_output_schema": OUTPUT_SCHEMA_HINT,
        "instructions": [
            "Classify decision_intent and calibrate confidence by intent band.",
            "Respect blocking patches; list data gaps in missing_data when quality is partial.",
            "For watch: set directional_bias, watch_confirmation_reason, invalidation, mae_risk_estimate_pct.",
            "For enter_candidate: require candidate_side, directional_bias, entry_trigger, invalidation, mae_risk_estimate_pct, risk_reward_estimate.",
            "If direction unclear, use soft_skip/hard_skip — never enter_candidate with NONE side.",
            "Stage 4.18-H/I: MAE = invalidation distance from reference_price to invalidation_price, not ATR/vol.",
            "mae_risk_estimate_pct is percent (0.25 = 0.25%); must be <= invalidation.max_adverse_move_pct.",
            "BTC/ETH: watch survival <=0.28%, graduation <=0.35%; above 0.35% → soft_skip/hard_skip.",
            "SOL cap 0.25%; PEPE cap 0.20%; do not deflate MAE to pass caps — skip instead.",
            "ETH watch: tie MAE to invalidation distance; 0.28–0.35% watch needs watch_followup_required=true.",
            "BTC: if bias clear, side set, MAE<=0.35%, conf>=0.40 → paper-ready watch; do not over-skip.",
            "PEPE high vol → soft_skip; SOL/PEPE never deflate MAE for graduation.",
            "If MAE too high: paper_readiness.eligible_for_watchlist=false, block_reason=mae_risk_too_high.",
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
