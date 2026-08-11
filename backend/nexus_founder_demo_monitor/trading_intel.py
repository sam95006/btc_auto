"""V18.2.28 founder trading intelligence / performance / learning mappers."""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _dict_or_none(v: Any) -> dict[str, Any] | None:
    return dict(v) if isinstance(v, dict) and v else None


def _list_or_empty(v: Any) -> list[Any]:
    return list(v) if isinstance(v, list) else []


def empty_trading_intel() -> dict[str, Any]:
    return {
        "side": None,
        "position_state": "FLAT",
        "entry": None,
        "current": None,
        "stop_loss": None,
        "initial_target": None,
        "dynamic_profit_zone": None,
        "unrealized_pnl": None,
        "estimated_net_if_closed": None,
        "mfe": None,
        "mae": None,
        "mfe_capture_estimate": None,
        "remaining_net_edge": None,
        "continuation_score": None,
        "giveback_risk": None,
        "ai_thesis": None,
        "last_ai_position_review": None,
        "last_exit_reason": None,
    }


def empty_performance() -> dict[str, Any]:
    return {
        "win_rate_long": None,
        "win_rate_short": None,
        "win_rate_aggregate": None,
        "net_pnl": None,
        "profit_factor": None,
    }


def empty_learning() -> dict[str, Any]:
    return {
        "mistake_signatures": [],
        "pending_candidate_lessons": [],
    }


def _win_rate(wins: Any, total: Any) -> float | None:
    w = _num(wins)
    t = _num(total)
    if w is None or t is None or t <= 0:
        return None
    return w / t


