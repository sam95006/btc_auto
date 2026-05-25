from __future__ import annotations

from config.compound_capital_config import COMPOUND_REINVEST_ENABLED
from backend.config.capital_config import FUTURES_RESERVE_RATIO


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class CompoundCapitalService:
    """Expose live-equity reinvest base for fleet/RADAR sizing (full wallet, not fixed baseline)."""

    def build_snapshot(self, futures_equity, daily_payload=None, growth_status=None):
        equity = _safe_float(futures_equity)
        daily = dict(daily_payload or {})
        growth_status = dict(growth_status or {})
        start_equity = _safe_float(daily.get("start_equity") or daily.get("reinvest_base_equity"))
        yesterday_close = _safe_float(daily.get("yesterday_close_equity"))
        if start_equity <= 0 and equity > 0:
            start_equity = equity
        deployable_pool = max(equity * (1.0 - float(FUTURES_RESERVE_RATIO)), 0.0) if equity > 0 else 0.0
        reinvest_base = start_equity if COMPOUND_REINVEST_ENABLED and start_equity > 0 else equity
        growth_factor = (equity / reinvest_base) if reinvest_base > 0 and equity > 0 else 1.0
        return {
            "enabled": bool(COMPOUND_REINVEST_ENABLED),
            "reinvest_base_equity": round(reinvest_base, 4),
            "yesterday_close_equity": round(yesterday_close, 4) if yesterday_close > 0 else None,
            "live_futures_equity": round(equity, 4),
            "deployable_pool": round(deployable_pool, 4),
            "reserve_ratio": round(float(FUTURES_RESERVE_RATIO), 4),
            "growth_factor_vs_day_open": round(growth_factor, 4),
            "day": daily.get("day"),
            "is_positive_day": bool(daily.get("is_positive_day")),
            "daily_target_hit": bool(growth_status.get("daily_target_hit")),
            "mode": growth_status.get("mode"),
            "note": "每日開盤權益 = 昨日收盤權益復投；下單預算來自即時合約總權益分配。",
        }
