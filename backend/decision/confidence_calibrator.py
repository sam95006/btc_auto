class ConfidenceCalibrator:
    def calibrate(
        self,
        raw_confidence,
        fleet_recent_win_rate_factor,
        strategy_performance_factor,
        regime_success_factor,
        market_context_factor,
        penalty_factor,
    ):
        adjusted = float(raw_confidence or 0.0)
        adjusted *= fleet_recent_win_rate_factor
        adjusted *= strategy_performance_factor
        adjusted *= regime_success_factor
        adjusted *= market_context_factor
        adjusted *= penalty_factor
        return max(0.0, min(1.0, adjusted))

