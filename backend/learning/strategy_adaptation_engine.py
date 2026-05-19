from __future__ import annotations

from config.strategy_adaptation_config import (
    ADAPTIVE_MODE_CAUTIOUS,
    ADAPTIVE_MODE_NORMAL,
    ADAPTIVE_MODE_RESTRICTED,
    ADAPTIVE_MODE_SUSPENDED,
    CAUTIOUS_AGGRESSION_CAP,
    CAUTIOUS_LEVERAGE_CAP,
    CAUTIOUS_MIN_CONFIDENCE_FLOOR,
    CAUTIOUS_POSITION_CAP,
    CAUTIOUS_PRESSURE_THRESHOLD,
    PEPE_RESTRICTED_LEVERAGE_CAP,
    PEPE_SUSPENDED_LEVERAGE_CAP,
    PRESSURE_WEIGHTS,
    RESTRICTED_AGGRESSION_CAP,
    RESTRICTED_LEVERAGE_CAP,
    RESTRICTED_MIN_CONFIDENCE_FLOOR,
    RESTRICTED_POSITION_CAP,
    RESTRICTED_PRESSURE_THRESHOLD,
    SUSPENDED_AGGRESSION_CAP,
    SUSPENDED_LEVERAGE_CAP,
    SUSPENDED_MIN_CONFIDENCE_FLOOR,
    SUSPENDED_POSITION_CAP,
    SUSPENDED_PRESSURE_THRESHOLD,
)


def _safe_float(value):
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


