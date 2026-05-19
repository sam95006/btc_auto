class WalkForwardEvaluator:
    """Phase 3 scaffold: lightweight rolling evaluation over recent trade outcomes."""

    def __init__(self, window_size=30, step_size=10):
        self.window_size = max(5, int(window_size))
        self.step_size = max(1, int(step_size))

    def evaluate(self, trade_results):
        rows = list(trade_results or [])
        if len(rows) < self.window_size:
            return {
                "ready": False,
                "reason": "insufficient_sample",
                "sample_size": len(rows),
                "windows": [],
            }

        windows = []
        for start in range(0, len(rows) - self.window_size + 1, self.step_size):
            chunk = rows[start : start + self.window_size]
            wins = sum(1 for item in chunk if float(item.get("pnl", 0.0) or 0.0) > 0)
            total_pnl = sum(float(item.get("pnl", 0.0) or 0.0) for item in chunk)
            win_rate = wins / len(chunk)
            windows.append(
                {
                    "start_index": start,
                    "sample_size": len(chunk),
                    "win_rate": round(win_rate, 4),
                    "total_pnl": round(total_pnl, 4),
                    "avg_pnl": round(total_pnl / len(chunk), 4),
                }
            )

        positive_windows = sum(1 for item in windows if item["total_pnl"] > 0)
        stability = positive_windows / len(windows) if windows else 0.0
        return {
            "ready": True,
            "reason": "walk_forward_ready",
            "sample_size": len(rows),
            "window_size": self.window_size,
            "step_size": self.step_size,
            "window_count": len(windows),
            "positive_window_ratio": round(stability, 4),
            "latest_window": windows[-1] if windows else None,
            "windows": windows[-5:],
        }
