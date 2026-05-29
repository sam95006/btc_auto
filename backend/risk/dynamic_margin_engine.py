from config.leverage_config import CONFIDENCE_SIZING_BANDS


class DynamicMarginEngine:
    """Map 0–1 confidence -> margin multiplier & deployable-pool share (aligned with leverage bands)."""

    def calculate_proposed_margin(self, confidence_score):
        confidence = max(0.0, min(1.0, float(confidence_score or 0.0)))
        if confidence < 0.35:
            return {
                "confidence_score": confidence,
                "allowed": False,
                "margin_mult": 0.0,
                "deployable_pct": 0.0,
                "reason": "confidence_below_trade_threshold",
            }

        for band in CONFIDENCE_SIZING_BANDS:
            if band["min"] <= confidence < band["max"]:
                return {
                    "confidence_score": confidence,
                    "allowed": True,
                    "margin_mult": float(band["margin_mult"]),
                    "deployable_pct": float(band["deployable_pct"]),
                    "band_leverage": int(band["leverage"]),
                    "reason": "confidence_band_match",
                }

        last = CONFIDENCE_SIZING_BANDS[-1]
        return {
            "confidence_score": confidence,
            "allowed": True,
            "margin_mult": float(last["margin_mult"]),
            "deployable_pct": float(last["deployable_pct"]),
            "band_leverage": int(last["leverage"]),
            "reason": "confidence_upper_band_fallback",
        }
