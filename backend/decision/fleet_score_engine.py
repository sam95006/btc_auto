from collections import defaultdict
from datetime import datetime, timedelta


class FleetScoreEngine:
    def __init__(self):
        self.pause_until = {}

    def import_state(self, payload=None):
        payload = payload or {}
        self.pause_until = payload.get("pause_until", {})

    def export_state(self):
        return {"pause_until": dict(self.pause_until)}

    def _is_paused(self, fleet):
        until = self.pause_until.get(fleet)
        if not until:
            return False
        try:
            return datetime.now() < datetime.fromisoformat(until)
        except Exception:
            return False

    def evaluate(self, fleet, trades, capital_snapshot, loan_snapshot, market_context, audits, meeting_notes=None):
        meeting_notes = meeting_notes or {}
        closes = [item for item in trades if item.get("event") == "CLOSE" and item.get("fleet") == fleet][:20]
        wins = [item for item in closes if float(item.get("pnl", 0.0)) > 0]
        losses = [item for item in closes if float(item.get("pnl", 0.0)) <= 0]
        recent_win_rate = len(wins) / len(closes) if closes else 0.5
        gross_profit = sum(max(0.0, float(item.get("pnl", 0.0))) for item in closes)
        gross_loss = abs(sum(min(0.0, float(item.get("pnl", 0.0))) for item in closes))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (2.0 if gross_profit > 0 else 1.0)
        fleets_cap = dict(capital_snapshot.get("fleets") or {})
        acct = fleets_cap.get(fleet) or {"realized_pnl": 0.0, "allocated": 0.0, "available": 0.0, "frozen": 0.0}
        today_pnl = float(acct.get("realized_pnl", 0.0) or 0.0)
        loan_pressure = 0.0
        loan_item = loan_snapshot.get(fleet, {})
        if loan_item:
            loan_pressure = float(loan_item.get("principal", 0.0)) / max(float(loan_item.get("limit", 1.0) or 1.0), 1.0)
        volatility = float(market_context.get("volatility_percentile", 0.0) or 0.0)
        signal_rows = [row for row in audits if row.get("symbol") == fleet][:20]
        signal_efficiency = (
            sum(1 for row in signal_rows if row.get("approved")) / len(signal_rows)
            if signal_rows
            else 0.5
        )

        score = 100.0
        score -= max(0.0, (0.5 - recent_win_rate) * 70)
        score -= max(0.0, (1.0 - min(profit_factor, 2.0)) * 18)
        score -= max(0.0, loan_pressure * 20)
        score -= max(0.0, volatility * 15)
        if today_pnl < 0:
            score -= min(20.0, abs(today_pnl) / 3.0)
        score += max(0.0, (signal_efficiency - 0.5) * 20)
        if meeting_notes.get("risk_notes"):
            score -= min(8.0, len(meeting_notes.get("risk_notes", [])) * 2.0)
        if meeting_notes.get("forbidden_actions"):
            score -= min(10.0, len(meeting_notes.get("forbidden_actions", [])) * 2.5)
        score = max(0.0, min(100.0, score))

        state = "NORMAL"
        position_multiplier = 1.0
        leverage_multiplier = 1.0
        if self._is_paused(fleet):
            state = "PAUSED"
            position_multiplier = 0.0
            leverage_multiplier = 0.0
        elif score < 40:
            state = "PAUSED"
            position_multiplier = 0.0
            leverage_multiplier = 0.0
            self.pause_until[fleet] = (datetime.now() + timedelta(hours=1)).isoformat()
        elif score < 60:
            state = "DEFENSIVE"
            position_multiplier = 0.5
            leverage_multiplier = 0.75
        elif score < 80:
            state = "CAUTIOUS"
            position_multiplier = 0.7
            leverage_multiplier = 0.85

        return {
            "fleet_score": round(score, 4),
            "state": state,
            "position_multiplier": position_multiplier,
            "leverage_multiplier": leverage_multiplier,
            "recent_win_rate": round(recent_win_rate, 4),
            "profit_factor": round(profit_factor, 4),
            "today_pnl": round(today_pnl, 4),
            "signal_efficiency": round(signal_efficiency, 4),
            "strategy_recent_win_rate": round(recent_win_rate, 4),
        }