def _extract_performance_block(raw: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("performance", "PERFORMANCE", "research_performance"):
        block = raw.get(key)
        if isinstance(block, dict) and block:
            return block

    for ck_key in ("CHECKPOINT_30", "CHECKPOINT_25"):
        ck = raw.get(ck_key)
        if isinstance(ck, dict):
            rp = ck.get("RESEARCH PERFORMANCE") or ck.get("RESEARCH_PERFORMANCE")
            if isinstance(rp, dict) and rp:
                return rp
    return None


def _extract_learning_block(raw: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("learning", "LEARNING", "LEARNING_MONITOR"):
        block = raw.get(key)
        if isinstance(block, dict) and block:
            return block
    return None


def _extract_trading_intel_block(raw: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("trading_intel", "TRADING_INTEL", "FOUNDER_MONITOR"):
        block = raw.get(key)
        if isinstance(block, dict) and block:
            return block
    return None


def map_trading_intel(
    raw: dict[str, Any],
    *,
    position: dict[str, Any],
    accounting: dict[str, Any],
    position_state: str,
) -> dict[str, Any]:
    out = empty_trading_intel()
    block = _extract_trading_intel_block(raw) or {}
    nested = block.get("trading_intel") if isinstance(block.get("trading_intel"), dict) else {}

    pos_item = raw.get("active_position")
    if not isinstance(pos_item, dict):
        pos_item = position if position.get("open") else {}

    side = _str_or_none(
        block.get("side")
        or nested.get("side")
        or pos_item.get("side")
        or raw.get("side")
    )
    out["side"] = side.upper() if side else None
    out["position_state"] = position_state

    out["entry"] = _num(
        block.get("entry")
        or nested.get("entry")
        or pos_item.get("entry")
        or pos_item.get("entry_price")
    )
    out["current"] = _num(
        block.get("current")
        or nested.get("current")
        or pos_item.get("current")
        or pos_item.get("mark_price")
    )
    out["stop_loss"] = _num(
        block.get("stop_loss")
        or block.get("stop")
        or nested.get("stop_loss")
        or pos_item.get("stop")
        or pos_item.get("stop_loss")
        or pos_item.get("sl")
    )
    out["initial_target"] = _num(
        block.get("initial_target")
        or nested.get("initial_target")
        or pos_item.get("initial_target")
        or pos_item.get("target")
        or pos_item.get("tp")
    )
    dpz = (
        block.get("dynamic_profit_zone")
        or nested.get("dynamic_profit_zone")
        or pos_item.get("dynamic_profit_zone")
    )
    out["dynamic_profit_zone"] = _dict_or_none(dpz)

    out["unrealized_pnl"] = _num(
        block.get("unrealized_pnl")
        or nested.get("unrealized_pnl")
        or pos_item.get("unrealized_pnl")
        or position.get("unrealized_pnl")
    )
    out["estimated_net_if_closed"] = _num(
        block.get("estimated_net_if_closed")
        or nested.get("estimated_net_if_closed")
        or pos_item.get("estimated_net_if_closed")
        or position.get("estimated_net_if_closed")
    )

    out["mfe"] = _num(
        block.get("mfe")
        or block.get("MFE_usdt")
        or block.get("MFE")
        or nested.get("mfe")
        or pos_item.get("mfe")
        or raw.get("mfe")
    )
    out["mae"] = _num(
        block.get("mae")
        or block.get("MAE_usdt")
        or block.get("MAE")
        or nested.get("mae")
        or pos_item.get("mae")
        or raw.get("mae")
    )
    out["mfe_capture_estimate"] = _num(
        block.get("mfe_capture_estimate")
        or nested.get("mfe_capture_estimate")
        or block.get("exit_efficiency")
    )
    out["remaining_net_edge"] = _num(
        block.get("remaining_net_edge") or nested.get("remaining_net_edge")
    )
    out["continuation_score"] = _num(
        block.get("continuation_score") or nested.get("continuation_score")
    )
    out["giveback_risk"] = _num(block.get("giveback_risk") or nested.get("giveback_risk"))

    ai_thesis = block.get("ai_thesis") or nested.get("ai_thesis") or raw.get("ai_thesis")
    if ai_thesis is None:
        thesis = raw.get("thesis")
        if isinstance(thesis, dict) and thesis:
            ai_thesis = thesis
        elif isinstance(block.get("horizon"), dict):
            ai_thesis = block.get("horizon")
    out["ai_thesis"] = ai_thesis if isinstance(ai_thesis, (dict, str)) else None

    review = block.get("last_ai_position_review") or nested.get("last_ai_position_review")
    out["last_ai_position_review"] = review if isinstance(review, (dict, str)) else None

    out["last_exit_reason"] = _str_or_none(
        block.get("last_exit_reason")
        or block.get("exit_reason")
        or nested.get("last_exit_reason")
        or accounting.get("last_exit_reason")
    )
    return out


def map_performance(raw: dict[str, Any]) -> dict[str, Any]:
    out = empty_performance()
    block = _extract_performance_block(raw) or {}
    cumulative = block.get("cumulative") if isinstance(block.get("cumulative"), dict) else {}

    out["win_rate_long"] = _num(block.get("win_rate_long") or cumulative.get("win_rate_long"))
    out["win_rate_short"] = _num(block.get("win_rate_short") or cumulative.get("win_rate_short"))

    agg = block.get("win_rate_aggregate") or block.get("win_rate") or cumulative.get("win_rate")
    if agg is None:
        wins = cumulative.get("wins")
        n = cumulative.get("n")
        agg = _win_rate(wins, n)
    out["win_rate_aggregate"] = _num(agg)

    out["net_pnl"] = _num(
        block.get("net_pnl") or cumulative.get("net_pnl") or block.get("session_net_pnl")
    )
    out["profit_factor"] = _num(
        block.get("profit_factor") or cumulative.get("profit_factor")
    )
    return out


def map_learning(raw: dict[str, Any]) -> dict[str, Any]:
    out = empty_learning()
    block = _extract_learning_block(raw) or {}

    sigs = block.get("mistake_signatures")
    if sigs is None:
        sigs = raw.get("mistake_signatures")
    out["mistake_signatures"] = _list_or_empty(sigs)

    lessons = block.get("pending_candidate_lessons")
    if lessons is None:
        lessons = block.get("candidate_lessons") or raw.get("pending_candidate_lessons")
    out["pending_candidate_lessons"] = _list_or_empty(lessons)
    return out
