class SetupClassifier:
    def classify(self, fleet, signal, market_context, news_items, whale_status, funding_status):
        action = signal.get("action", "HOLD")
        reason = (signal.get("reason", "") or "").lower()
        sentiment_hit = any(fleet in item.get("targets", []) or "ALL" in item.get("targets", []) for item in news_items)

        if whale_status.get("severity") == "ALERT_RED":
            return "whale_risk_hold"
        if funding_status.get("severity") == "WARNING":
            return "funding_risk_hold"
        if sentiment_hit and action != "HOLD":
            return "news_reaction"
        if action == "BUY" and market_context.get("support_distance", 1.0) < 0.015:
            return "pullback_long"
        if action == "BUY" and market_context.get("local_change_fast", 0.0) > 0.003:
            return "breakout_long"
        if action == "SELL" and market_context.get("resistance_distance", 1.0) < 0.015:
            return "resistance_reject_short"
        if action == "SELL" and market_context.get("local_change_fast", 0.0) < -0.003:
            return "breakdown_short"
        if action == "BUY":
            return "mean_reversion_long"
        if action == "SELL":
            return "mean_reversion_short"
        if "whale" in reason:
            return "whale_risk_hold"
        return "funding_risk_hold" if "funding" in reason else "mean_reversion_long"

