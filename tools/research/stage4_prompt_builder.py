"""Stage 4 LLM prompt builder for structured trading decisions (dry-run)."""
from __future__ import annotations

import json
import os
from pathlib import Path
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
Paper-readiness rules (Stage 4.18-C / 4.18-L):
- watch: MUST include directional_bias (not NONE), candidate_side (BUY/SELL — not NONE when bias is LONG/SHORT), watch_confirmation_reason, entry_trigger (type != none), invalidation, mae_risk_estimate_pct.
- enter_candidate: MUST include candidate_side (not NONE), directional_bias (not NONE), entry_trigger, invalidation, mae_risk_estimate_pct, risk_reward_estimate.
- LONG directional_bias → candidate_side=BUY. SHORT directional_bias → candidate_side=SELL. Never LONG/SHORT bias with candidate_side=NONE.
- If direction is unclear, use soft_skip or hard_skip — never enter_candidate with NONE side.
- watch cannot become entry in the same tick; describe follow-up conditions only.
- watch is NOT vague observation — watch MUST have entry_trigger + invalidation.

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
- PEPE in high volatility: prefer soft_skip.

Worked examples (Stage 4.18-J / 4.18-L):

Example 1 — BTC valid watch WITH side (Stage 4.18-L):
- symbol=BTCUSDT, decision_intent=watch, directional_bias=SHORT
- reference_price=100000, invalidation_price=100300, adverse distance=0.30%, confidence=0.62
- MUST output: candidate_side=SELL, mae_risk_estimate_pct=0.30
- entry_trigger.type != none (e.g. pullback_confirm) with clear trigger_condition
- invalidation.invalidation_price=100300, invalidation.max_adverse_move_pct=0.30
- watch_followup_required=true, paper_readiness.eligible_for_watchlist=true, block_reason=null

Example 2 — ETH valid watch WITH side (Stage 4.18-L):
- symbol=ETHUSDT, decision_intent=watch, directional_bias=LONG
- reference_price=3000, invalidation_price=2991, adverse distance=0.30%, confidence>=0.40
- MUST output: candidate_side=BUY, mae_risk_estimate_pct=0.30
- entry_trigger.type != none, invalidation.invalidation_price=2991, max_adverse_move_pct=0.30
- watch_followup_required=true, paper_readiness.eligible_for_watchlist=true, block_reason=null

Example 3 — Directional bias but side missing is INVALID (Stage 4.18-L):
- If directional_bias=LONG or SHORT and candidate_side=NONE:
- decision_quality_incomplete=true, paper_readiness.eligible_for_watchlist=false
- block_reason=directional_bias_without_candidate_side
- LONG bias → candidate_side MUST be BUY (not NONE). SHORT bias → candidate_side MUST be SELL (not NONE).
- Never output LONG/SHORT bias with candidate_side=NONE on watch or enter_candidate.

Example 4 — entry_trigger / invalidation missing is INVALID (Stage 4.18-L):
- Watch is NOT vague observation — watch MUST have entry_trigger + invalidation.
- If entry_trigger.type=none, entry_trigger missing, or invalidation missing on watch/enter_candidate:
- paper_readiness.eligible_for_watchlist=false, block_reason=missing_paper_fields

Example 5 — MAE above cap remains skip (Stage 4.18-L):
- BTC/ETH MAE > 0.35%, SOL MAE > 0.25%, PEPE MAE > 0.20%:
- decision_intent=soft_skip or hard_skip, eligible_for_watchlist=false, block_reason=mae_risk_too_high
- Do NOT deflate MAE to pass graduation.

ETH acceptable watch:
- reference_price=3000, invalidation_price=2991 → mae_risk_estimate_pct=0.30, candidate_side=BUY

ETH too-risky (reference):
- reference_price=3000, invalidation_price=2960 → mae=1.33%, soft_skip/hard_skip, block_reason=mae_risk_too_high

SOL/PEPE: if SOL MAE>0.25% or PEPE MAE>0.20%, skip/watchlist-only; never deflate MAE.

Structured output contract (Stage 4.18-M) — for watch / enter_candidate:
1. candidate_side is REQUIRED (BUY or SELL). candidate_side NONE is ONLY allowed for soft_skip or hard_skip.
2. directional_bias LONG requires candidate_side BUY.
3. directional_bias SHORT requires candidate_side SELL.
4. entry_trigger.type must NOT be none; entry_trigger.trigger_condition must be non-empty.
5. invalidation is REQUIRED (invalidation_price or max_adverse_move_pct).
6. mae_risk_estimate_pct must equal reference-to-invalidation adverse distance in percent.
7. If you cannot provide side + trigger + invalidation + MAE within cap, output soft_skip or hard_skip.

Bad output (INVALID):
- decision_intent=watch, directional_bias=LONG, candidate_side=NONE, entry_trigger.type=none

