class EntryQualityFilter:
    def evaluate(self, fleet, side, market_context, signal, setup_type, adjusted_confidence, fleet_metrics, memory_check, meeting_notes=None):
        reasons = []
        quality = float(adjusted_confidence or 0.0)
        meeting_notes = meeting_notes or {}

        trend_strength = float(market_context.get("trend_strength", 0.0) or 0.0)
        volatility = float(market_context.get("volatility_percentile", 0.0) or 0.0)
        support_distance = float(market_context.get("support_distance", 1.0) or 1.0)
        resistance_distance = float(market_context.get("resistance_distance", 1.0) or 1.0)
        volume_confirmed = bool(market_context.get("volume_confirmed"))
        fake_breakout_risk = bool(market_context.get("fake_breakout_risk"))
        btc_bias = market_context.get("btc_market_bias", "NEUTRAL")
        recent_win_rate = float(fleet_metrics.get("recent_win_rate", 0.5) or 0.5)
        strategy_win_rate = float(fleet_metrics.get("strategy_recent_win_rate", 0.5) or 0.5)

        if side == "BUY" and trend_strength < -0.015:
            reasons.append("strong_downtrend_buy_block")
            quality -= 0.16
        if side == "SELL" and trend_strength > 0.015:
            reasons.append("strong_uptrend_sell_block")
            quality -= 0.16
        if side == "BUY" and support_distance > 0.04:
            reasons.append("buy_far_from_support")
            quality -= 0.08
        if side == "SELL" and resistance_distance > 0.04:
            reasons.append("sell_far_from_resistance")
            quality -= 0.08
        if not volume_confirmed:
            reasons.append("low_volume_setup")
            quality -= 0.08
        if volatility > 0.85:
            reasons.append("high_volatility")
            quality -= 0.1
        if fake_breakout_risk:
            reasons.append("fake_breakout_risk")
            quality -= 0.12
        if recent_win_rate < 0.4:
            reasons.append("fleet_recent_win_rate_too_low")
            quality -= 0.12
        if strategy_win_rate < 0.4:
            reasons.append("strategy_recent_win_rate_too_low")
            quality -= 0.1
        if fleet != "BTC" and side == "BUY" and btc_bias == "BEARISH":
            reasons.append("btc_reverse_pressure")
            quality -= 0.14
        if "similar_loss_pattern" in memory_check.get("penalties", []):
            reasons.append("similar_loss_pattern")
            quality -= 0.08
        risk_notes = [str(item) for item in meeting_notes.get("risk_notes", [])]
        if any(("??" in item) or ("volatility" in item.lower()) for item in risk_notes) and volatility > 0.75:
            reasons.append("meeting_high_volatility_penalty")
            quality -= 0.05
        focus_items = [str(item) for item in meeting_notes.get("next_6h_focus", [])]
        if any(("??" in item) or ("volume" in item.lower()) for item in focus_items) and not volume_confirmed:
            reasons.append("meeting_low_volume_penalty")
            quality -= 0.04

        risk_reward = 1.6 if setup_type not in ("whale_risk_hold", "funding_risk_hold") else 0.5
        if risk_reward < 1.5:
            reasons.append("risk_reward_below_threshold")
            quality -= 0.3

        quality = max(0.0, min(1.0, quality))
        approved = quality >= 0.65
        position_mode = "high" if quality > 0.85 else "normal" if quality > 0.75 else "small" if approved else "reject"
        reject_reason = reasons[0] if not approved and reasons else ""

        return {
            "approved": approved,
            "quality_score": round(quality, 6),
            "adjusted_confidence": round(quality, 6),
            "position_mode": position_mode,
            "reject_reason": reject_reason,
            "reasons": reasons,
        }
