from __future__ import annotations

from config.quality_gates_config import (
    MIN_TRADE_CONFIDENCE,
    QUALITY_GATE_ENABLED,
    TARGET_WIN_RATE,
    WALK_FORWARD_MIN_WIN_RATE,
)
from config.revenue_target_config import REVENUE_GROWTH_MODE


def _safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(float(value or default))
    except Exception:
        return int(default)


class StrategyEvolutionService:
    """Auto-tighten growth directives from walk-forward + rotation signals (no fleet engine rewrite)."""

    def evolve_growth_directives(
        self,
        growth_directives,
        walk_forward_status=None,
        rotation=None,
        recent_trades=None,
    ):
        directives = dict(growth_directives or {})
        walk_forward_status = walk_forward_status or {}
        rotation = rotation or {}
        trades = list(recent_trades or [])[:80]

        if walk_forward_status.get("ready"):
            positive_ratio = _safe_float(walk_forward_status.get("positive_window_ratio"))
            latest = walk_forward_status.get("latest_window") or {}
            latest_wr = _safe_float(latest.get("win_rate"))
            if positive_ratio < 0.35 or latest_wr < WALK_FORWARD_MIN_WIN_RATE:
                directives["min_win_rate"] = max(
                    _safe_float(directives.get("min_win_rate"), WALK_FORWARD_MIN_WIN_RATE),
                    WALK_FORWARD_MIN_WIN_RATE,
                )
                directives["position_multiplier"] = min(
                    _safe_float(directives.get("position_multiplier"), 1.0),
                    0.82,
                )
                directives["max_leverage"] = min(
                    _safe_int(directives.get("max_leverage"), 20),
                    12,
                )
                directives["evolution_mode"] = "tighten_guards"
            elif positive_ratio > 0.65 and latest_wr >= TARGET_WIN_RATE:
                directives["position_multiplier"] = min(
                    _safe_float(directives.get("position_multiplier"), 1.0) * 1.05,
                    1.0,
                )
                directives["evolution_mode"] = "stable_scale"

        rec = str(rotation.get("recommendation") or "hold")
        if rec == "tighten_guards":
            directives["min_win_rate"] = max(
                _safe_float(directives.get("min_win_rate"), TARGET_WIN_RATE),
                TARGET_WIN_RATE,
            )
            directives["position_multiplier"] = min(_safe_float(directives.get("position_multiplier"), 1.0), 0.78)
            directives["evolution_mode"] = "rotation_tighten"
        elif rec == "pause_rotation":
            if REVENUE_GROWTH_MODE:
                directives["evolution_mode"] = "rotation_hold"
                directives["position_multiplier"] = min(_safe_float(directives.get("position_multiplier"), 1.0), 0.92)
            else:
                directives["evolution_mode"] = "rotation_paused"

        if QUALITY_GATE_ENABLED and len(trades) >= 10:
            wins = sum(1 for item in trades if _safe_float(item.get("pnl")) > 0)
            win_rate = wins / len(trades)
            directives["recent_win_rate"] = round(win_rate, 4)
            directives["min_trade_confidence"] = max(
                _safe_float(directives.get("min_trade_confidence"), MIN_TRADE_CONFIDENCE),
                MIN_TRADE_CONFIDENCE if win_rate < TARGET_WIN_RATE else MIN_TRADE_CONFIDENCE * 0.95,
            )
            if win_rate < TARGET_WIN_RATE * 0.8:
                directives["block_reason"] = directives.get("block_reason") or "quality_gate_weak_window"
                if not REVENUE_GROWTH_MODE:
                    directives["block_new_entries"] = bool(directives.get("block_new_entries")) or win_rate < 0.35
                elif win_rate < 0.25:
                    directives["block_new_entries"] = True

        directives["strategy_evolution_applied"] = True
        return directives
