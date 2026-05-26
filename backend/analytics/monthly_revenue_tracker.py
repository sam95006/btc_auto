from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config.revenue_target_config import (
    MONTHLY_REVENUE_CAPITAL_FRACTION,
    MONTHLY_REVENUE_TARGET_MODE,
    MONTHLY_REVENUE_TARGET_USD,
)


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class MonthlyRevenueTracker:
    """Track realized futures PnL against monthly revenue target (contract capital only)."""

    def _month_key(self):
        import os

        tz_name = str(os.getenv("NEXUS_MEETING_TIMEZONE", "Asia/Taipei") or "Asia/Taipei").strip()
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Asia/Taipei")
        return datetime.now(tz).strftime("%Y-%m")

    def resolve_target_usd(self, futures_equity):
        equity = max(_safe_float(futures_equity), 0.0)
        mode = MONTHLY_REVENUE_TARGET_MODE
        if mode == "fixed":
            return round(max(MONTHLY_REVENUE_TARGET_USD, 0.0), 2)
        if mode == "third_of_legacy_10k":
            return round(max(MONTHLY_REVENUE_TARGET_USD, 10000.0 / 3.0), 2)
        return round(equity * max(MONTHLY_REVENUE_CAPITAL_FRACTION, 0.0), 2)

    def _month_realized_from_trades(self, trade_results, month):
        gross = 0.0
        fees = 0.0
        count = 0
        for item in list(trade_results or []):
            if str(item.get("market_type") or "futures") != "futures":
                continue
            event = str(item.get("event") or "").upper()
            if event not in {"CLOSE", "LIVE"}:
                continue
            ts = str(item.get("timestamp") or item.get("time") or "")
            if len(ts) >= 7 and ts[:7] != month:
                continue
            pnl = _safe_float(item.get("pnl"))
            gross += pnl
            fees += abs(_safe_float(item.get("commission")))
            count += 1
        return gross, fees, count

    def build_report(self, futures_equity, trade_results=None, start_equity=None):
        month = self._month_key()
        equity = max(_safe_float(futures_equity), 0.0)
        base_equity = max(_safe_float(start_equity), equity)

        gross, fees, trade_count = self._month_realized_from_trades(trade_results, month)
        net_realized = round(gross - fees, 4)
        target_usd = self.resolve_target_usd(equity if equity > 0 else base_equity)
        progress_pct = round((net_realized / target_usd) * 100, 2) if target_usd > 0 else 0.0
        remaining = round(max(target_usd - net_realized, 0.0), 2)
        base = equity if equity > 0 else base_equity
        required_monthly_return_pct = round((target_usd / base) * 100, 2) if base > 0 else 0.0

        return {
            "month": month,
            "target_mode": MONTHLY_REVENUE_TARGET_MODE,
            "target_usd": target_usd,
            "start_futures_equity": round(base_equity, 4),
            "current_futures_equity": round(equity, 4),
            "realized_pnl_gross": round(gross, 4),
            "fees_usd": round(fees, 4),
            "realized_pnl_net": net_realized,
            "progress_pct": progress_pct,
            "remaining_usd": remaining,
            "target_met": net_realized >= target_usd if target_usd > 0 else False,
            "trade_count": trade_count,
            "required_monthly_return_pct": required_monthly_return_pct,
            "capital_scope": "futures_only",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