Correct output (choose one):
- soft_skip or hard_skip with clear why_skip
- OR candidate_side=BUY + entry_trigger (type != none) + invalidation + mae_risk_estimate_pct within symbol cap

Provider-specific strict output rules (Stage 4.18-N) are injected per provider at call time.

Follow-up confirmation rules (Stage 4.18-P2D) — when previous_watch_context is present:
- This tick is a watchlist FOLLOW-UP confirmation, not a fresh blank-slate decision.
- MUST recheck previous_watch_context: entry_trigger, invalidation, mae_risk_estimate_pct, directional_bias, candidate_side, market_context continuity.
- Set previous_watch_rechecked=true and entry_trigger_rechecked=true in the JSON output.
- entry_trigger_status: confirmed|pending|failed|unknown
- invalidation_status: intact|breached|unknown
- mae_status: within_cap|breached|unknown
- context_continuity_status: stable|improved|degraded|unknown
- followup_continuation_status: confirmed|pending|failed|blocked
- Do NOT hard_skip to NONE/NONE solely because this is a new tick.
- If context is stable/improved AND invalidation intact AND MAE within_cap AND no major new risk_factors:
  do NOT collapse LONG/BUY → NONE/NONE. Prefer decision_intent=watch (continuation_watch / confirmation_pending)
  OR soft_skip while RETAINING previous directional_bias + candidate_side, with an explicit why_skip.
- direction_collapse_allowed=true ONLY when at least one is true: invalidation_breached, mae_breached,
  regime_reversal, data_quality_degraded, entry_trigger_failed, major_risk_factor_added.
- If collapsing direction to NONE/NONE, set direction_collapse_reason to one of those explicit reasons.
- Confidence must NOT drop from a valid watch (e.g. 0.55) to 0.0 without collapse_reason / confidence_reason explaining why.
- Do NOT force ETH watch when direction truly reversed; do NOT loosen MAE caps or confidence floors."""

# Exported markers for Stage 4.18-P2D static review / tests (must stay in sync with SYSTEM_PROMPT).
FOLLOWUP_CONFIRMATION_MARKERS = (
    "previous_watch_rechecked",
    "entry_trigger_rechecked",
    "entry_trigger_status",
    "invalidation_status",
    "mae_status",
    "context_continuity_status",
    "direction_collapse_allowed",
    "direction_collapse_reason",
    "followup_continuation_status",
    "collapse_reason",
    "continuation_watch",
    "confirmation_pending",
)

FOLLOWUP_USER_INSTRUCTIONS = [
    "Stage 4.18-P2D FOLLOW-UP: previous_watch_context is active — recheck entry_trigger, invalidation, MAE, bias/side, context continuity.",
    "Set previous_watch_rechecked=true, entry_trigger_rechecked=true, and fill entry_trigger_status / invalidation_status / mae_status / context_continuity_status.",
    "If context stable/improved and invalidation/MAE not breached: do NOT hard_skip NONE/NONE; use watch (confirmation_pending) or soft_skip retaining prior bias/side.",
    "Direction collapse LONG/BUY→NONE/NONE requires direction_collapse_allowed with explicit reason (invalidation_breached|mae_breached|regime_reversal|data_quality_degraded|entry_trigger_failed|major_risk_factor_added).",
    "Confidence collapse to ~0.0 requires collapse_reason / confidence_reason; unexplained 0.55→0.0 is forbidden.",
]

GROQ_STRICT_OUTPUT_RULE = """GROQ STRICT OUTPUT RULE:
For any watch or enter_candidate, candidate_side must not be NONE.
If you cannot provide BUY/SELL, output soft_skip.
Never output directional_bias LONG/SHORT with candidate_side NONE.
LONG directional_bias → candidate_side=BUY.
SHORT directional_bias → candidate_side=SELL."""

CEREBRAS_STRICT_OUTPUT_RULE = """CEREBRAS STRICT OUTPUT RULE:
For watch or enter_candidate, entry_trigger.type must not be none.
entry_trigger.trigger_condition must be non-empty.
invalidation must be present (invalidation_price or max_adverse_move_pct).
If no concrete trigger exists, output soft_skip/hard_skip.
Do not output watch with missing or none entry_trigger."""


def provider_strict_output_block(provider: str) -> str:
    p = str(provider or "").strip().lower()
    if p == "groq":
        return GROQ_STRICT_OUTPUT_RULE
    if p == "cerebras":
        return CEREBRAS_STRICT_OUTPUT_RULE
    return ""


def inject_provider_strict_prompt(messages: List[Dict[str, str]], provider: str) -> List[Dict[str, str]]:
    block = provider_strict_output_block(provider)
    if not block:
        return messages
    out: List[Dict[str, str]] = []
    for msg in messages:
        if msg.get("role") == "system":
            content = str(msg.get("content") or "")
            if block not in content:
                content = f"{content}\n\n{block}"
            out.append({"role": "system", "content": content})
        else:
            out.append(dict(msg))
    return out

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
    # Stage 4.18-P2D follow-up diagnostics (optional; required when previous_watch_context present)
    "previous_watch_rechecked",
    "entry_trigger_rechecked",
    "entry_trigger_status",
    "invalidation_status",
    "mae_status",
    "context_continuity_status",
    "direction_collapse_allowed",
    "direction_collapse_reason",
    "followup_continuation_status",
    "confirmation_failure_reason",
    "collapse_reason",
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
    "previous_watch_rechecked": "bool (required on follow-up)",
    "entry_trigger_rechecked": "bool (required on follow-up)",
    "entry_trigger_status": "confirmed|pending|failed|unknown",
    "invalidation_status": "intact|breached|unknown",
    "mae_status": "within_cap|breached|unknown",
    "context_continuity_status": "stable|improved|degraded|unknown",
    "direction_collapse_allowed": "bool",
    "direction_collapse_reason": "string",
    "followup_continuation_status": "confirmed|pending|failed|blocked",
    "confirmation_failure_reason": "string",
    "collapse_reason": "string (required if confidence collapses near 0)",
}


def build_previous_watch_context(decision: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Slim prior watch decision into prompt-safe previous_watch_context."""
    if not isinstance(decision, dict):
        return None
    intent = str(
        decision.get("decision_intent")
        or decision.get("intent")
        or decision.get("final_decision")
        or ""
    ).strip().lower()
    if intent not in {"watch", "valid_watch", "enter_candidate"}:
        return None
    bias = str(decision.get("directional_bias") or decision.get("bias") or "").strip().upper()
    side = str(decision.get("candidate_side") or "").strip().upper()
    if bias in {"", "NONE"} and side in {"", "NONE"}:
        return None
    mc = decision.get("market_context")
    if not isinstance(mc, dict):
        mc = {}
    return {
        "symbol": str(decision.get("symbol") or "").upper(),
        "decision_id": decision.get("decision_id"),
        "provider": decision.get("provider"),
        "decision_intent": intent,
        "directional_bias": bias or ("LONG" if side == "BUY" else "SHORT" if side == "SELL" else "NONE"),
        "candidate_side": side or ("BUY" if bias == "LONG" else "SELL" if bias == "SHORT" else "NONE"),
        "confidence": decision.get("confidence"),
        "entry_trigger": decision.get("entry_trigger"),
        "invalidation": decision.get("invalidation"),
        "mae_risk_estimate_pct": decision.get("mae_risk_estimate_pct"),
        "market_context": slim_market_context(mc),
    }


