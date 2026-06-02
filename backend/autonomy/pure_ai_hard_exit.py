"""Mandatory Pure AI exits — ROE / USD stop-loss and partial take-profit (no LLM veto)."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.autonomy.ai_flexible_evaluator import _position_age_hours
from config.pure_ai_trading_config import (
    PURE_AI_HARD_EXIT_ENABLED,
    PURE_AI_PARTIAL_FRACTION,
    PURE_AI_SL_ABS_USD,
    PURE_AI_SL_PCT_ON_MARGIN,
    PURE_AI_TP_ABS_USD,
    PURE_AI_TP_FULL_PCT,
    PURE_AI_TP_PARTIAL_PCT,
    pure_ai_active,
)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _pnl_pct_on_margin(position: Dict[str, Any]) -> float:
    margin = _safe_float(position.get("margin"))
    pnl = _safe_float(position.get("unrealized_pnl"))
    if margin <= 0:
        return 0.0
    return round((pnl / margin) * 100.0, 2)


def collect_pure_ai_hard_exits(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Hard TP/SL for testnet Pure AI — runs every tick, cannot be disabled by LLM_ONLY."""
    if not pure_ai_active() or not PURE_AI_HARD_EXIT_ENABLED:
        return []
    actions: List[Dict[str, Any]] = []
    for item in list(positions or []):
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper()
        if not symbol:
            continue
        qty = abs(_safe_float(item.get("quantity") or item.get("signed_quantity")))
        margin = _safe_float(item.get("margin"))
        if qty <= 0 or margin <= 0:
            continue
        fleet = str(item.get("fleet") or "RADAR").upper()
        pnl = _safe_float(item.get("unrealized_pnl"))
        pnl_pct = _pnl_pct_on_margin(item)
        age_h = _position_age_hours(item)

        # Catastrophic loss (isolated margin blow-through on testnet UI)
        if pnl_pct <= -PURE_AI_SL_PCT_ON_MARGIN * 2.5 or pnl <= -max(PURE_AI_SL_ABS_USD * 2, margin * 0.85):
            actions.append(
                _exit_row(
                    symbol,
                    fleet,
                    action="reduce_or_close",
                    fraction=1.0,
                    reason=f"pure_ai_emergency_sl:{round(pnl_pct, 1)}pct:{round(pnl, 2)}u",
                    urgency="critical",
                )
            )
            continue

        # Stop loss
        if pnl_pct <= -PURE_AI_SL_PCT_ON_MARGIN or pnl <= -PURE_AI_SL_ABS_USD:
            actions.append(
                _exit_row(
                    symbol,
                    fleet,
                    action="reduce_or_close",
                    fraction=1.0,
                    reason=f"pure_ai_stop_loss:{round(pnl_pct, 1)}pct:{round(pnl, 2)}u",
                    urgency="critical",
                )
            )
            continue

        # Take profit — full
        if pnl_pct >= PURE_AI_TP_FULL_PCT or pnl >= PURE_AI_TP_ABS_USD * 2.5:
            actions.append(
                _exit_row(
                    symbol,
                    fleet,
                    action="reduce_or_close",
                    fraction=1.0,
                    reason=f"pure_ai_take_profit_full:{round(pnl_pct, 1)}pct:{round(pnl, 2)}u",
                    urgency="high",
                )
            )
            continue

        # Take profit — partial (sell half / reduce)
        if pnl_pct >= PURE_AI_TP_PARTIAL_PCT or pnl >= PURE_AI_TP_ABS_USD:
            actions.append(
                _exit_row(
                    symbol,
                    fleet,
                    action="take_partial_profit",
                    fraction=PURE_AI_PARTIAL_FRACTION,
                    reason=f"pure_ai_take_profit_partial:{round(pnl_pct, 1)}pct:{round(pnl, 2)}u:age{round(age_h, 1)}h",
                    urgency="high",
                )
            )
    return actions


def _exit_row(
    symbol: str,
    fleet: str,
    *,
    action: str,
    fraction: float,
    reason: str,
    urgency: str,
) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "fleet": fleet,
        "action": action,
        "fraction": round(float(fraction), 4),
        "confidence": 0.96,
        "reason": reason[:200],
        "source": "pure_ai_hard_exit",
        "urgency": urgency,
    }


def merge_exit_actions_prefer_hard(
    hard: List[Dict[str, Any]],
    others: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_symbol: Dict[str, Dict[str, Any]] = {}
    for item in list(others or []):
        symbol = str(item.get("symbol") or "").upper()
        if symbol:
            by_symbol[symbol] = item
    for item in list(hard or []):
        symbol = str(item.get("symbol") or "").upper()
        if symbol:
            by_symbol[symbol] = item
    return list(by_symbol.values())
