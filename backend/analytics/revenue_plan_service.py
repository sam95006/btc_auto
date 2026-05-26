from __future__ import annotations

from config.revenue_target_config import MONTHLY_REVENUE_CAPITAL_FRACTION, REVENUE_GROWTH_MODE


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


class RevenuePlanService:
    """Business-plan style milestones for futures-capital revenue targets."""

    def build_plan(self, monthly_report, compound_capital=None, maturity_radar=None):
        report = dict(monthly_report or {})
        compound = dict(compound_capital or {})
        maturity = dict(maturity_radar or {})
        equity = _safe_float(report.get("current_futures_equity") or compound.get("live_futures_equity"))
        target = _safe_float(report.get("target_usd"))
        deployable = _safe_float(compound.get("deployable_pool") or equity * 0.85)
        net = _safe_float(report.get("realized_pnl_net"))
        req_pct = _safe_float(report.get("required_monthly_return_pct"))

        stages = [
            {"stage": 1, "label": "樣本累積", "target_usd": round(target * 0.05, 2), "note": "月淨利 ≥ 5% 月目標，驗證管線"},
            {"stage": 2, "label": "流程驗證", "target_usd": round(target * 0.15, 2), "note": "月淨利 ≥ 15% 月目標，費後期望值 ≥ 0"},
            {"stage": 3, "label": "月目標三分之一", "target_usd": round(target, 2), "note": f"合約資金 × {MONTHLY_REVENUE_CAPITAL_FRACTION:.2f}"},
            {"stage": 4, "label": "複利放大", "target_usd": round(target * 1.5, 2), "note": "達標後提高 deployable_pool 利用率"},
        ]
        current_stage = 0
        for stage in stages:
            if net >= _safe_float(stage.get("target_usd")):
                current_stage = int(stage["stage"])

        avg_trade_needed = 0.0
        est_trades = 0
        if target > 0 and equity > 0:
            est_trades = max(40, int(300 / max(req_pct, 1.0)))
            avg_trade_needed = round(target / est_trades, 2)

        return {
            "revenue_growth_mode": bool(REVENUE_GROWTH_MODE),
            "capital_scope": "futures_only",
            "futures_equity_usd": round(equity, 2),
            "deployable_pool_usd": round(deployable, 2),
            "monthly_target_usd": round(target, 2),
            "monthly_net_usd": round(net, 2),
            "required_monthly_return_pct": round(req_pct, 2),
            "current_stage": current_stage,
            "stages": stages,
            "est_trades_per_month": est_trades if target > 0 else 0,
            "est_avg_pnl_per_trade_usd": avg_trade_needed,
            "maturity_overall": maturity.get("overall_score"),
            "honest_note": (
                "月目標依合約權益動態計算，不保證達成；現貨資金不計入交易預算。"
                if equity > 0
                else "合約權益為 0，無法計算可持續月目標。"
            ),
        }
