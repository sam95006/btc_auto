"""LLM-driven holistic trade entry/exit using wallet, regime, radar, and external intel."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.ai_flexible_eval_config import (
    AI_FLEX_AUTO_PROFIT_ENABLED,
    AI_FLEX_AUTO_PROFIT_PCT,
    AI_FLEX_EVAL_ENABLED,
    AI_FLEX_EXIT_ENABLED,
    AI_FLEX_EXIT_MIN_CONFIDENCE,
    AI_FLEX_HEURISTIC_FALLBACK,
    AI_FLEX_MAX_LEVERAGE,
    AI_FLEX_MAX_PROPOSALS,
    AI_FLEX_MIN_CONFIDENCE,
    AI_FLEX_SIZING_FROM_LLM,
    AI_FLEX_STALE_EXIT_HOURS,
    AI_FLEX_STALE_FLAT_EXIT_HOURS,
    AI_FLEX_STALE_MIN_PROFIT_USD,
)
from config.fleet_routing_config import validate_futures_open_route
from config.pure_ai_trading_config import PURE_AI_LLM_ONLY, pure_ai_active
from config.sandbox_exit_config import (
    SANDBOX_ABS_EXIT_ENABLED,
    SANDBOX_SL_ABS_USD,
    SANDBOX_TP_ABS_USD,
)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


def _position_age_hours(position: Dict[str, Any]) -> float:
    opened = str(position.get("opened_at") or "").strip()
    if not opened:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return max(0.0, (time.time() - datetime.strptime(opened[:19], fmt).timestamp()) / 3600.0)
        except Exception:
            continue
    return 0.0


def _compact_context(ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ctx = dict(ctx or {})
    return {
        "trend_bias": ctx.get("trend_bias"),
        "market_regime": ctx.get("market_regime"),
        "market_regime_ai": ctx.get("market_regime_ai"),
        "rsi_14": ctx.get("rsi_14"),
        "atr_pct": ctx.get("atr_pct"),
        "funding_rate": ctx.get("funding_rate"),
        "volume_confirmed": ctx.get("volume_confirmed"),
        "liquidation_risk": ctx.get("liquidation_risk"),
        "news_conflict": ctx.get("news_conflict"),
        "whale_conflict": ctx.get("whale_conflict"),
    }


class AiFlexibleEvaluator:
    """Advisory LLM layer: evaluates full snapshot → entry proposals & exit actions."""

    def __init__(self, llm_gateway=None):
        self.llm_gateway = llm_gateway
        self._last_entry_eval: Dict[str, Any] = {}

    @property
    def entry_enabled(self) -> bool:
        return bool(AI_FLEX_EVAL_ENABLED)

    @property
    def exit_enabled(self) -> bool:
        return bool(AI_FLEX_EXIT_ENABLED)

    def _llm_enabled(self) -> bool:
        return bool(self.llm_gateway and getattr(self.llm_gateway, "enabled", lambda: False)())

    def build_snapshot(self, context: Dict[str, Any]) -> Dict[str, Any]:
        context = dict(context or {})
        market_contexts = dict(context.get("market_context") or {})
        compact_markets = {
            str(key).upper(): _compact_context(val)
            for key, val in list(market_contexts.items())[:24]
            if isinstance(val, dict)
        }
        radar = dict(context.get("radar_scan") or {})
        candidates = list(radar.get("candidates") or [])[:12]
        positions = list(context.get("positions") or [])[:12]
        deployable = _safe_float(context.get("deployable_pool"))
        growth = dict(context.get("growth_status") or {})
        return {
            "wallet_intel": dict(context.get("wallet_intel") or {}),
            "deployable_pool": deployable,
            "max_leverage_cap": min(
                _safe_float(growth.get("max_leverage"), AI_FLEX_MAX_LEVERAGE),
                AI_FLEX_MAX_LEVERAGE,
            ),
            "regime": dict(context.get("regime_state") or {}),
            "external_market_intel": dict(context.get("external_market_intel") or {}),
            "growth_mode": str(growth.get("mode") or ""),
            "core_fleet_signals": {
                fleet: {
                    "symbol": data.get("symbol"),
                    "action": (data.get("signal") or {}).get("action"),
                    "confidence": (data.get("signal") or {}).get("confidence"),
                    "reason": (data.get("signal") or {}).get("reason"),
                }
                for fleet, data in dict(context.get("core_fleets") or {}).items()
                if isinstance(data, dict)
            },
            "radar_candidates": candidates,
            "open_positions": [
                {
                    "symbol": item.get("symbol"),
                    "fleet": item.get("fleet"),
                    "side": item.get("side"),
                    "unrealized_pnl": item.get("unrealized_pnl"),
                    "margin": item.get("margin"),
                    "leverage": item.get("leverage"),
                }
                for item in positions
                if isinstance(item, dict)
            ],
            "market_contexts": compact_markets,
            "news_headlines": list(context.get("news_headlines") or [])[:8],
            "blocked_symbols": list(context.get("blocked_symbols") or [])[:20],
            "learning_guidance_summary": dict(context.get("learning_guidance_summary") or {}),
            "ml_confidence_by_symbol": dict(context.get("ml_confidence_by_symbol") or {}),
            "sizing_guidance": {
                "use_llm_leverage_and_margin": AI_FLEX_SIZING_FROM_LLM,
                "margin_pct_range": [0.03, 0.20],
                "leverage_range": [2, AI_FLEX_MAX_LEVERAGE],
                "deployable_pool": deployable,
            },
        }

    def collect_trade_proposals(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        self._last_entry_eval = {"timestamp": int(time.time() * 1000)}
        if not self.entry_enabled:
            self._last_entry_eval.update({"status": "disabled", "reason": "entry_disabled"})
            return []
        if not self._llm_enabled():
            self._last_entry_eval.update({"status": "disabled", "reason": "llm_offline"})
            return []
        snapshot = self.build_snapshot(context)
        if context.get("pure_ai_mode"):
            snapshot["pure_ai_mode"] = True
            snapshot["trader_directive"] = str(context.get("trader_directive") or "")
            snapshot["tick_seq"] = int(context.get("pure_ai_tick_seq") or 0)
            try:
                from config.pure_ai_trading_config import pure_ai_llm_refresh_seconds

                refresh = pure_ai_llm_refresh_seconds()
                if refresh > 0:
                    snapshot["eval_bucket"] = int(time.time() // refresh)
            except Exception:
                pass
        result = self.llm_gateway.run_task("flex_trade_eval", snapshot, fallback_output={})
        output = result.get("output") if isinstance(result.get("output"), dict) else result
        if not isinstance(output, dict):
            self._last_entry_eval.update(
                {
                    "status": str(result.get("status") or "bad_output"),
                    "reason": "invalid_llm_output",
                    "llm_error": result.get("error"),
                }
            )
            return []
        min_conf = AI_FLEX_MIN_CONFIDENCE
        if context.get("pure_ai_mode"):
            from config.pure_ai_trading_config import PURE_AI_MIN_CONFIDENCE

            min_conf = min(AI_FLEX_MIN_CONFIDENCE, PURE_AI_MIN_CONFIDENCE)
        raw_items = list(output.get("trade_proposals") or [])[: max(1, AI_FLEX_MAX_PROPOSALS)]
        rows = []
        rejected_low_conf = 0
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            proposal = self._parse_trade_proposal(item, min_confidence=min_conf)
            if proposal:
                rows.append(proposal)
            else:
                rejected_low_conf += 1
        fallback_used = None
        if not rows and context.get("pure_ai_mode"):
            from config.pure_ai_trading_config import (
                PURE_AI_HEURISTIC_HEARTBEAT,
                PURE_AI_RADAR_FALLBACK,
                PURE_AI_REQUIRE_MIN_PROPOSALS,
            )

            if PURE_AI_RADAR_FALLBACK:
                rows = self._pure_ai_radar_fallback(context, min_confidence=min_conf)
                if rows:
                    fallback_used = "radar"
            if not rows and PURE_AI_REQUIRE_MIN_PROPOSALS:
                rows = self._pure_ai_liquid_heartbeat(context, min_confidence=min_conf)
                if rows:
                    fallback_used = "liquid_heartbeat"
            if not rows and PURE_AI_HEURISTIC_HEARTBEAT:
                rows = self.collect_heuristic_proposals(context)[:3]
                if rows:
                    fallback_used = "heuristic_heartbeat"
        if not rows and AI_FLEX_HEURISTIC_FALLBACK and not (pure_ai_active() and PURE_AI_LLM_ONLY):
            rows = self.collect_heuristic_proposals(context)
            if rows:
                fallback_used = "heuristic"
        self._last_entry_eval.update(
            {
                "status": str(result.get("status") or "unknown"),
                "cache_hit": bool(result.get("cache_hit")),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "skip_reason": output.get("skip_reason") or output.get("market_read"),
                "market_read": output.get("market_read"),
                "raw_proposal_count": len(raw_items),
                "parsed_proposal_count": len(rows),
                "rejected_low_confidence": rejected_low_conf,
                "min_confidence_used": min_conf,
                "fallback_used": fallback_used,
            }
        )
        return rows

    def _pure_ai_liquid_heartbeat(self, context: Dict[str, Any], min_confidence: float) -> List[Dict[str, Any]]:
        """Guaranteed liquid entries when LLM + radar both return nothing (testnet activity)."""
        from config.pure_ai_trading_config import (
            PURE_AI_DEFAULT_LEVERAGE,
            PURE_AI_HEARTBEAT_SYMBOLS_MAX,
            PURE_AI_PREFERRED_SYMBOLS,
        )

        blocked = {str(s).upper() for s in (context.get("blocked_symbols") or [])}
        tradable = {str(s).upper() for s in (context.get("tradable_symbols") or PURE_AI_PREFERRED_SYMBOLS)}
        held = {
            str(item.get("symbol") or "").upper()
            for item in (context.get("positions") or [])
            if isinstance(item, dict) and item.get("symbol")
        }
        preferred = [s for s in PURE_AI_PREFERRED_SYMBOLS if s and s not in blocked and s in tradable]
        if not preferred:
            return []
        rotate = int(time.time() // 45) % max(1, len(preferred))
        rows: List[Dict[str, Any]] = []
        for offset in range(min(PURE_AI_HEARTBEAT_SYMBOLS_MAX, len(preferred))):
            symbol = preferred[(rotate + offset) % len(preferred)]
            if symbol in held:
                continue
            side = self._infer_heartbeat_side(symbol, context)
            confidence = max(min_confidence + 0.03, 0.26)
            from config.fleet_routing_config import core_fleet_for_symbol, is_core_symbol

            fleet = core_fleet_for_symbol(symbol) or "RADAR" if is_core_symbol(symbol) else "RADAR"
            proposal = self._parse_trade_proposal(
                {
                    "fleet": fleet,
                    "symbol": symbol,
                    "side": side,
                    "confidence": confidence,
                    "leverage": round(min(AI_FLEX_MAX_LEVERAGE, max(15.0, PURE_AI_DEFAULT_LEVERAGE)), 1),
                    "margin_pct_deployable": 0.03,
                    "rationale": "pure_ai_liquid_heartbeat",
                },
                min_confidence=min_confidence,
            )
            if proposal:
                proposal["decision_source"] = "pure_ai_liquid_heartbeat"
                proposal["proposer"] = "pure_ai_liquid_heartbeat"
                rows.append(proposal)
        return rows

    @staticmethod
    def _infer_heartbeat_side(symbol: str, context: Dict[str, Any]) -> str:
        symbol = str(symbol or "").upper()
        for data in dict(context.get("core_fleets") or {}).values():
            if not isinstance(data, dict):
                continue
            if str(data.get("symbol") or "").upper() != symbol:
                continue
            action = str((data.get("signal") or {}).get("action") or "").upper()
            if action in {"BUY", "SELL"}:
                return action
        markets = dict(context.get("market_context") or {})
        ctx = markets.get(symbol) if isinstance(markets.get(symbol), dict) else {}
        bias = str(ctx.get("bias") or ctx.get("trend") or ctx.get("market_regime") or "").lower()
        if bias in {"bear", "down", "short", "sell", "risk_off"}:
            return "SELL"
        return "BUY"

    def _pure_ai_radar_fallback(self, context: Dict[str, Any], min_confidence: float) -> List[Dict[str, Any]]:
        """When LLM returns empty, take top RADAR candidate so testnet keeps trading."""
        from config.pure_ai_trading_config import PURE_AI_PREFERRED_SYMBOLS, PURE_AI_RADAR_FALLBACK_MAX

        blocked = {str(s).upper() for s in (context.get("blocked_symbols") or [])}
        tradable = {str(s).upper() for s in (context.get("tradable_symbols") or PURE_AI_PREFERRED_SYMBOLS)}
        radar = dict(context.get("radar_scan") or {})
        candidates = list(radar.get("candidates") or [])
        preferred = {str(s).upper() for s in PURE_AI_PREFERRED_SYMBOLS if str(s).upper() in tradable}

        def _score(row: Any) -> float:
            return _safe_float((row or {}).get("score", (row or {}).get("candidate_score")), 0.0)

        ranked = sorted(candidates, key=_score, reverse=True)
        liquid_first = [row for row in ranked if str((row or {}).get("symbol") or "").upper() in preferred]
        ordered = liquid_first + [row for row in ranked if row not in liquid_first]
        rows: List[Dict[str, Any]] = []
        for item in ordered[:8]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper().replace("/", "")
            score_raw = item.get("score", item.get("candidate_score", 0))
            confidence = _safe_float(score_raw, 0.0)
            if confidence > 1.0:
                confidence = confidence / 100.0
            confidence = max(confidence, min_confidence + 0.02)
            if not symbol or symbol in blocked or symbol not in tradable or confidence < min_confidence:
                continue
            side_raw = str(item.get("side") or item.get("candidate_side") or "LONG").upper()
            side = "BUY" if side_raw in {"LONG", "BUY"} else "SELL"
            proposal = self._parse_trade_proposal(
                {
                    "fleet": "RADAR",
                    "symbol": symbol,
                    "side": side,
                    "confidence": confidence,
                    "leverage": round(min(AI_FLEX_MAX_LEVERAGE, max(12.0, confidence * 40)), 1),
                    "margin_pct_deployable": round(min(0.05, max(0.02, confidence * 0.04)), 4),
                    "rationale": "pure_ai_radar_fallback_top_candidate",
                },
                min_confidence=min_confidence,
            )
            if proposal:
                proposal["decision_source"] = "ai_flex_radar_fallback"
                proposal["proposer"] = "ai_flex_radar_fallback"
                rows.append(proposal)
            if len(rows) >= max(1, PURE_AI_RADAR_FALLBACK_MAX):
                break
        return rows

    def collect_heuristic_proposals(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Signal/radar fallback when LLM returns nothing."""
        context = dict(context or {})
        rows: List[Dict[str, Any]] = []
        blocked = {str(item).upper() for item in (context.get("blocked_symbols") or [])}
        held = {
            str(item.get("symbol") or "").upper()
            for item in (context.get("positions") or [])
            if isinstance(item, dict) and item.get("symbol")
        }
        for fleet, data in dict(context.get("core_fleets") or {}).items():
            if not isinstance(data, dict):
                continue
            symbol = str(data.get("symbol") or "").upper()
            signal = dict(data.get("signal") or {})
            action = str(signal.get("action") or "HOLD").upper()
            confidence = _safe_float(signal.get("confidence"))
            if action not in {"BUY", "SELL"} or confidence < AI_FLEX_MIN_CONFIDENCE:
                continue
            if symbol in blocked or symbol in held:
                continue
            proposal = self._parse_trade_proposal(
                {
                    "fleet": str(fleet).upper(),
                    "symbol": symbol,
                    "side": action,
                    "confidence": confidence,
                    "leverage": round(min(AI_FLEX_MAX_LEVERAGE, max(5.0, confidence * 50)), 1),
                    "margin_pct_deployable": round(min(0.15, max(0.04, confidence * 0.12)), 4),
                    "rationale": str(signal.get("reason") or "heuristic_core_signal")[:200],
                }
            )
            if proposal:
                proposal["decision_source"] = "ai_flex_heuristic"
                proposal["proposer"] = "ai_flex_heuristic"
                rows.append(proposal)
        for item in list((context.get("radar_scan") or {}).get("candidates") or [])[:6]:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper().replace("/", "")
            score_raw = item.get("score", item.get("candidate_score", 0))
            confidence = _safe_float(score_raw, 0.0)
            if confidence > 1.0:
                confidence = confidence / 100.0
            if confidence < AI_FLEX_MIN_CONFIDENCE or not symbol:
                continue
            if symbol in blocked or symbol in held:
                continue
            side_raw = str(item.get("side") or item.get("candidate_side") or "LONG").upper()
            side = "BUY" if side_raw in {"LONG", "BUY"} else "SELL"
            proposal = self._parse_trade_proposal(
                {
                    "fleet": "RADAR",
                    "symbol": symbol,
                    "side": side,
                    "confidence": confidence,
                    "leverage": round(min(AI_FLEX_MAX_LEVERAGE, max(8.0, confidence * 45)), 1),
                    "margin_pct_deployable": round(min(0.12, max(0.03, confidence * 0.10)), 4),
                    "rationale": "heuristic_radar_candidate",
                }
            )
            if proposal:
                proposal["decision_source"] = "ai_flex_heuristic"
                proposal["proposer"] = "ai_flex_heuristic"
                rows.append(proposal)
        return rows[: max(1, AI_FLEX_MAX_PROPOSALS)]

    def _parse_trade_proposal(self, item: Dict[str, Any], min_confidence: Optional[float] = None) -> Optional[Dict[str, Any]]:
        symbol = str(item.get("symbol") or "").upper().replace("/", "")
        side = str(item.get("side") or "BUY").upper()
        if side not in {"BUY", "SELL"}:
            side = "BUY" if side == "LONG" else "SELL"
        confidence = _safe_float(item.get("confidence"))
        floor = _safe_float(min_confidence, AI_FLEX_MIN_CONFIDENCE) if min_confidence is not None else AI_FLEX_MIN_CONFIDENCE
        if not symbol or confidence < floor:
            return None
        fleet = str(item.get("fleet") or "RADAR").upper()
        route_ok, _reason = validate_futures_open_route(fleet, symbol)
        if not route_ok:
            fleet = "RADAR"
            route_ok, _reason = validate_futures_open_route(fleet, symbol)
            if not route_ok:
                return None
        margin_pct = _safe_float(item.get("margin_pct_deployable"), 0.0)
        margin_usd = _safe_float(item.get("margin_usd"), 0.0)
        leverage = _safe_float(item.get("leverage"), 0.0)
        proposal = {
            "fleet": fleet,
            "symbol": symbol,
            "symbol_override": symbol,
            "side": side,
            "reason": f"ai_flex_entry:{symbol}",
            "raw_confidence": round(confidence, 4),
            "adjusted_confidence": round(confidence, 4),
            "strategy_key": "ai_flex_evaluator",
            "market_type": "futures",
            "capital_pool": "radar" if fleet == "RADAR" else "fleet",
            "decision_source": "ai_flex_eval",
            "proposer": "ai_flex_eval",
            "ai_rationale": str(item.get("rationale") or item.get("reason") or "")[:400],
            "ai_flex_eval": {
                "score": _safe_float(item.get("score"), confidence * 100),
                "edge_summary": str(item.get("edge_summary") or "")[:200],
                "risk_flags": list(item.get("risk_flags") or [])[:6],
                "margin_pct_deployable": round(margin_pct, 4) if margin_pct > 0 else None,
                "margin_usd": round(margin_usd, 4) if margin_usd > 0 else None,
                "leverage": round(leverage, 2) if leverage > 0 else None,
            },
        }
        if margin_pct > 0:
            proposal["margin_pct_deployable"] = round(min(0.25, max(0.02, margin_pct)), 4)
        if margin_usd > 0:
            proposal["ai_flex_margin_usd"] = round(margin_usd, 4)
        if leverage > 0:
            proposal["ai_flex_leverage"] = round(min(leverage, AI_FLEX_MAX_LEVERAGE), 2)
        return proposal

    @staticmethod
    def apply_ai_sizing(
        proposal: Dict[str, Any],
        *,
        deployable_pool: float,
        max_leverage: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Apply LLM leverage/margin as primary sizing when enabled."""
        proposal = dict(proposal or {})
        if str(proposal.get("decision_source")) != "ai_flex_eval" or not AI_FLEX_SIZING_FROM_LLM:
            return proposal
        cap = min(_safe_float(max_leverage, AI_FLEX_MAX_LEVERAGE), AI_FLEX_MAX_LEVERAGE)
        ai = dict(proposal.get("ai_flex_eval") or {})
        lev = _safe_float(proposal.get("ai_flex_leverage") or ai.get("leverage"))
        margin_usd = _safe_float(proposal.get("ai_flex_margin_usd") or ai.get("margin_usd"))
        margin_pct = _safe_float(proposal.get("margin_pct_deployable") or ai.get("margin_pct_deployable"))
        if lev > 0:
            proposal["leverage"] = round(min(max(lev, 1.0), cap), 2)
        if margin_usd > 0:
            proposal["margin"] = round(margin_usd, 4)
        elif margin_pct > 0 and deployable_pool > 0:
            proposal["margin"] = round(deployable_pool * min(0.25, max(0.02, margin_pct)), 4)
        if proposal.get("leverage") or proposal.get("margin"):
            proposal["sizing_source"] = "ai_flex_llm"
        return proposal

    def evaluate_exit_actions(
        self,
        positions: List[Dict[str, Any]],
        *,
        market_contexts: Optional[Dict[str, Any]] = None,
        wallet_intel: Optional[Dict[str, Any]] = None,
        external_market_intel: Optional[Dict[str, Any]] = None,
        regime_state: Optional[Dict[str, Any]] = None,
        pure_ai_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        if not self.exit_enabled:
            return []
        positions = [dict(item) for item in (positions or []) if isinstance(item, dict)]
        if not positions:
            return []
        auto_actions = self._auto_profit_exit_candidates(positions)
        llm_actions: List[Dict[str, Any]] = []
        if self._llm_enabled():
            payload = {
                "pure_ai_mode": bool(pure_ai_mode),
                "wallet_intel": dict(wallet_intel or {}),
                "regime": dict(regime_state or {}),
                "external_market_intel": dict(external_market_intel or {}),
                "profit_targets": {
                    "take_profit_usd": SANDBOX_TP_ABS_USD,
                    "stop_loss_usd": SANDBOX_SL_ABS_USD,
                    "auto_profit_enabled": AI_FLEX_AUTO_PROFIT_ENABLED,
                },
                "positions": [
                    {
                        "symbol": item.get("symbol"),
                        "fleet": item.get("fleet"),
                        "side": item.get("side"),
                        "entry_price": item.get("entry_price"),
                        "mark_price": item.get("mark_price"),
                        "unrealized_pnl": item.get("unrealized_pnl"),
                        "margin": item.get("margin"),
                        "leverage": item.get("leverage"),
                        "pnl_pct_on_margin": self._pnl_pct_on_margin(item),
                        "market_context": _compact_context(
                            (market_contexts or {}).get(str(item.get("fleet") or "").upper())
                        ),
                    }
                    for item in positions[:10]
                ],
            }
            result = self.llm_gateway.run_task("flex_exit_eval", payload, fallback_output={})
            output = result.get("output") if isinstance(result.get("output"), dict) else result
            if isinstance(output, dict):
                for item in list(output.get("exit_actions") or []):
                    if isinstance(item, dict):
                        parsed = self._parse_exit_action(item)
                        if parsed:
                            llm_actions.append(parsed)
        return self._merge_exit_actions(auto_actions, llm_actions)

    @staticmethod
    def _pnl_pct_on_margin(position: Dict[str, Any]) -> float:
        margin = _safe_float(position.get("margin"))
        pnl = _safe_float(position.get("unrealized_pnl"))
        if margin <= 0:
            return 0.0
        return round((pnl / margin) * 100.0, 2)

    def _auto_profit_exit_candidates(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not AI_FLEX_AUTO_PROFIT_ENABLED or not SANDBOX_ABS_EXIT_ENABLED:
            return []
        actions = []
        for item in positions:
            symbol = str(item.get("symbol") or "").upper()
            fleet = str(item.get("fleet") or "RADAR").upper()
            if not symbol:
                continue
            pnl = _safe_float(item.get("unrealized_pnl"))
            pnl_pct = self._pnl_pct_on_margin(item)
            age_h = _position_age_hours(item)
            hit_abs_tp = SANDBOX_ABS_EXIT_ENABLED and pnl >= SANDBOX_TP_ABS_USD
            hit_abs_sl = SANDBOX_ABS_EXIT_ENABLED and pnl <= -SANDBOX_SL_ABS_USD
            hit_pct_tp = pnl > 0 and pnl_pct >= AI_FLEX_AUTO_PROFIT_PCT
            hit_stale_profit = age_h >= AI_FLEX_STALE_EXIT_HOURS and pnl >= AI_FLEX_STALE_MIN_PROFIT_USD
            hit_stale_flat = age_h >= AI_FLEX_STALE_FLAT_EXIT_HOURS and abs(pnl) < AI_FLEX_STALE_MIN_PROFIT_USD
            if hit_abs_tp or hit_pct_tp or hit_stale_profit:
                fraction = 1.0 if (hit_abs_tp and pnl >= SANDBOX_TP_ABS_USD * 2) or pnl_pct >= AI_FLEX_AUTO_PROFIT_PCT * 2 else 0.5
                if hit_stale_profit and not hit_abs_tp and pnl_pct < AI_FLEX_AUTO_PROFIT_PCT:
                    fraction = 0.5
                action = "reduce_or_close" if fraction >= 1.0 else "take_partial_profit"
                actions.append(
                    {
                        "symbol": symbol,
                        "fleet": fleet,
                        "action": action,
                        "fraction": fraction,
                        "confidence": 0.88,
                        "reason": f"ai_auto_profit:{round(pnl, 2)}u:{round(pnl_pct, 1)}pct:{round(age_h, 1)}h",
                        "source": "ai_flex_auto_profit",
                        "urgency": "high",
                    }
                )
            elif hit_abs_sl or hit_stale_flat:
                actions.append(
                    {
                        "symbol": symbol,
                        "fleet": fleet,
                        "action": "reduce_or_close",
                        "fraction": 1.0,
                        "confidence": 0.85,
                        "reason": (
                            f"ai_auto_stop_loss:{round(pnl, 2)}u"
                            if hit_abs_sl
                            else f"ai_stale_flat_exit:{round(age_h, 1)}h"
                        ),
                        "source": "ai_flex_auto_profit",
                        "urgency": "high",
                    }
                )
        return actions

    @staticmethod
    def _merge_exit_actions(
        auto_actions: List[Dict[str, Any]],
        llm_actions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_symbol: Dict[str, Dict[str, Any]] = {}
        for item in auto_actions + llm_actions:
            symbol = str(item.get("symbol") or "").upper()
            if not symbol:
                continue
            existing = by_symbol.get(symbol)
            if not existing or _safe_float(item.get("confidence")) >= _safe_float(existing.get("confidence")):
                by_symbol[symbol] = item
        return list(by_symbol.values())

    def _parse_exit_action(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        decision = str(item.get("decision") or item.get("action") or "HOLD").upper()
        if decision in {"HOLD", "WAIT"}:
            return None
        confidence = _safe_float(item.get("confidence"))
        if confidence < AI_FLEX_EXIT_MIN_CONFIDENCE:
            return None
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            return None
        if decision in {"CLOSE", "FULL_CLOSE", "EXIT"}:
            action = "reduce_or_close"
        elif decision in {"PARTIAL", "TAKE_PROFIT", "TRIM"}:
            action = "take_partial_profit"
        elif decision in {"REDUCE", "CUT"}:
            action = "reduce"
        else:
            return None
        fraction = _safe_float(item.get("fraction") or item.get("close_fraction"), 0.35)
        if action == "reduce_or_close":
            fraction = 1.0
        else:
            fraction = min(0.75, max(0.15, fraction))
        return {
            "symbol": symbol,
            "fleet": str(item.get("fleet") or "RADAR").upper(),
            "action": action,
            "fraction": round(fraction, 4),
            "confidence": round(confidence, 4),
            "reason": str(item.get("reason") or item.get("rationale") or "ai_flex_exit")[:200],
            "source": "ai_flex_exit",
            "urgency": str(item.get("urgency") or "medium").lower(),
        }
