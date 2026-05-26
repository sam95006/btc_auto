from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.compound_capital_config import MEETING_TIMEZONE
from config.risk_budget_config import MONTHLY_DRAWDOWN_GUARD_ENABLED, MONTHLY_MAX_DRAWDOWN_PCT


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


def _state_path():
    import os

    data_dir = str(os.getenv("NEXUS_DATA_DIR", "") or "").strip()
    if data_dir:
        base = Path(data_dir) / "logs"
    else:
        base = Path(__file__).resolve().parents[2] / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base / "monthly_risk_state.json"


class MonthlyDrawdownGuard:
    """Peak-to-trough monthly drawdown cap (default 10%)."""

    def __init__(self):
        self.last_status = {}

    def _month_key(self):
        try:
            tz = ZoneInfo(MEETING_TIMEZONE)
        except Exception:
            tz = ZoneInfo("Asia/Taipei")
        return datetime.now(tz).strftime("%Y-%m")

    def _load_state(self):
        path = _state_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, payload):
        path = _state_path()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def evaluate(self, futures_equity):
        equity = max(_safe_float(futures_equity), 0.0)
        month = self._month_key()
        state = self._load_state()

        if state.get("month") != month:
            state = {
                "month": month,
                "month_start_equity": equity,
                "month_peak_equity": equity,
                "updated_at": datetime.now().isoformat(),
            }
        else:
            state["month_peak_equity"] = max(_safe_float(state.get("month_peak_equity")), equity)
            state["month_start_equity"] = _safe_float(state.get("month_start_equity"), equity) or equity
            state["updated_at"] = datetime.now().isoformat()

        peak = max(_safe_float(state.get("month_peak_equity")), equity, 1e-9)
        drawdown_pct = max(0.0, (peak - equity) / peak)
        limit = max(0.01, float(MONTHLY_MAX_DRAWDOWN_PCT or 0.10))
        breached = drawdown_pct >= limit

        block = bool(MONTHLY_DRAWDOWN_GUARD_ENABLED and breached and equity > 0)
        status = {
            "enabled": bool(MONTHLY_DRAWDOWN_GUARD_ENABLED),
            "month": month,
            "month_start_equity": round(_safe_float(state.get("month_start_equity")), 4),
            "month_peak_equity": round(peak, 4),
            "current_equity": round(equity, 4),
            "drawdown_pct": round(drawdown_pct * 100, 3),
            "max_drawdown_pct": round(limit * 100, 2),
            "breached": breached,
            "block_new_entries": block,
            "block_reason": "monthly_max_drawdown" if block else "",
        }
        self._save_state(state)
        self.last_status = status
        return status
