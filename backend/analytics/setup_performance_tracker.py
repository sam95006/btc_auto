from collections import defaultdict

from config.growth_mode_config import SETUP_MIN_SAMPLE, SETUP_MIN_WIN_RATE


class SetupPerformanceTracker:
    def __init__(self):
        self.stats = defaultdict(
            lambda: {
                "wins": 0,
                "losses": 0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "sample_size": 0,
            }
        )

    def _key(self, fleet, setup_type, regime):
        return f"{str(fleet or '').upper()}|{setup_type or 'unknown'}|{regime or 'normal'}"

    def record_outcome(self, fleet, setup_type, regime, pnl):
        key = self._key(fleet, setup_type, regime)
        bucket = self.stats[key]
        pnl = float(pnl or 0.0)
        bucket["sample_size"] += 1
        if pnl > 0:
            bucket["wins"] += 1
            bucket["gross_profit"] += pnl
        else:
            bucket["losses"] += 1
            bucket["gross_loss"] += abs(pnl)

    def get_stats(self, fleet, setup_type, regime):
        bucket = self.stats[self._key(fleet, setup_type, regime)]
        sample_size = int(bucket["sample_size"])
        wins = int(bucket["wins"])
        win_rate = wins / sample_size if sample_size else 0.5
        gross_profit = float(bucket["gross_profit"])
        gross_loss = float(bucket["gross_loss"])
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (2.0 if gross_profit > 0 else 1.0)
        expectancy = (gross_profit - gross_loss) / sample_size if sample_size else 0.0
        blocked = sample_size >= SETUP_MIN_SAMPLE and win_rate < SETUP_MIN_WIN_RATE
        return {
            "sample_size": sample_size,
            "wins": wins,
            "losses": int(bucket["losses"]),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 4),
            "expectancy": round(expectancy, 4),
            "blocked": blocked,
        }

    def export_state(self):
        return dict(self.stats)

    def import_state(self, payload=None):
        payload = payload or {}
        self.stats = defaultdict(
            lambda: {
                "wins": 0,
                "losses": 0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "sample_size": 0,
            },
            payload,
        )
