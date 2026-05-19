from config.leverage_config import CONFIDENCE_LEVERAGE_TABLE


class DynamicLeverageEngine:
    def calculate_proposed_leverage(self, confidence_score):
        confidence = max(0.0, min(1.0, float(confidence_score or 0.0)))
        if confidence < 0.35:
            return {
                "confidence_score": confidence,
                "allowed": False,
                "proposed_leverage": 0,
                "reason": "confidence_below_trade_threshold",
            }

        for band in CONFIDENCE_LEVERAGE_TABLE:
            if band["min"] <= confidence < band["max"]:
                return {
                    "confidence_score": confidence,
                    "allowed": True,
                    "proposed_leverage": int(band["leverage"]),
                    "reason": "confidence_band_match",
                }

        return {
            "confidence_score": confidence,
            "allowed": True,
            "proposed_leverage": int(CONFIDENCE_LEVERAGE_TABLE[-1]["leverage"]),
            "reason": "confidence_upper_band_fallback",
        }