class StrategyAdaptationEngine:
    def evaluate(self, fleet, strategy_key, base_guidance=None, market_context=None):
        fleet = str(fleet or "UNKNOWN").upper()
        strategy_key = strategy_key or "unknown_strategy"
        base_guidance = dict(base_guidance or {})
        market_context = dict(market_context or {})

        reasons = []
        pressure = 0.0
        market_regime = str(market_context.get("market_regime") or "normal").lower()
        slippage_risk = str(market_context.get("slippage_risk") or "normal").lower()
        liquidity_status = str(market_context.get("liquidity_status") or "healthy").lower()
        oi_notional_status = str(market_context.get("oi_notional_status") or "healthy").lower()
        funding_risk = str(market_context.get("funding_risk") or "normal").lower()
        basis_risk = str(market_context.get("basis_risk") or "normal").lower()
        liquidation_risk = str(market_context.get("liquidation_risk") or "none").lower()
        news_conflict = bool(market_context.get("news_conflict"))
        whale_conflict = bool(market_context.get("whale_conflict"))

        if slippage_risk == "elevated":
            pressure += PRESSURE_WEIGHTS["slippage_elevated"]
            reasons.append("elevated_slippage")
        if liquidity_status != "healthy":
            pressure += PRESSURE_WEIGHTS["liquidity_unhealthy"]
            reasons.append("unhealthy_liquidity")
        if oi_notional_status != "healthy":
            pressure += PRESSURE_WEIGHTS["oi_notional_weak"]
            reasons.append("weak_open_interest")
        if funding_risk == "elevated":
            pressure += PRESSURE_WEIGHTS["funding_elevated"]
            reasons.append("funding_dislocation")
        if basis_risk == "elevated":
            pressure += PRESSURE_WEIGHTS["basis_elevated"]
            reasons.append("basis_dislocation")
        if liquidation_risk == "critical":
            pressure += PRESSURE_WEIGHTS["liquidation_critical"]
            reasons.append("critical_liquidation_risk")
        elif liquidation_risk == "elevated":
            pressure += PRESSURE_WEIGHTS["liquidation_elevated"]
            reasons.append("elevated_liquidation_risk")
        if news_conflict:
            pressure += PRESSURE_WEIGHTS["news_conflict"]
            reasons.append("news_conflict")
        if whale_conflict:
            pressure += PRESSURE_WEIGHTS["whale_conflict"]
            reasons.append("whale_conflict")

        loss_rate = _safe_float(base_guidance.get("loss_rate"))
        consecutive_losses = int(base_guidance.get("consecutive_losses") or 0)
        confidence_penalty = _safe_float(base_guidance.get("confidence_penalty"))
        failure_focus = set(base_guidance.get("failure_focus", []) or [])

        if loss_rate >= 0.6:
            pressure += PRESSURE_WEIGHTS["loss_rate_high"]
            reasons.append("loss_rate_high")
        if consecutive_losses >= 5:
            pressure += PRESSURE_WEIGHTS["consecutive_losses_hard"]
            reasons.append("hard_loss_streak")
        elif consecutive_losses >= 3:
            pressure += PRESSURE_WEIGHTS["consecutive_losses_soft"]
            reasons.append("soft_loss_streak")
        if confidence_penalty >= 0.12:
            pressure += PRESSURE_WEIGHTS["confidence_penalty_high"]
            reasons.append("confidence_penalty_high")
        if "bad_market_regime" in failure_focus:
            pressure += PRESSURE_WEIGHTS["failure_focus_market_regime"]
            reasons.append("strategy_fails_in_bad_regime")
        if "low_liquidity" in failure_focus:
            pressure += PRESSURE_WEIGHTS["failure_focus_low_liquidity"]
            reasons.append("strategy_fails_in_thin_liquidity")
        if "over_leverage" in failure_focus or "confidence_overestimated" in failure_focus:
            pressure += PRESSURE_WEIGHTS["failure_focus_over_leverage"]
            reasons.append("strategy_overreaches")

        pressure = round(min(1.0, pressure), 4)
        mode = ADAPTIVE_MODE_NORMAL
        if base_guidance.get("pause_new_entries") or pressure >= SUSPENDED_PRESSURE_THRESHOLD:
            mode = ADAPTIVE_MODE_SUSPENDED
        elif pressure >= RESTRICTED_PRESSURE_THRESHOLD:
            mode = ADAPTIVE_MODE_RESTRICTED
        elif pressure >= CAUTIOUS_PRESSURE_THRESHOLD:
            mode = ADAPTIVE_MODE_CAUTIOUS

        overrides = {
            "min_confidence_threshold": _safe_float(base_guidance.get("min_confidence_threshold") or 0.35),
            "aggression_multiplier": _safe_float(base_guidance.get("aggression_multiplier") or 1.0),
            "position_size_multiplier": _safe_float(base_guidance.get("position_size_multiplier") or 1.0),
            "leverage_cap": base_guidance.get("leverage_cap"),
            "blocked_regimes": list(base_guidance.get("blocked_regimes", []) or []),
        }

        review_required = False
        pause_new_entries = bool(base_guidance.get("pause_new_entries"))
        recommended_actions = []
        if mode == ADAPTIVE_MODE_CAUTIOUS:
            overrides["min_confidence_threshold"] = max(overrides["min_confidence_threshold"], CAUTIOUS_MIN_CONFIDENCE_FLOOR)
            overrides["aggression_multiplier"] = min(overrides["aggression_multiplier"], CAUTIOUS_AGGRESSION_CAP)
            overrides["position_size_multiplier"] = min(overrides["position_size_multiplier"], CAUTIOUS_POSITION_CAP)
            leverage_cap = CAUTIOUS_LEVERAGE_CAP
            overrides["leverage_cap"] = leverage_cap if overrides["leverage_cap"] is None else min(leverage_cap, overrides["leverage_cap"])
            recommended_actions.extend(["tighten_entry_filter", "reduce_position_size"])
        elif mode == ADAPTIVE_MODE_RESTRICTED:
            overrides["min_confidence_threshold"] = max(overrides["min_confidence_threshold"], RESTRICTED_MIN_CONFIDENCE_FLOOR)
            overrides["aggression_multiplier"] = min(overrides["aggression_multiplier"], RESTRICTED_AGGRESSION_CAP)
            overrides["position_size_multiplier"] = min(overrides["position_size_multiplier"], RESTRICTED_POSITION_CAP)
            leverage_cap = PEPE_RESTRICTED_LEVERAGE_CAP if fleet == "PEPE" else RESTRICTED_LEVERAGE_CAP
            overrides["leverage_cap"] = leverage_cap if overrides["leverage_cap"] is None else min(leverage_cap, overrides["leverage_cap"])
            review_required = True
            recommended_actions.extend(["restrict_new_entries", "require_stronger_confirmation", "reduce_leverage"])
        elif mode == ADAPTIVE_MODE_SUSPENDED:
            overrides["min_confidence_threshold"] = max(overrides["min_confidence_threshold"], SUSPENDED_MIN_CONFIDENCE_FLOOR)
            overrides["aggression_multiplier"] = min(overrides["aggression_multiplier"], SUSPENDED_AGGRESSION_CAP)
            overrides["position_size_multiplier"] = min(overrides["position_size_multiplier"], SUSPENDED_POSITION_CAP)
            leverage_cap = PEPE_SUSPENDED_LEVERAGE_CAP if fleet == "PEPE" else SUSPENDED_LEVERAGE_CAP
            overrides["leverage_cap"] = leverage_cap if overrides["leverage_cap"] is None else min(leverage_cap, overrides["leverage_cap"])
            pause_new_entries = True
            review_required = True
            recommended_actions.extend(["suspend_strategy", "force_review", "fallback_to_observe_mode"])

        if market_regime in {"thin_liquidity", "high_slippage", "basis_dislocation", "funding_dislocation", "liquidation_risk"}:
            if market_regime not in overrides["blocked_regimes"] and mode in {ADAPTIVE_MODE_RESTRICTED, ADAPTIVE_MODE_SUSPENDED}:
                overrides["blocked_regimes"].append(market_regime)

        return {
            "fleet": fleet,
            "strategy_key": strategy_key,
            "mode": mode,
            "pressure_score": pressure,
            "market_regime": market_regime,
            "reasons": reasons,
            "recommended_actions": recommended_actions,
            "review_required": review_required,
            "pause_new_entries": pause_new_entries,
            "overrides": {
                "min_confidence_threshold": round(overrides["min_confidence_threshold"], 4),
                "aggression_multiplier": round(overrides["aggression_multiplier"], 4),
                "position_size_multiplier": round(overrides["position_size_multiplier"], 4),
                "leverage_cap": overrides["leverage_cap"],
                "blocked_regimes": sorted(set(overrides["blocked_regimes"])),
            },
        }
