import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.compound_capital_config import COMPOUND_REINVEST_ENABLED, compound_state_path


class DailyPnlTracker:
    def __init__(self, state_path=None):
        root = Path(__file__).resolve().parents[2]
        self.state_path = Path(state_path or compound_state_path() or (root / "logs" / "growth_daily_state.json"))
        self._day = None
        self._start_equity = 0.0
        self._peak_equity = 0.0
        self._yesterday_close_equity = 0.0
        self._last_equity = 0.0
        self._load()

    def _today(self):
        tz_name = str(os.getenv("NEXUS_MEETING_TIMEZONE", "Asia/Taipei") or "Asia/Taipei").strip()
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Asia/Taipei")
        return datetime.now(tz).strftime("%Y-%m-%d")

    def _load(self):
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._day = payload.get("day")
            self._start_equity = float(payload.get("start_equity", 0.0) or 0.0)
            self._peak_equity = float(payload.get("peak_equity", 0.0) or 0.0)
            self._yesterday_close_equity = float(payload.get("yesterday_close_equity", 0.0) or 0.0)
            self._last_equity = float(payload.get("last_equity", 0.0) or 0.0)
        except Exception:
            self._day = None
            self._start_equity = 0.0
            self._peak_equity = 0.0
            self._yesterday_close_equity = 0.0
            self._last_equity = 0.0

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "day": self._day,
            "start_equity": round(self._start_equity, 4),
            "peak_equity": round(self._peak_equity, 4),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def update(self, equity):
        equity = float(equity or 0.0)
        today = self._today()
        if self._day != today:
            if equity > 0:
                if self._last_equity > 0:
                    self._yesterday_close_equity = self._last_equity
                elif self._start_equity > 0:
                    self._yesterday_close_equity = self._start_equity
                self._day = today
                if COMPOUND_REINVEST_ENABLED and self._yesterday_close_equity > 0:
                    self._start_equity = self._yesterday_close_equity
                else:
                    self._start_equity = equity
                self._peak_equity = equity
                self._save()
        elif self._start_equity <= 0 and equity > 0:
            self._day = today
            self._start_equity = equity
            self._peak_equity = equity
            self._save()
        elif equity > self._peak_equity:
            self._peak_equity = equity
            self._save()
        if equity > 0:
            self._last_equity = equity
            self._save()

        if equity <= 0 and self._start_equity > 0:
            return {
                "day": self._day or today,
                "start_equity": round(self._start_equity, 4),
                "current_equity": 0.0,
                "peak_equity": round(self._peak_equity, 4),
                "daily_pnl": 0.0,
                "daily_pnl_pct": 0.0,
                "is_positive_day": True,
                "equity_sync_missing": True,
            }

        daily_pnl = equity - self._start_equity
        daily_pnl_pct = daily_pnl / self._start_equity if self._start_equity > 0 else 0.0
        return {
            "day": self._day,
            "start_equity": round(self._start_equity, 4),
            "reinvest_base_equity": round(self._start_equity, 4),
            "yesterday_close_equity": round(self._yesterday_close_equity, 4) if self._yesterday_close_equity > 0 else None,
            "current_equity": round(equity, 4),
            "peak_equity": round(self._peak_equity, 4),
            "daily_pnl": round(daily_pnl, 4),
            "daily_pnl_pct": round(daily_pnl_pct, 6),
            "is_positive_day": daily_pnl >= 0,
            "compound_reinvest": bool(COMPOUND_REINVEST_ENABLED),
        }
