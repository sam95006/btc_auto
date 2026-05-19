from collections import deque


class MarketContextFilter:
    def __init__(self, max_points=120):
        self.max_points = max_points
        self.price_history = {
            fleet: deque(maxlen=max_points)
            for fleet in ["BTC", "ETH", "SOL", "PEPE"]
        }

    def import_state(self, payload=None):
        payload = payload or {}
        history = payload.get("price_history", {})
        for fleet, values in history.items():
            if fleet in self.price_history:
                self.price_history[fleet].clear()
                self.price_history[fleet].extend(values[-self.max_points :])

    def export_state(self):
        return {
            "price_history": {
                fleet: list(values)
                for fleet, values in self.price_history.items()
            }
        }

    def observe(self, prices):
        for fleet, item in (prices or {}).items():
            price = float(item.get("price", 0.0) or 0.0)
            if fleet in self.price_history and price > 0:
                self.price_history[fleet].append(price)

    def _percent_change(self, fleet, lookback):
        series = self.price_history.get(fleet, [])
        if len(series) <= lookback:
            return 0.0
        old = float(series[-lookback - 1] or 0.0)
        new = float(series[-1] or 0.0)
        if old <= 0:
            return 0.0
        return (new - old) / old

    def evaluate(self, fleet, whale_status, funding_status, meeting_notes=None):
        series = self.price_history.get(fleet, [])
        meeting_notes = meeting_notes or {}
        btc_change_fast = self._percent_change("BTC", 3)
        btc_change_slow = self._percent_change("BTC", 12)
        local_fast = self._percent_change(fleet, 3)
        local_slow = self._percent_change(fleet, 12)

        recent = list(series)[-20:]
        if len(recent) >= 5:
            high = max(recent)
            low = min(recent)
            last = recent[-1]
            support_distance = 0.0 if last == 0 else max(0.0, (last - low) / last)
            resistance_distance = 0.0 if last == 0 else max(0.0, (high - last) / last)
            volatility = 0.0 if low <= 0 else (high - low) / max(low, 1e-9)
        else:
            support_distance = 0.05
            resistance_distance = 0.05
            volatility = 0.02

        trend_strength = local_slow
        volatility_percentile = min(1.0, volatility / 0.12)
        volume_confirmed = abs(local_fast) > 0.0012 or abs(local_slow) > 0.002
        btc_market_bias = "BEARISH" if btc_change_slow < -0.01 else "BULLISH" if btc_change_slow > 0.01 else "NEUTRAL"
        altcoin_beta_risk = fleet != "BTC" and btc_change_fast < -0.006
        fake_breakout_risk = abs(local_fast) > 0.007 and not volume_confirmed

        approved = whale_status.get("severity") != "ALERT_RED" and funding_status.get("severity") != "WARNING"
        reason = ""
        forbidden_items = [str(item) for item in meeting_notes.get("forbidden_actions", [])]
        if whale_status.get("severity") == "ALERT_RED":
            reason = "whale_alert_red"
        elif funding_status.get("severity") == "WARNING":
            reason = "funding_warning"
        elif any(("高波" in item) or ("volatility" in item.lower()) for item in forbidden_items) and volatility_percentile > 0.9:
            approved = False
            reason = "meeting_high_volatility_block"

        market_regime = "trend_up" if trend_strength > 0.01 else "trend_down" if trend_strength < -0.01 else "range"

        return {
            "approved": approved,
            "reject_reason": reason,
            "market_regime": market_regime,
            "trend_strength": round(trend_strength, 6),
            "volatility_percentile": round(volatility_percentile, 6),
            "volume_confirmed": volume_confirmed,
            "support_distance": round(support_distance, 6),
            "resistance_distance": round(resistance_distance, 6),
            "btc_market_bias": btc_market_bias,
            "altcoin_beta_risk": altcoin_beta_risk,
            "fake_breakout_risk": fake_breakout_risk,
            "btc_change_fast": round(btc_change_fast, 6),
            "btc_change_slow": round(btc_change_slow, 6),
            "local_change_fast": round(local_fast, 6),
            "local_change_slow": round(local_slow, 6),
            "meeting_focus": meeting_notes.get("next_6h_focus", []),
        }
