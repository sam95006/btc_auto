from __future__ import annotations

import time

from config.kill_switch_config import (
    KILL_SWITCH_AUTO_FLATTEN,
    KILL_SWITCH_ENABLED,
    KILL_SWITCH_MAX_CONSECUTIVE_LOSSES,
    KILL_SWITCH_SYNC_STALE_SEC,
    KILL_SWITCH_VALIDATION_BLOCK_RATE,
)


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class KillSwitchService:
    """P1 kill-switch v2: sync stale, loss streak, validation choke, daily loss."""

    def evaluate(
        self,
        growth_status=None,
        validation_events=None,
        live_sync=None,
        trading_paused=False,
        trade_results=None,
    ):
        if not KILL_SWITCH_ENABLED:
            return {"triggered": False, "action": "none", "checks": {}}

        growth = dict(growth_status or {})
        validations = list(validation_events or [])
        sync = dict(live_sync or {})
        trades = list(trade_results or [])

        checks = {}
        reasons = []

        if trading_paused and growth.get("kill_switch_reason"):
            return {
                "triggered": True,
                "action": "already_paused",
                "reason": growth.get("kill_switch_reason"),
                "checks": {"manual_or_prior_kill": True},
            }

        if growth.get("daily_max_loss_hit") or growth.get("profit_lock_active"):
            checks["daily_guard"] = True
            if growth.get("daily_max_loss_hit"):
                reasons.append("daily_max_loss")

        updated_ms = int(sync.get("updated_at_ms") or 0)
        if updated_ms:
            age_sec = max(0.0, time.time() - updated_ms / 1000.0)
            checks["sync_age_sec"] = round(age_sec, 1)
            if age_sec > KILL_SWITCH_SYNC_STALE_SEC:
                reasons.append("exchange_sync_stale")

        blocks = sum(1 for item in validations if not item.get("approved"))
        total = len(validations)
        if total >= 20:
            block_rate = blocks / total
            checks["validation_block_rate"] = round(block_rate, 4)
            if block_rate >= KILL_SWITCH_VALIDATION_BLOCK_RATE:
                reasons.append("validation_choke")

        streak = 0
        for item in trades:
            if str(item.get("market_type") or "futures") != "futures":
                continue
            pnl = _safe_float(item.get("pnl"))
            if pnl < 0:
                streak += 1
            elif pnl > 0:
                break
        checks["consecutive_losses"] = streak
        if streak >= KILL_SWITCH_MAX_CONSECUTIVE_LOSSES:
            reasons.append("consecutive_losses")

        triggered = bool(reasons)
        action = "pause_trading"
        if triggered and KILL_SWITCH_AUTO_FLATTEN and "daily_max_loss" in reasons:
            action = "pause_and_flatten"

        return {
            "triggered": triggered,
            "action": action if triggered else "none",
            "reasons": reasons,
            "reason": ",".join(reasons),
            "checks": checks,
        }
