class TradeExitAnalyzer:
    def analyze(self, trade):
        pnl = float(trade.get("pnl", 0.0) or 0.0)
        margin = float(trade.get("margin", 0.0) or 0.0)
        pnl_ratio = pnl / margin if margin > 0 else 0.0

        if pnl_ratio > 0.12:
            return {
                "exit_quality": "GOOD",
                "exit_reason": "trend_follow_through_captured",
                "suggestion": "allow_runner_or_trailing_stop",
            }
        if pnl_ratio > 0:
            return {
                "exit_quality": "MEDIUM",
                "exit_reason": "profit_taken_early",
                "suggestion": "consider_partial_take_profit",
            }
        if pnl_ratio < -0.18:
            return {
                "exit_quality": "POOR",
                "exit_reason": "late_stop_loss",
                "suggestion": "cut_earlier_or_reduce_size",
            }
        return {
            "exit_quality": "MEDIUM",
            "exit_reason": "high_volatility_washout",
            "suggestion": "use_trailing_stop_or_scale_out",
        }
