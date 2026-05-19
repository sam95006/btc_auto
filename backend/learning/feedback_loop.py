from collections import Counter, defaultdict
from datetime import datetime
from backend.learning.strategy_adaptation_engine import StrategyAdaptationEngine
from config.learning_config import (
    BASE_AGGRESSION_MULTIPLIER_FLOOR,
    BASE_POSITION_SIZE_MULTIPLIER_FLOOR,
    CONSECUTIVE_LOSS_HARD_BLOCK,
    CONSECUTIVE_LOSS_SOFT_BLOCK,
    FAILURE_FOCUS_BLOCK_MAP,
    HIGH_LEVERAGE_FAILURE_THRESHOLD,
    HIGH_LEVERAGE_PENALTY_STEP,
    LOSS_RATE_PENALTY_THRESHOLD,
    MAX_CONFIDENCE_PENALTY,
    MAX_HIGH_LEVERAGE_PENALTY,
    SYMBOL_COOLDOWN_LOSS_COUNT,
    SYMBOL_COOLDOWN_SECONDS,
    SYMBOL_COOLDOWN_WINDOW,
)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_timestamp(value):
    if not value:
        return None
    for parser in (
        lambda raw: datetime.fromisoformat(str(raw)),
        lambda raw: datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            return parser(value)
        except Exception:
            continue
    return None


class FailureAnalyzer:
    FAILURE_REASONS = (
        "false_breakout",
        "late_entry",
        "news_conflict",
        "whale_reversal",
        "over_leverage",
        "bad_market_regime",
        "low_liquidity",
        "stop_too_tight",
        "take_profit_too_late",
        "confidence_overestimated",
        "false_signal_high_leverage",
        "unknown",
    )

    def classify_loss(self, result, context=None):
        context = context or {}
        leverage = float(result.get("final_leverage", 0.0) or 0.0)
        regime = str(result.get("market_regime", "") or context.get("market_regime", "")).lower()
        funding_risk = str(context.get("funding_risk", "normal") or "normal").lower()
        basis_risk = str(context.get("basis_risk", "normal") or "normal").lower()
        liquidation_risk = str(context.get("liquidation_risk", "none") or "none").lower()
        slippage_risk = str(context.get("slippage_risk", "normal") or "normal").lower()
        if leverage >= 20 and float(result.get("pnl", 0.0) or 0.0) < 0:
            if context.get("confidence_score", 0.0) >= 0.85:
                return "confidence_overestimated"
            return "over_leverage"
        if liquidation_risk in {"critical", "elevated"}:
            return "bad_market_regime"
        if funding_risk == "elevated" or basis_risk == "elevated":
            return "bad_market_regime"
        if slippage_risk == "elevated":
            return "low_liquidity"
        if regime in {"extreme_volatility", "crash", "news_shock", "alert_red"}:
            return "bad_market_regime"
        if context.get("whale_conflict"):
            return "whale_reversal"
        if context.get("news_conflict"):
            return "news_conflict"
        if context.get("liquidity_risk"):
            return "low_liquidity"
        return "unknown"


class LearningFeedbackLoop:
    def __init__(self, runtime_store):
        self.runtime_store = runtime_store
        self.failure_analyzer = FailureAnalyzer()
        self.strategy_adaptation_engine = StrategyAdaptationEngine()
        self._calibration_cache = {"expires_at": 0.0, "snapshot": None}

    def record_trade_journal(self, journal):
        self.runtime_store.append_trade_journal(journal)

    def record_trade_result(self, result, context=None):
        payload = dict(result)
        pnl = float(payload.get("pnl", 0.0) or 0.0)
        payload["win_loss"] = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT"
        if payload["win_loss"] == "LOSS":
            payload["failure_reason"] = self.failure_analyzer.classify_loss(payload, context=context)
        self.runtime_store.append_trade_result(payload)
        recommendation = self.build_recommendation(payload, context=context)
        if recommendation:
            self.runtime_store.append_signal_weight_recommendation(recommendation)
        self._calibration_cache = {"expires_at": 0.0, "snapshot": None}
        return payload, recommendation

    def build_recommendation(self, result, context=None):
        context = context or {}
        if result.get("win_loss") != "LOSS":
            return None
        leverage = float(result.get("final_leverage", 0.0) or 0.0)
        confidence = float(result.get("confidence_score", 0.0) or context.get("confidence_score", 0.0) or 0.0)
        strategy_key = result.get("strategy_key") or context.get("strategy_key") or "unknown_strategy"
        adjustment = -0.05 if leverage >= 20 or confidence >= 0.85 else -0.02
        return {
            "timestamp": result.get("timestamp"),
            "symbol": result.get("symbol"),
            "fleet": result.get("fleet"),
            "strategy_key": strategy_key,
            "signal_weight_adjustment": adjustment,
            "strategy_confidence_adjustment": adjustment,
            "disabled_pattern_candidate": result.get("failure_reason"),
            "blacklist_candidate": result.get("symbol") if result.get("failure_reason") == "low_liquidity" else None,
            "recommended_leverage_cap": 10 if leverage >= 50 else 20 if leverage >= 20 else None,
            "confidence_penalty_suggestion": abs(adjustment),
            "position_size_multiplier_suggestion": 0.8 if leverage >= 20 or confidence >= 0.85 else 0.92,
            "review_priority": "high" if leverage >= 20 or confidence >= 0.85 else "normal",
            "recommendation_only": True,
        }

    def _consecutive_losses(self, items):
        count = 0
        for item in items:
            if item.get("win_loss") == "LOSS":
                count += 1
            else:
                break
        return count

    def _summarize_bucket(self, items, fleet):
        items = list(items or [])
        if not items:
            return {
                "fleet": fleet,
                "trade_count": 0,
                "loss_rate": 0.0,
                "consecutive_losses": 0,
                "high_leverage_loss_count": 0,
                "confidence_penalty": 0.0,
                "leverage_cap": None,
                "aggression_multiplier": 1.0,
                "position_size_multiplier": 1.0,
                "min_confidence_threshold": 0.35,
                "blocked_regimes": [],
                "pause_new_entries": False,
                "failure_focus": [],
                "failure_focus_flags": [],
                "symbol_cooldown": {},
            }

        losses = [item for item in items if item.get("win_loss") == "LOSS"]
        consecutive_losses = self._consecutive_losses(items)
        recent = items[:10]
        high_leverage_losses = [
            item
            for item in recent
            if item.get("win_loss") == "LOSS" and float(item.get("final_leverage", 0.0) or 0.0) >= 20
        ]
        failure_focus = Counter(item.get("failure_reason", "unknown") for item in losses)
        regime_losses = Counter(
            str(item.get("market_regime", "unknown") or "unknown")
            for item in losses
            if item.get("market_regime")
        )

        confidence_penalty = 0.0
        loss_rate = len(losses) / len(items)
        if loss_rate >= LOSS_RATE_PENALTY_THRESHOLD:
            confidence_penalty += 0.03
        if consecutive_losses >= 2:
            confidence_penalty += 0.05
        if consecutive_losses >= CONSECUTIVE_LOSS_SOFT_BLOCK:
            confidence_penalty += 0.05
        if any(item.get("failure_reason") in {"confidence_overestimated", "false_signal_high_leverage"} for item in recent[:5]):
            confidence_penalty += 0.05
        confidence_penalty += min(MAX_HIGH_LEVERAGE_PENALTY, len(high_leverage_losses) * HIGH_LEVERAGE_PENALTY_STEP)
        confidence_penalty = round(min(MAX_CONFIDENCE_PENALTY, confidence_penalty), 4)

        leverage_cap = None
        if consecutive_losses >= CONSECUTIVE_LOSS_HARD_BLOCK:
            leverage_cap = 0
        elif consecutive_losses >= CONSECUTIVE_LOSS_SOFT_BLOCK:
            leverage_cap = 3
        elif any(item.get("failure_reason") == "over_leverage" for item in recent[:5]):
            leverage_cap = 10
        elif high_leverage_losses:
            leverage_cap = 20
        if fleet == "PEPE":
            leverage_cap = 20 if leverage_cap is None else min(leverage_cap, 20)

        blocked_regimes = [
            regime
            for regime, count in regime_losses.items()
            if count >= 3 and regime not in {"normal", "unknown", "hq_spot"}
        ]
        aggression_multiplier = round(max(BASE_AGGRESSION_MULTIPLIER_FLOOR, 1.0 - confidence_penalty * 1.6), 4)
        position_size_multiplier = round(max(BASE_POSITION_SIZE_MULTIPLIER_FLOOR, 1.0 - confidence_penalty * 1.9), 4)
        min_confidence_threshold = round(min(0.62, 0.35 + confidence_penalty * 0.55), 4)

        failure_focus_flags = [
            FAILURE_FOCUS_BLOCK_MAP[name]
            for name, _count in failure_focus.most_common(3)
            if name in FAILURE_FOCUS_BLOCK_MAP
        ]

        symbol_losses = defaultdict(list)
        for item in items:
            if item.get("win_loss") == "LOSS":
                symbol_losses[str(item.get("symbol") or "UNKNOWN")].append(item)
        symbol_cooldown = {}
        now = datetime.now()
        for symbol, symbol_items in symbol_losses.items():
            recent_symbol_losses = symbol_items[:SYMBOL_COOLDOWN_WINDOW]
            if len(recent_symbol_losses) < SYMBOL_COOLDOWN_LOSS_COUNT:
                continue
            latest_ts = _parse_timestamp(recent_symbol_losses[0].get("timestamp"))
            active = False
            if latest_ts is not None:
                age_seconds = (now - latest_ts).total_seconds()
                active = age_seconds <= SYMBOL_COOLDOWN_SECONDS or latest_ts.date() == now.date()
            symbol_cooldown[symbol] = {
                "loss_count": len(recent_symbol_losses),
                "active": active,
                "latest_loss_at": recent_symbol_losses[0].get("timestamp"),
                "reason": "repeated_symbol_losses",
            }

        return {
            "fleet": fleet,
            "trade_count": len(items),
            "loss_rate": round(loss_rate, 4),
            "consecutive_losses": consecutive_losses,
            "high_leverage_loss_count": len(high_leverage_losses),
            "confidence_penalty": confidence_penalty,
            "leverage_cap": leverage_cap,
            "aggression_multiplier": aggression_multiplier,
            "position_size_multiplier": position_size_multiplier,
            "min_confidence_threshold": min_confidence_threshold,
            "blocked_regimes": blocked_regimes,
            "pause_new_entries": leverage_cap == 0,
            "failure_focus": [name for name, _count in failure_focus.most_common(3)],
            "failure_focus_flags": sorted(set(failure_focus_flags)),
            "symbol_cooldown": symbol_cooldown,
        }

    def build_calibration_snapshot(self, limit=240, cache_seconds=15):
        now = datetime.now().timestamp()
        if self._calibration_cache["snapshot"] and now < self._calibration_cache["expires_at"]:
            return self._calibration_cache["snapshot"]

        trade_results = list(self.runtime_store.recent_trade_results(limit=limit))
        by_fleet = defaultdict(list)
        by_strategy = defaultdict(list)
        for item in trade_results:
            fleet = str(item.get("fleet") or "UNKNOWN").upper()
            strategy_key = item.get("strategy_key") or "unknown_strategy"
            by_fleet[fleet].append(item)
            by_strategy[(fleet, strategy_key)].append(item)

        fleet_snapshot = {
            fleet: self._summarize_bucket(items, fleet)
            for fleet, items in by_fleet.items()
        }
        strategy_snapshot = {}
        for (fleet, strategy_key), items in by_strategy.items():
            summary = self._summarize_bucket(items, fleet)
            strategy_snapshot[f"{fleet}:{strategy_key}"] = {
                **summary,
                "strategy_key": strategy_key,
            }

        snapshot = {
            "generated_at": _now(),
            "fleet_adjustments": fleet_snapshot,
            "strategy_adjustments": strategy_snapshot,
        }
        self._calibration_cache = {
            "expires_at": now + cache_seconds,
            "snapshot": snapshot,
        }
        return snapshot

    def get_strategy_guidance(self, fleet, strategy_key, market_regime=None, market_context=None):
        snapshot = self.build_calibration_snapshot()
        fleet_key = str(fleet or "UNKNOWN").upper()
        strategy_compound = f"{fleet_key}:{strategy_key or 'unknown_strategy'}"
        fleet_adjustment = snapshot.get("fleet_adjustments", {}).get(fleet_key, {})
        strategy_adjustment = snapshot.get("strategy_adjustments", {}).get(strategy_compound, {})

        confidence_penalty = round(
            min(
                0.32,
                float(fleet_adjustment.get("confidence_penalty", 0.0) or 0.0)
                + float(strategy_adjustment.get("confidence_penalty", 0.0) or 0.0),
            ),
            4,
        )
        leverage_caps = [
            cap
            for cap in [
                fleet_adjustment.get("leverage_cap"),
                strategy_adjustment.get("leverage_cap"),
            ]
            if cap is not None
        ]
        leverage_cap = min(leverage_caps) if leverage_caps else None
        blocked_regimes = sorted(
            set(fleet_adjustment.get("blocked_regimes", []) or [])
            | set(strategy_adjustment.get("blocked_regimes", []) or [])
        )
        pause_new_entries = bool(fleet_adjustment.get("pause_new_entries") or strategy_adjustment.get("pause_new_entries"))
        regime_blocked = bool(market_regime and market_regime in blocked_regimes)
        aggression_multiplier = min(
            float(fleet_adjustment.get("aggression_multiplier", 1.0) or 1.0),
            float(strategy_adjustment.get("aggression_multiplier", 1.0) or 1.0),
        )
        position_size_multiplier = min(
            float(fleet_adjustment.get("position_size_multiplier", 1.0) or 1.0),
            float(strategy_adjustment.get("position_size_multiplier", 1.0) or 1.0),
        )
        min_confidence_threshold = max(
            float(fleet_adjustment.get("min_confidence_threshold", 0.35) or 0.35),
            float(strategy_adjustment.get("min_confidence_threshold", 0.35) or 0.35),
        )
        failure_focus_flags = sorted(
            set(fleet_adjustment.get("failure_focus_flags", []) or [])
            | set(strategy_adjustment.get("failure_focus_flags", []) or [])
        )
        symbol_cooldown = dict(fleet_adjustment.get("symbol_cooldown", {}) or {})
        for symbol, payload in dict(strategy_adjustment.get("symbol_cooldown", {}) or {}).items():
            current = symbol_cooldown.get(symbol)
            if not current or bool(payload.get("active")):
                symbol_cooldown[symbol] = payload
        guidance = {
            "fleet": fleet_key,
            "strategy_key": strategy_key or "unknown_strategy",
            "loss_rate": round(float(fleet_adjustment.get("loss_rate", 0.0) or 0.0), 4),
            "consecutive_losses": int(max(
                float(fleet_adjustment.get("consecutive_losses", 0) or 0),
                float(strategy_adjustment.get("consecutive_losses", 0) or 0),
            )),
            "confidence_penalty": confidence_penalty,
            "leverage_cap": leverage_cap,
            "blocked_regimes": blocked_regimes,
            "pause_new_entries": pause_new_entries,
            "regime_blocked": regime_blocked,
            "aggression_multiplier": round(aggression_multiplier, 4),
            "position_size_multiplier": round(position_size_multiplier, 4),
            "min_confidence_threshold": round(min_confidence_threshold, 4),
            "failure_focus": sorted(
                set(fleet_adjustment.get("failure_focus", []) or [])
                | set(strategy_adjustment.get("failure_focus", []) or [])
            ),
            "failure_focus_flags": failure_focus_flags,
            "symbol_cooldown": symbol_cooldown,
            "generated_at": snapshot.get("generated_at"),
        }
        adaptation = self.strategy_adaptation_engine.evaluate(
            fleet_key,
            strategy_key or "unknown_strategy",
            base_guidance=guidance,
            market_context=market_context or {"market_regime": market_regime},
        )
        overrides = dict(adaptation.get("overrides", {}) or {})
        guidance["confidence_penalty"] = round(
            min(0.45, float(guidance.get("confidence_penalty", 0.0) or 0.0) + float(adaptation.get("pressure_score", 0.0) or 0.0) * 0.08),
            4,
        )
        guidance["leverage_cap"] = (
            overrides.get("leverage_cap")
            if guidance.get("leverage_cap") is None
            else min(guidance.get("leverage_cap"), overrides.get("leverage_cap"))
            if overrides.get("leverage_cap") is not None
            else guidance.get("leverage_cap")
        )
        guidance["blocked_regimes"] = sorted(set(guidance.get("blocked_regimes", []) or []) | set(overrides.get("blocked_regimes", []) or []))
        guidance["pause_new_entries"] = bool(guidance.get("pause_new_entries") or adaptation.get("pause_new_entries"))
        guidance["regime_blocked"] = bool((market_regime and market_regime in guidance["blocked_regimes"]) or guidance["pause_new_entries"])
        guidance["aggression_multiplier"] = round(min(float(guidance.get("aggression_multiplier", 1.0) or 1.0), float(overrides.get("aggression_multiplier", 1.0) or 1.0)), 4)
        guidance["position_size_multiplier"] = round(min(float(guidance.get("position_size_multiplier", 1.0) or 1.0), float(overrides.get("position_size_multiplier", 1.0) or 1.0)), 4)
        guidance["min_confidence_threshold"] = round(max(float(guidance.get("min_confidence_threshold", 0.35) or 0.35), float(overrides.get("min_confidence_threshold", 0.35) or 0.35)), 4)
        guidance["strategy_adaptation"] = adaptation
        guidance["adaptive_mode"] = adaptation.get("mode", "normal")
        guidance["strategy_review_required"] = bool(adaptation.get("review_required"))
        return guidance

    def build_strategy_adaptation_snapshot(self, market_contexts=None):
        snapshot = self.build_calibration_snapshot()
        market_contexts = dict(market_contexts or {})
        fleet_adjustments = snapshot.get("fleet_adjustments", {}) or {}
        items = {}
        for fleet, fleet_guidance in fleet_adjustments.items():
            strategy_key = f"{str(fleet).lower()}_adaptive_strategy"
            guidance = self.get_strategy_guidance(
                fleet,
                strategy_key,
                (market_contexts.get(fleet, {}) or {}).get("market_regime", "normal"),
                market_context=market_contexts.get(fleet, {}) or {},
            )
            items[fleet] = {
                "strategy_key": strategy_key,
                "mode": guidance.get("adaptive_mode", "normal"),
                "pressure_score": float((guidance.get("strategy_adaptation") or {}).get("pressure_score", 0.0) or 0.0),
                "review_required": bool(guidance.get("strategy_review_required")),
                "reasons": list((guidance.get("strategy_adaptation") or {}).get("reasons", []) or []),
                "recommended_actions": list((guidance.get("strategy_adaptation") or {}).get("recommended_actions", []) or []),
                "overrides": dict((guidance.get("strategy_adaptation") or {}).get("overrides", {}) or {}),
            }
        return {
            "generated_at": _now(),
            "strategies": items,
        }
