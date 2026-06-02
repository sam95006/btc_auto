"""Pure AI entry/exit policy — learning guard, trend pyramid, per-tick throttling."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from config.pure_ai_trading_config import (
    PURE_AI_MAX_ENTRIES_PER_TICK,
    PURE_AI_MAX_PYRAMID_PER_TICK,
    PURE_AI_PYRAMID_COOLDOWN_SECONDS,
    pure_ai_respect_learning,
)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _normalize_side(side: str) -> str:
    side = str(side or "").upper()
    if side in {"LONG", "BUY"}:
        return "BUY"
    if side in {"SHORT", "SELL"}:
        return "SELL"
    return side


def build_pure_ai_learning_context(runtime_store, guidance: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    guidance = dict(guidance or {})
    recent_losses: List[Dict[str, Any]] = []
    try:
        trades = list(runtime_store.recent_trade_results(limit=60))
    except Exception:
        trades = []
    for item in trades:
        if not isinstance(item, dict):
            continue
        if str(item.get("strategy_key") or "") != "pure_ai_trader":
            continue
        pnl = _safe_float(item.get("pnl"))
        if pnl >= 0:
            continue
        post = item.get("post_mortem") if isinstance(item.get("post_mortem"), dict) else {}
        recent_losses.append(
            {
                "symbol": str(item.get("symbol") or "").upper(),
                "side": _normalize_side(item.get("side") or ""),
                "pnl": round(pnl, 4),
                "exit_reason": str(item.get("exit_reason") or item.get("exit_class") or "")[:120],
                "lesson": str(post.get("rationale") or post.get("action_recommendation") or "")[:200],
            }
        )
    return {
        "symbol_lessons": dict(guidance.get("symbol_lessons") or {}),
        "blocked_symbols": sorted({str(s).upper() for s in (guidance.get("blocked_symbols") or []) if s}),
        "failure_focus": list(guidance.get("failure_focus_flags") or []),
        "recent_pure_ai_losses": recent_losses[:12],
        "learning_guard_mode": guidance.get("learning_guard_mode"),
    }


def filter_entries_by_learning(proposals: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not pure_ai_respect_learning():
        return list(proposals or [])
    blocked = {str(s).upper() for s in (context.get("blocked_symbols") or []) if s}
    symbol_lessons = dict(context.get("symbol_lessons") or {})
    loss_repeat: Dict[str, str] = {}
    for item in list(context.get("recent_pure_ai_losses") or []):
        if not isinstance(item, dict):
            continue
        sym = str(item.get("symbol") or "").upper()
        side = _normalize_side(item.get("side") or "")
        if sym and side:
            loss_repeat[sym] = side

    filtered: List[Dict[str, Any]] = []
    for row in list(proposals or []):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        side = _normalize_side(row.get("side") or "")
        if not symbol or not side:
            continue
        if symbol in blocked and not row.get("pyramid_add"):
            continue
        lesson = dict(symbol_lessons.get(symbol) or {})
        avoid_side = _normalize_side(lesson.get("avoid_side") or "")
        if avoid_side and side == avoid_side and not row.get("pyramid_add"):
            continue
        if loss_repeat.get(symbol) == side and not row.get("pyramid_add"):
            continue
        filtered.append(row)
    return filtered


def apply_entry_throttle(
    proposals: List[Dict[str, Any]],
    *,
    max_entries: Optional[int] = None,
    max_pyramid: Optional[int] = None,
) -> List[Dict[str, Any]]:
    max_entries = max(1, int(max_entries if max_entries is not None else PURE_AI_MAX_ENTRIES_PER_TICK))
    max_pyramid = max(0, int(max_pyramid if max_pyramid is not None else PURE_AI_MAX_PYRAMID_PER_TICK))
    new_rows: List[Dict[str, Any]] = []
    pyramid_rows: List[Dict[str, Any]] = []
    for row in list(proposals or []):
        if not isinstance(row, dict):
            continue
        if row.get("pyramid_add"):
            pyramid_rows.append(row)
        else:
            new_rows.append(row)

    out: List[Dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for row in new_rows:
        symbol = str(row.get("symbol") or "").upper()
        if not symbol or symbol in seen_symbols:
            continue
        if len(out) >= max_entries:
            break
        seen_symbols.add(symbol)
        out.append(row)

    pyramid_added = 0
    for row in pyramid_rows:
        if pyramid_added >= max_pyramid:
            break
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        if any(str(item.get("symbol") or "").upper() == symbol for item in out):
            continue
        out.append(row)
        pyramid_added += 1
    return out


def trend_confirms_position(position: Dict[str, Any], context: Dict[str, Any]) -> bool:
    position = dict(position or {})
    symbol = str(position.get("symbol") or "").upper()
    side = _normalize_side(position.get("side") or "")
    if not symbol or side not in {"BUY", "SELL"}:
        qty = _safe_float(position.get("signed_quantity") or position.get("quantity"))
        side = "BUY" if qty >= 0 else "SELL"

    entry = _safe_float(position.get("entry_price"))
    mark = _safe_float(position.get("mark_price") or entry)
    if entry > 0 and mark > 0:
        if side == "BUY" and mark >= entry * 1.0015:
            return True
        if side == "SELL" and mark <= entry * 0.9985:
            return True

    for _fleet, data in dict(context.get("core_fleets") or {}).items():
        if not isinstance(data, dict):
            continue
        if str(data.get("symbol") or "").upper() != symbol:
            continue
        signal = dict(data.get("signal") or {})
        action = _normalize_side(signal.get("action") or "")
        confidence = _safe_float(signal.get("confidence"))
        if action == side and confidence >= 0.18:
            return True

    fleet = str(position.get("fleet") or "RADAR").upper()
    market = dict((context.get("market_context") or {}).get(fleet) or {})
    bias = str(market.get("bias") or market.get("trend") or market.get("market_regime") or "").lower()
    if side == "BUY" and any(token in bias for token in ("bull", "up", "long", "risk_on", "trend_up")):
        return True
    if side == "SELL" and any(token in bias for token in ("bear", "down", "short", "risk_off", "trend_down")):
        return True
    return False


def filter_pyramid_candidates(
    proposals: List[Dict[str, Any]],
    context: Dict[str, Any],
    *,
    pyramid_last_at: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    if not proposals:
        return []
    positions_by_symbol = {
        str(item.get("symbol") or "").upper(): item
        for item in list(context.get("positions") or [])
        if isinstance(item, dict) and item.get("symbol")
    }
    last_at = dict(pyramid_last_at or context.get("pure_ai_pyramid_last_at") or {})
    cooldown = max(30, int(PURE_AI_PYRAMID_COOLDOWN_SECONDS))
    now = time.time()
    filtered: List[Dict[str, Any]] = []
    for row in proposals:
        if not row.get("pyramid_add"):
            filtered.append(row)
            continue
        symbol = str(row.get("symbol") or "").upper()
        position = positions_by_symbol.get(symbol)
        if not position:
            continue
        if not trend_confirms_position(position, context):
            continue
        if now - _safe_float(last_at.get(symbol)) < cooldown:
            continue
        filtered.append(row)
    return filtered
