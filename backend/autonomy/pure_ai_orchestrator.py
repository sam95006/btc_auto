"""Pure AI orchestrator — single trader brain (TradingAgents / LLM-TradeBot inspired)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from backend.autonomy.ai_flexible_evaluator import AiFlexibleEvaluator, _position_age_hours, _safe_float
from backend.autonomy.pure_ai_debate_gate import PureAiDebateGate
from backend.autonomy.pure_ai_position_policy import (
    apply_entry_throttle,
    filter_entries_by_learning,
    filter_pyramid_candidates,
    trend_confirms_position,
)
from config.pure_ai_trading_config import (
    PURE_AI_DEFAULT_LEVERAGE,
    PURE_AI_DYNAMIC_LEVERAGE_MAX,
    PURE_AI_DYNAMIC_LEVERAGE_MIN,
    PURE_AI_DYNAMIC_MAX_MARGIN_PCT,
    PURE_AI_DYNAMIC_MAX_MARGIN_USD,
    PURE_AI_DYNAMIC_SIZING,
    PURE_AI_MAX_LEVERAGE,
    PURE_AI_LLM_ONLY,
    PURE_AI_MAX_ENTRIES_PER_TICK,
    PURE_AI_MAX_MARGIN_USD,
    PURE_AI_MAX_PROPOSALS_PER_TICK,
    PURE_AI_MAX_PYRAMID_PER_TICK,
    PURE_AI_MIN_MARGIN_USD,
    PURE_AI_RADAR_MARGIN_CAP_FRAC,
    PURE_AI_PYRAMID_ENABLED,
    PURE_AI_PYRAMID_MARGIN_MULT,
    PURE_AI_PYRAMID_MAX_ADDS,
    PURE_AI_PYRAMID_MIN_PNL_PCT,
    PURE_AI_PYRAMID_MIN_PNL_USD,
    PURE_AI_SL_PCT_ON_MARGIN,
    PURE_AI_STALE_SAFETY_HOURS,
    PURE_AI_TARGET_NOTIONAL_USD,
    PURE_AI_TP_FULL_PCT,
    PURE_AI_TP_PARTIAL_PCT,
    pure_ai_active,
    pure_ai_respect_learning,
)


class PureAiOrchestrator:
    """
    Reference patterns integrated:
    - TradingAgents: unified snapshot → trader decision → minimal risk veto
    - LLM-TradeBot: DecisionCore aggregates all intel; RiskAudit = hard caps only
    - ROMA / agentic: plan (LLM eval) → execute in same tick
    - Institutional OMS: decouple reasoning from execution (runtime executes)
    """

    def __init__(self, llm_gateway=None):
        self.evaluator = AiFlexibleEvaluator(llm_gateway=llm_gateway)
        self.debate_gate = PureAiDebateGate(llm_gateway=llm_gateway)
        self._last_cycle: Dict[str, Any] = {}

    @property
    def enabled(self) -> bool:
        return pure_ai_active()

    def run_cycle(self, context: Dict[str, Any]) -> Dict[str, Any]:
        context = dict(context or {})
        context["pure_ai_mode"] = True
        lessons = str(context.get("learning_lessons_text") or "").strip()
        context["trader_directive"] = (
            "TESTNET pure AI swing trader: flexible entries when edge exists. "
            "LEARN from recent losses — do NOT repeat the same symbol+direction that just lost. "
            f"Hard exits: partial reduce near +{PURE_AI_TP_PARTIAL_PCT:.0f}% ROE, full take profit near +{PURE_AI_TP_FULL_PCT:.0f}% ROE, "
            f"stop loss near -{PURE_AI_SL_PCT_ON_MARGIN:.0f}% ROE (mandatory, no hold). "
            "Pyramid ONLY when open position trend still confirms same direction (add size gradually, not burst). "
            f"Max {PURE_AI_MAX_ENTRIES_PER_TICK} brand-new entries and {PURE_AI_MAX_PYRAMID_PER_TICK} pyramid add per tick."
            + (f" Recent lessons: {lessons[:400]}" if lessons else "")
        )
        entries, policy_meta = self._collect_entries(context)
        exits = self._collect_exits(context)
        self._last_cycle = {
            "mode": "pure_ai",
            "timestamp": int(time.time() * 1000),
            "entry_proposals": entries[:8],
            "exit_actions": exits[:8],
            "entry_count": len(entries),
            "exit_count": len(exits),
            "deployable_pool": _safe_float(context.get("deployable_pool")),
            "hq_debate": self.debate_gate.last_snapshot(),
            "entry_eval": dict(getattr(self.evaluator, "_last_entry_eval", None) or {}),
            "position_policy": policy_meta,
        }
        return dict(self._last_cycle)

    def snapshot_status(self) -> Dict[str, Any]:
        return dict(self._last_cycle or {})

    def _collect_entries(self, context: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        policy_meta: Dict[str, Any] = {
            "learning_active": pure_ai_respect_learning(),
            "blocked_by_learning": 0,
            "blocked_by_pyramid": 0,
            "throttled": 0,
        }
        if not self.evaluator.entry_enabled:
            return [], policy_meta
        rows = self.evaluator.collect_trade_proposals(context)
        rows.extend(self._collect_market_signal_entries(context))
        if PURE_AI_LLM_ONLY:
            # Keep LLM + Pure AI fallbacks (heartbeat/radar); block rule-engine proposers only.
            rows = [
                row
                for row in rows
                if str(row.get("decision_source") or "").startswith(("ai_flex", "pure_ai"))
                or str(row.get("proposer") or "").startswith(("ai_flex", "pure_ai"))
            ]
        deployable = _safe_float(context.get("deployable_pool"))
        radar_available = _safe_float(context.get("radar_budget_available"))
        sized = []
        for row in rows[: max(1, PURE_AI_MAX_PROPOSALS_PER_TICK)]:
            proposal = self.apply_aggressive_sizing(
                dict(row),
                deployable_pool=deployable,
                radar_available=radar_available,
            )
            proposal["decision_source"] = "pure_ai_trader"
            proposal["proposer"] = "pure_ai_trader"
            proposal["strategy_key"] = "pure_ai_trader"
            sized.append(proposal)
        pyramid = self._collect_pyramid_adds(context, sized)
        combined = sized + pyramid
        before_pyramid = len(combined)
        combined = filter_pyramid_candidates(
            combined,
            context,
            pyramid_last_at=dict(context.get("pure_ai_pyramid_last_at") or {}),
        )
        policy_meta["blocked_by_pyramid"] = max(0, before_pyramid - len(combined))
        before_learning = len(combined)
        combined = filter_entries_by_learning(combined, context)
        policy_meta["blocked_by_learning"] = max(0, before_learning - len(combined))
        filtered, gate_meta = self.debate_gate.filter_entries(combined, context)
        policy_meta["debate_gate"] = gate_meta
        before_throttle = len(filtered)
        filtered = apply_entry_throttle(
            filtered,
            max_entries=max(1, PURE_AI_MAX_ENTRIES_PER_TICK),
            max_pyramid=max(0, PURE_AI_MAX_PYRAMID_PER_TICK),
        )
        policy_meta["throttled"] = max(0, before_throttle - len(filtered))
        policy_meta["final_count"] = len(filtered)
        return filtered, policy_meta

    def _collect_pyramid_adds(
        self,
        context: Dict[str, Any],
        existing: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Add to winning positions in the same direction (scale into profit)."""
        if not PURE_AI_PYRAMID_ENABLED:
            return []
        existing_symbols = {str(item.get("symbol") or "").upper() for item in existing}
        deployable = _safe_float(context.get("deployable_pool"))
        radar_available = _safe_float(context.get("radar_budget_available"))
        rows: List[Dict[str, Any]] = []
        for item in list(context.get("positions") or []):
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            if not symbol or symbol in existing_symbols:
                continue
            pnl = _safe_float(item.get("unrealized_pnl"))
            margin = _safe_float(item.get("margin"))
            if margin <= 0:
                continue
            pnl_pct = round((pnl / margin) * 100.0, 2)
            if pnl_pct < PURE_AI_PYRAMID_MIN_PNL_PCT and pnl < PURE_AI_PYRAMID_MIN_PNL_USD:
                continue
            if not trend_confirms_position(item, context):
                continue
            side = str(item.get("side") or "").upper()
            if side in {"LONG", "BUY"}:
                side = "BUY"
            elif side in {"SHORT", "SELL"}:
                side = "SELL"
            else:
                qty = _safe_float(item.get("signed_quantity") or item.get("quantity"))
                side = "BUY" if qty >= 0 else "SELL"
            fleet = str(item.get("fleet") or "RADAR").upper()
            proposal = self.apply_aggressive_sizing(
                {
                    "fleet": fleet,
                    "symbol": symbol,
                    "side": side,
                    "adjusted_confidence": min(0.92, 0.62 + pnl_pct / 200.0),
                    "rationale": f"pyramid_winner:+{pnl_pct:.1f}%_on_margin_${pnl:.1f}",
                },
                deployable_pool=deployable,
                radar_available=radar_available,
            )
            proposal["margin"] = round(
                max(PURE_AI_MIN_MARGIN_USD * 0.75, _safe_float(proposal.get("margin")) * PURE_AI_PYRAMID_MARGIN_MULT),
                4,
            )
            proposal["decision_source"] = "pure_ai_pyramid"
            proposal["proposer"] = "pure_ai_pyramid"
            proposal["strategy_key"] = "pure_ai_trader"
            proposal["pyramid_add"] = True
            proposal["pyramid_pnl_pct"] = pnl_pct
            rows.append(proposal)
            if len(rows) >= max(1, PURE_AI_PYRAMID_MAX_ADDS):
                break
        return rows

    def _collect_market_signal_entries(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Regime switching entries (no extra LLM call):
        - Trend regime: follow EMA bias + volume confirmation
        - Range regime: mean reversion using RSI extremes
        - High-risk macro: suppress entries (handled upstream by gates; we also avoid adding here)
        """
        from config.pure_ai_trading_config import PURE_AI_MIN_CONFIDENCE

        blocked = {str(s).upper() for s in (context.get("blocked_symbols") or [])}
        held = {
            str(item.get("symbol") or "").upper()
            for item in (context.get("positions") or [])
            if isinstance(item, dict) and item.get("symbol")
        }
        deployable = _safe_float(context.get("deployable_pool"))
        rows: List[Dict[str, Any]] = []
        markets = dict(context.get("market_context") or {})
        regime = str((context.get("regime_state") or {}).get("label") or "").upper()
        if "HIGH_RISK" in regime or "ALERT" in regime:
            return []

        universe = [str(s).upper() for s in (context.get("tradable_symbols") or [])][:24]
        for symbol in universe:
            if not symbol or symbol in blocked or symbol in held:
                continue
            ctx = markets.get(symbol) if isinstance(markets.get(symbol), dict) else {}
            if not ctx:
                continue
            # Basic market quality gate
            if str(ctx.get("liquidity_status") or "healthy") != "healthy":
                continue
            if str(ctx.get("spread_status") or "normal") != "normal":
                continue
            if str(ctx.get("slippage_risk") or "normal") != "normal":
                continue

            trend_bias = str(ctx.get("trend_bias") or "neutral").lower()
            volume_ok = bool(ctx.get("volume_confirmed"))
            rsi = _safe_float(ctx.get("rsi_14"), 50.0)
            trend_strength = abs(_safe_float(ctx.get("trend_strength"), 0.0))
            vol_pct = _safe_float(ctx.get("volatility_percentile"), 0.5)

            # Determine regime: trend vs range
            is_trend = (trend_bias in {"bullish", "bearish"}) and volume_ok and trend_strength >= 0.004 and vol_pct >= 0.15
            is_range = (trend_bias == "neutral" or trend_strength < 0.0025) and 0.10 <= vol_pct <= 0.85

            side = None
            reason = ""
            confidence = 0.0
            if is_trend:
                side = "BUY" if trend_bias == "bullish" else "SELL"
                confidence = 0.18 + min(0.55, trend_strength * 40.0) + (0.08 if volume_ok else 0.0)
                reason = f"regime_trend:{trend_bias}:str{round(trend_strength,4)}"
            elif is_range:
                if rsi <= 33:
                    side = "BUY"
                    confidence = 0.16 + min(0.35, (33 - rsi) / 40.0)
                    reason = f"regime_range:mr_buy:rsi{round(rsi,1)}"
                elif rsi >= 67:
                    side = "SELL"
                    confidence = 0.16 + min(0.35, (rsi - 67) / 40.0)
                    reason = f"regime_range:mr_sell:rsi{round(rsi,1)}"
            if side not in {"BUY", "SELL"} or confidence < PURE_AI_MIN_CONFIDENCE:
                continue

            from config.fleet_routing_config import core_fleet_for_symbol, is_core_symbol

            fleet = core_fleet_for_symbol(symbol) or ("RADAR" if not is_core_symbol(symbol) else "RADAR")
            proposal = self.evaluator._parse_trade_proposal(
                {
                    "fleet": fleet,
                    "symbol": symbol,
                    "side": side,
                    "confidence": round(confidence, 4),
                    "leverage": round(min(100.0, max(20.0, 20.0 + confidence * 90.0)), 1),
                    "margin_pct_deployable": round(min(0.10, max(0.03, confidence * 0.07)), 4),
                    "rationale": reason[:200],
                },
                min_confidence=PURE_AI_MIN_CONFIDENCE,
            )
            if proposal:
                proposal["decision_source"] = "pure_ai_regime_switch"
                proposal["proposer"] = "pure_ai_regime_switch"
                rows.append(proposal)
        return rows[: max(1, PURE_AI_MAX_PROPOSALS_PER_TICK)]

    def _collect_exits(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        positions = list(context.get("positions") or [])
        if not positions or not self.evaluator.exit_enabled:
            return []
        from backend.autonomy.pure_ai_hard_exit import collect_pure_ai_hard_exits, merge_exit_actions_flexible

        hard = collect_pure_ai_hard_exits(positions)
        soft: List[Dict[str, Any]] = []
        if self._llm_enabled_for_exits():
            soft = self.evaluator.evaluate_exit_actions(
                positions,
                market_contexts=context.get("market_context"),
                wallet_intel=context.get("wallet_intel"),
                external_market_intel=context.get("external_market_intel"),
                regime_state=context.get("regime_state"),
                pure_ai_mode=True,
            )
            if PURE_AI_LLM_ONLY:
                soft = [a for a in soft if str(a.get("source") or "") == "ai_flex_exit"]
        merged = merge_exit_actions_flexible(hard, soft)
        merged.extend(self._stale_safety_exits(positions, existing=merged))
        return merged

    def _llm_enabled_for_exits(self) -> bool:
        try:
            return bool(self.evaluator._llm_enabled())
        except Exception:
            return False

    @staticmethod
    def _stale_safety_exits(positions: List[Dict[str, Any]], existing: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Hard safety only — not a strategy rule; closes dead weight if LLM silent too long."""
        handled = {str(item.get("symbol") or "").upper() for item in existing}
        rows = []
        for item in positions:
            symbol = str(item.get("symbol") or "").upper()
            if not symbol or symbol in handled:
                continue
            age_h = _position_age_hours(item)
            if age_h < PURE_AI_STALE_SAFETY_HOURS:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "fleet": str(item.get("fleet") or "RADAR").upper(),
                    "action": "reduce_or_close",
                    "fraction": 1.0,
                    "confidence": 0.9,
                    "reason": f"pure_ai_stale_safety:{round(age_h, 1)}h",
                    "source": "pure_ai_safety",
                    "urgency": "high",
                }
            )
        return rows

    @staticmethod
    def apply_aggressive_sizing(
        proposal: Dict[str, Any],
        *,
        deployable_pool: float,
        radar_available: float = 0.0,
    ) -> Dict[str, Any]:
        proposal = dict(proposal or {})
        confidence = _safe_float(
            proposal.get("adjusted_confidence") or proposal.get("raw_confidence"),
            0.55,
        )
        leverage = _safe_float(proposal.get("ai_flex_leverage") or proposal.get("leverage"))
        if leverage <= 0:
            leverage = min(100.0, max(10.0, PURE_AI_DEFAULT_LEVERAGE * max(0.85, confidence)))
        # Optional: confidence-based leverage scaling (20–100x) for testnet experimentation.
        if PURE_AI_DYNAMIC_SIZING:
            lo = max(2.0, float(PURE_AI_DYNAMIC_LEVERAGE_MIN))
            hi = max(lo, float(PURE_AI_DYNAMIC_LEVERAGE_MAX))
            leverage = lo + max(0.0, min(1.0, confidence)) * (hi - lo)
        margin = _safe_float(proposal.get("margin") or proposal.get("ai_flex_margin_usd"))
        margin_pct = _safe_float(proposal.get("margin_pct_deployable"))
        if margin <= 0 and margin_pct > 0 and deployable_pool > 0:
            margin = deployable_pool * margin_pct
        if margin <= 0:
            margin = max(PURE_AI_MIN_MARGIN_USD, deployable_pool * 0.04 if deployable_pool > 0 else PURE_AI_MIN_MARGIN_USD)

        max_margin = PURE_AI_MAX_MARGIN_USD
        if PURE_AI_DYNAMIC_SIZING:
            max_margin = max(max_margin, float(PURE_AI_DYNAMIC_MAX_MARGIN_USD))
        if deployable_pool > 0:
            pool_cap = deployable_pool * (float(PURE_AI_DYNAMIC_MAX_MARGIN_PCT) if PURE_AI_DYNAMIC_SIZING else 0.05)
            max_margin = min(max_margin, pool_cap)
        if radar_available > 0:
            max_margin = min(max_margin, radar_available * PURE_AI_RADAR_MARGIN_CAP_FRAC)

        target_margin = PURE_AI_TARGET_NOTIONAL_USD / max(leverage, 1.0)
        margin = min(max(margin, PURE_AI_MIN_MARGIN_USD), max_margin, target_margin + 1.0)
        margin = max(PURE_AI_MIN_MARGIN_USD, min(margin, max_margin))

        proposal["leverage"] = round(min(PURE_AI_MAX_LEVERAGE, 100.0, max(2.0, leverage)), 2)
        proposal["margin"] = round(margin, 4)
        proposal["deployable_pool"] = round(deployable_pool, 4)
        proposal["radar_budget_available"] = round(radar_available, 4)
        proposal["sizing_source"] = "pure_ai_aggressive"
        proposal.pop("margin_pct_deployable", None)
        return proposal