def load_previous_watch_context_from_jsonl(
    output_dir: str | Path | None,
    symbol: str,
) -> Dict[str, Any] | None:
    """Read last same-symbol watch/enter_candidate from ai_decisions.jsonl (if present)."""
    if not output_dir:
        return None
    path = Path(output_dir) / "ai_decisions.jsonl"
    if not path.is_file():
        return None
    sym = str(symbol or "").upper()
    last_watch: Dict[str, Any] | None = None
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if str(row.get("symbol") or "").upper() != sym:
                continue
            # Skip shadow rows if flagged
            if row.get("shadow") or row.get("is_shadow") or str(row.get("lane") or "").lower() == "shadow":
                continue
            ctx = build_previous_watch_context(row)
            if ctx:
                last_watch = ctx
    except OSError:
        return None
    return last_watch


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
    previous_watch_context: Dict[str, Any] | None = None,
) -> List[Dict[str, str]]:
    s3 = stage3_context or {}
    instructions = [
        "Classify decision_intent and calibrate confidence by intent band.",
        "Respect blocking patches; list data gaps in missing_data when quality is partial.",
        "For watch: set directional_bias, candidate_side (BUY/SELL), entry_trigger (type != none), watch_confirmation_reason, invalidation, mae_risk_estimate_pct.",
        "LONG bias → candidate_side=BUY; SHORT bias → candidate_side=SELL; never bias with NONE side.",
        "Watch requires entry_trigger + invalidation — entry_trigger.type=none is invalid for watch.",
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
        "Stage 4.18-M: structured contract — side+trigger+invalidation+MAE required for watch; else soft_skip/hard_skip.",
        "candidate_side NONE only for skip intents; LONG→BUY, SHORT→SELL; entry_trigger.type=none is invalid.",
    ]
    prev = previous_watch_context if isinstance(previous_watch_context, dict) and previous_watch_context else None
    if prev:
        instructions.extend(FOLLOWUP_USER_INSTRUCTIONS)
    user_payload: Dict[str, Any] = {
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
        "instructions": instructions,
    }
    if prev:
        user_payload["previous_watch_context"] = prev
        user_payload["followup_confirmation_mode"] = True
        user_payload["task"] = "stage4_dry_run_followup_confirmation"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def prompt_fingerprint(messages: List[Dict[str, str]]) -> str:
    import hashlib

    blob = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
