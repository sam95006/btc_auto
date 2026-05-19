from collections import defaultdict, deque
from datetime import datetime, timedelta


class SignalMemoryEngine:
    def __init__(self):
        self.signal_log = deque(maxlen=500)
        self.loss_patterns = deque(maxlen=120)
        self.direction_failures = defaultdict(lambda: {"BUY": 0, "SELL": 0})
        self.direction_pauses = {}
        self.regime_stats = defaultdict(lambda: {"wins": 0, "losses": 0})
        self.regime_pauses = {}

    def import_state(self, payload=None):
        payload = payload or {}
        self.signal_log = deque(payload.get("signal_log", []), maxlen=500)
        self.loss_patterns = deque(payload.get("loss_patterns", []), maxlen=120)
        self.direction_failures = defaultdict(
            lambda: {"BUY": 0, "SELL": 0},
            payload.get("direction_failures", {}),
        )
        self.direction_pauses = payload.get("direction_pauses", {})
        self.regime_stats = defaultdict(
            lambda: {"wins": 0, "losses": 0},
            payload.get("regime_stats", {}),
        )
        self.regime_pauses = payload.get("regime_pauses", {})

    def export_state(self):
        return {
            "signal_log": list(self.signal_log),
            "loss_patterns": list(self.loss_patterns),
            "direction_failures": dict(self.direction_failures),
            "direction_pauses": dict(self.direction_pauses),
            "regime_stats": dict(self.regime_stats),
            "regime_pauses": dict(self.regime_pauses),
        }

    def _is_paused_until(self, pause_until):
        if not pause_until:
            return False
        try:
            return datetime.now() < datetime.fromisoformat(pause_until)
        except Exception:
            return False

    def inspect(self, fleet, side, strategy_key, regime, setup_type, market_context):
        penalties = []
        penalty_factor = 1.0

        direction_pause_key = f"{fleet}:{side}"
        regime_pause_key = f"{strategy_key}:{regime}"
        if self._is_paused_until(self.direction_pauses.get(direction_pause_key)):
            return {
                "blocked": True,
                "reject_reason": "direction_cooldown_active",
                "penalty_factor": 0.0,
                "penalties": ["direction_cooldown_active"],
            }
        if self._is_paused_until(self.regime_pauses.get(regime_pause_key)):
            return {
                "blocked": True,
                "reject_reason": "strategy_regime_paused",
                "penalty_factor": 0.0,
                "penalties": ["strategy_regime_paused"],
            }

        similar_losses = 0
        for pattern in self.loss_patterns:
            if pattern.get("fleet") != fleet:
                continue
            if pattern.get("side") != side:
                continue
            if pattern.get("setup_type") != setup_type:
                continue
            if pattern.get("market_regime") != regime:
                continue
            if bool(pattern.get("high_volatility")) == bool(market_context.get("volatility_percentile", 0.0) > 0.8):
                similar_losses += 1

        if similar_losses:
            penalties.append("similar_loss_pattern")
            penalty_factor -= min(0.08 * similar_losses, 0.24)

        return {
            "blocked": False,
            "reject_reason": "",
            "penalty_factor": max(0.4, penalty_factor),
            "penalties": penalties,
        }

    def record_signal(self, payload):
        self.signal_log.append(payload)

    def record_trade_outcome(self, fleet, side, strategy_key, regime, setup_type, market_context, pnl):
        won = float(pnl or 0.0) > 0.0
        regime_key = f"{strategy_key}:{regime}"
        if won:
            self.direction_failures[fleet][side] = 0
            self.regime_stats[regime_key]["wins"] += 1
        else:
            self.direction_failures[fleet][side] += 1
            self.regime_stats[regime_key]["losses"] += 1
            self.loss_patterns.append(
                {
                    "fleet": fleet,
                    "side": side,
                    "setup_type": setup_type,
                    "market_regime": regime,
                    "high_volatility": market_context.get("volatility_percentile", 0.0) > 0.8,
                }
            )

        if self.direction_failures[fleet][side] >= 3:
            self.direction_pauses[f"{fleet}:{side}"] = (datetime.now() + timedelta(minutes=30)).isoformat()

        stats = self.regime_stats[regime_key]
        total = stats["wins"] + stats["losses"]
        if total >= 5 and stats["wins"] / total < 0.4:
            self.regime_pauses[regime_key] = (datetime.now() + timedelta(minutes=30)).isoformat()

