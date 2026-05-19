class SignalFusionEngine:
    def fuse(self, fleet, price_now, price_prev, news_items, alert_level, market_context=None, meeting_notes=None):
        market_context = market_context or {}
        meeting_notes = meeting_notes or {}
        if alert_level in ("ALERT_RED", "RED"):
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": "alert_level_blocks_entry",
            }

        change = 0.0 if not price_prev else (price_now - price_prev) / price_prev
        news_bias = 0
        for item in news_items:
            targets = item.get("targets", [])
            if fleet in targets or "ALL" in targets:
                news_bias += 1 if item.get("sentiment") == "POSITIVE" else 0
                news_bias -= 1 if item.get("sentiment") == "NEGATIVE" else 0

        trend_strength = float(market_context.get("trend_strength", 0.0) or 0.0)
        local_fast = float(market_context.get("local_change_fast", change) or change)
        volume_confirmed = bool(market_context.get("volume_confirmed"))
        support_distance = float(market_context.get("support_distance", 1.0) or 1.0)
        resistance_distance = float(market_context.get("resistance_distance", 1.0) or 1.0)
        fake_breakout_risk = bool(market_context.get("fake_breakout_risk"))
        btc_bias = market_context.get("btc_market_bias", "NEUTRAL")
        whale_bias = market_context.get("whale_bias", "NEUTRAL")
        whale_follow_strength = float(market_context.get("whale_follow_strength", 0.0) or 0.0)

        forbidden_map = meeting_notes.get("forbidden_actions_map") or {}
        if isinstance(forbidden_map, dict):
            fleet_rules = list(forbidden_map.get(fleet, []) or []) + list(forbidden_map.get("ALL", []) or [])
            if fleet_rules:
                return {
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": "meeting_forbidden_action",
                }

        forbidden_text = " ".join(str(item) for item in meeting_notes.get("forbidden_actions", []))
        if "禁止" in forbidden_text and fleet in forbidden_text:
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": "meeting_forbidden_action",
            }

        if (
            local_fast < (-0.0008 if fleet in {"ETH", "SOL"} else -0.0011)
            and news_bias >= 0
            and trend_strength > -0.04
            and (volume_confirmed or abs(local_fast) > (0.0012 if fleet in {"ETH", "SOL"} else 0.0018))
            and support_distance < (0.16 if fleet in {"ETH", "SOL"} else 0.11)
            and btc_bias != "BEARISH"
        ):
            return {
                "action": "BUY",
                "confidence": min(0.92, abs(local_fast) * 110 + 0.28 + max(0, news_bias) * 0.04),
                "reason": "contextual_pullback_buy",
            }

        if (
            local_fast > (0.001 if fleet in {"ETH", "SOL"} else 0.0013)
            and news_bias <= 0
            and trend_strength < 0.04
            and resistance_distance < (0.16 if fleet in {"ETH", "SOL"} else 0.11)
            and not fake_breakout_risk
        ):
            return {
                "action": "SELL",
                "confidence": min(0.9, abs(local_fast) * 104 + 0.26 + abs(min(0, news_bias)) * 0.04),
                "reason": "contextual_resistance_sell",
            }

        if local_fast > (0.0016 if fleet in {"ETH", "SOL"} else 0.0022) and trend_strength > 0.015 and volume_confirmed and not fake_breakout_risk:
            return {
                "action": "BUY",
                "confidence": min(0.95, 0.48 + local_fast * 95 + trend_strength * 4),
                "reason": "momentum_breakout_long",
            }

        if local_fast < (-0.0016 if fleet in {"ETH", "SOL"} else -0.0022) and trend_strength < -0.015 and volume_confirmed:
            return {
                "action": "SELL",
                "confidence": min(0.95, 0.48 + abs(local_fast) * 95 + abs(trend_strength) * 4),
                "reason": "momentum_breakdown_short",
            }

        if news_bias >= 2 and trend_strength >= 0 and local_fast > 0.0004:
            return {
                "action": "BUY",
                "confidence": min(0.9, 0.52 + local_fast * 40 + min(news_bias, 3) * 0.08),
                "reason": "news_followthrough_long",
            }

        if news_bias <= -2 and trend_strength <= 0 and local_fast < -0.0004:
            return {
                "action": "SELL",
                "confidence": min(0.9, 0.52 + abs(local_fast) * 40 + min(abs(news_bias), 3) * 0.08),
                "reason": "news_followthrough_short",
            }

        if fleet in {"SOL", "PEPE"} and whale_bias == "BULLISH" and local_fast > 0.0005:
            return {
                "action": "BUY",
                "confidence": min(0.96, 0.58 + whale_follow_strength * 0.38 + abs(local_fast) * 46),
                "reason": "radar_whale_follow_long",
            }

        if fleet in {"SOL", "PEPE"} and whale_bias == "BEARISH" and local_fast < -0.0005:
            return {
                "action": "SELL",
                "confidence": min(0.96, 0.58 + whale_follow_strength * 0.38 + abs(local_fast) * 46),
                "reason": "radar_whale_follow_short",
            }

        return {
            "action": "HOLD",
            "confidence": 0.24,
            "reason": "no_high_quality_context",
        }
