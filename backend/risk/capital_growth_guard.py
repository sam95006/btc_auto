from config.growth_mode_config import (
    BOLD_MIN_QUALITY,
    BOLD_TESTNET_ENABLED,
    CAPITAL_FLOOR,
    DAILY_A_PLUS_QUALITY,
    DAILY_DEFENSE_QUALITY,
    DAILY_MAX_LOSS_PCT,
    DAILY_PNL_TARGET_PCT,
    FLOOR_BUFFER_PCT,
    FLOOR_GUARD_MAX_LEVERAGE,
    FLOOR_GUARD_MIN_QUALITY,
    GROWTH_MAX_LEVERAGE,
    GROWTH_MIN_APPROVAL,
    GROWTH_MIN_QUALITY,
    GROWTH_MIN_WIN_RATE,
    GROWTH_POSITION_BOOST,
    GROWTH_TARGET,
    RECOVERY_MAX_LEVERAGE,
    RECOVERY_MIN_APPROVAL,
    RECOVERY_MIN_QUALITY,
    RECOVERY_MIN_WIN_RATE,
)
from backend.analytics.daily_pnl_tracker import DailyPnlTracker


class CapitalGrowthGuard:
    def __init__(self, daily_tracker=None):
        self.daily_tracker = daily_tracker or DailyPnlTracker()
        self.last_status = {}

    def evaluate(self, futures_equity):
        equity = float(futures_equity or 0.0)
        if equity <= 0:
            status = {
                "mode": "SYNC_WAIT",
                "block_new_entries": False,
                "block_reason": "",
                "min_quality_score": round(GROWTH_MIN_QUALITY, 4),
                "min_approval_score": round(GROWTH_MIN_APPROVAL, 4),
                "min_win_rate": round(GROWTH_MIN_WIN_RATE, 4),
                "max_leverage": round(GROWTH_MAX_LEVERAGE, 4),
                "position_multiplier": round(GROWTH_POSITION_BOOST if BOLD_TESTNET_ENABLED else 1.0, 4),
                "allow_aggressive": bool(BOLD_TESTNET_ENABLED),
                "capital_floor": round(CAPITAL_FLOOR, 4),
                "growth_target": round(GROWTH_TARGET, 4),
                "futures_equity": 0.0,
                "above_floor": False,
                "progress_to_floor": 0.0,
                "progress_to_target": 0.0,
                "daily": self.daily_tracker.update(equity),
                "daily_target_usd": 0.0,
                "daily_target_hit": False,
            }
            self.last_status = status
            return status

        daily = self.daily_tracker.update(equity)
        daily_pnl = float(daily.get("daily_pnl", 0.0) or 0.0)
        daily_pnl_pct = float(daily.get("daily_pnl_pct", 0.0) or 0.0)
        floor_buffer = CAPITAL_FLOOR * FLOOR_BUFFER_PCT

        mode = "GROWTH"
        block_new_entries = False
        block_reason = ""
        min_quality = GROWTH_MIN_QUALITY
        min_approval = GROWTH_MIN_APPROVAL
        min_win_rate = GROWTH_MIN_WIN_RATE
        max_leverage = GROWTH_MAX_LEVERAGE
        position_multiplier = GROWTH_POSITION_BOOST if BOLD_TESTNET_ENABLED else 1.0
        allow_aggressive = BOLD_TESTNET_ENABLED

        if equity < CAPITAL_FLOOR:
            mode = "RECOVERY"
            min_quality = RECOVERY_MIN_QUALITY
            min_approval = RECOVERY_MIN_APPROVAL
            min_win_rate = RECOVERY_MIN_WIN_RATE
            max_leverage = RECOVERY_MAX_LEVERAGE
            position_multiplier = 0.85
            allow_aggressive = False
        elif equity < CAPITAL_FLOOR + floor_buffer:
            if BOLD_TESTNET_ENABLED and equity >= CAPITAL_FLOOR:
                mode = "GROWTH"
            else:
                mode = "FLOOR_GUARD"
                min_quality = FLOOR_GUARD_MIN_QUALITY
                min_approval = max(GROWTH_MIN_APPROVAL, 0.60)
                min_win_rate = max(GROWTH_MIN_WIN_RATE, 0.45)
                max_leverage = FLOOR_GUARD_MAX_LEVERAGE
                position_multiplier = 0.9
                allow_aggressive = False

        if daily_pnl < 0:
            mode = "DAILY_DEFENSE" if mode == "GROWTH" else f"{mode}+DAILY_DEFENSE"
            min_quality = max(min_quality, DAILY_DEFENSE_QUALITY)
            min_approval = max(min_approval, 0.64)
            position_multiplier = min(position_multiplier, 0.75)
            allow_aggressive = False
            if daily_pnl_pct <= -DAILY_MAX_LOSS_PCT:
                block_new_entries = True
                block_reason = "daily_loss_limit_reached"
            elif daily_pnl < 0:
                min_quality = max(min_quality, DAILY_A_PLUS_QUALITY)

        daily_target = equity * DAILY_PNL_TARGET_PCT
        daily_target_hit = daily_pnl >= daily_target > 0

        progress_to_floor = 0.0
        if equity < CAPITAL_FLOOR:
            progress_to_floor = max(0.0, min(1.0, equity / CAPITAL_FLOOR))
        progress_to_target = 0.0
        if GROWTH_TARGET > CAPITAL_FLOOR:
            progress_to_target = max(0.0, min(1.0, (equity - CAPITAL_FLOOR) / (GROWTH_TARGET - CAPITAL_FLOOR)))

        if BOLD_TESTNET_ENABLED:
            min_quality = min(min_quality, BOLD_MIN_QUALITY)
            if equity >= CAPITAL_FLOOR:
                allow_aggressive = True
                position_multiplier = max(position_multiplier, 0.95)

        status = {
            "mode": mode,
            "block_new_entries": block_new_entries,
            "block_reason": block_reason,
            "min_quality_score": round(min_quality, 4),
            "min_approval_score": round(min_approval, 4),
            "min_win_rate": round(min_win_rate, 4),
            "max_leverage": round(max_leverage, 4),
            "position_multiplier": round(position_multiplier, 4),
            "allow_aggressive": allow_aggressive,
            "capital_floor": round(CAPITAL_FLOOR, 4),
            "growth_target": round(GROWTH_TARGET, 4),
            "futures_equity": round(equity, 4),
            "above_floor": equity >= CAPITAL_FLOOR,
            "progress_to_floor": round(progress_to_floor, 4),
            "progress_to_target": round(progress_to_target, 4),
            "daily": daily,
            "daily_target_usd": round(daily_target, 4),
            "daily_target_hit": daily_target_hit,
        }
        self.last_status = status
        return status
