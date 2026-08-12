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
        # V29 — direction + stop/entry + adaptive profit capture telemetry (null when missing).
        "direction_score_delta": None,
        "direction_ambiguity_supported": None,
        "last_entry_class": None,
        "stop_distance_pct": None,
        "fee_to_stop_loss_ratio": None,
        "profit_lock_state": None,
        "profit_lock_level": None,
        "protected_pnl_floor": None,
        "profit_lock_started_at": None,
        "adaptive_action": None,
    }


def empty_performance() -> dict[str, Any]:
    return {
        "win_rate_long": None,
        "win_rate_short": None,
        "win_rate_aggregate": None,
        "net_pnl": None,
        "profit_factor": None,
        "expectancy": None,
        "average_win": None,
        "average_loss": None,
        "max_drawdown": None,
        "sample_status": None,
        "accounting_complete_trades": None,
        "average_MFE_capture": None,
        "last_10": None,
        "last_30": None,
    }


def empty_learning() -> dict[str, Any]:
    return {
        "mistake_signatures": [],
        "pending_candidate_lessons": [],
        "lesson_pipeline": None,
        "repeat_after_validated_lesson": None,
    }


def empty_autonomy() -> dict[str, Any]:
    return {
        "service_status": None,
        "last_cycle": None,
        "next_cycle": None,
        "cycles_24h": None,
        "errors_24h": None,
        "open_position": None,
        "exchange_connectivity": None,
        "market_data_health": None,
        "runtime_location": None,
        "worker_instance_id": None,
        "waiting_market_valid": None,
        "top_rejection_reasons": None,
    }


def empty_ai_health() -> dict[str, Any]:
    return {
        "provider": None,
        "model": None,
        "configured": None,
        "credential_present": None,
        "ai_state": None,
        "last_request": None,
        "last_success": None,
        "requests_24h": None,
        "successes_24h": None,
        "rate_limits_24h": None,
        "quota_errors_24h": None,
        "auth_errors_24h": None,
        "timeouts_24h": None,
        "last_error": None,
        "quota_exhausted": None,
        "rate_limited": None,
        "ai_calls_working": None,
        "ai_required_for_v30_entry": None,
        "fallback_used": None,
    }


def map_autonomy(raw: dict[str, Any]) -> dict[str, Any]:
    out = empty_autonomy()
    block = raw.get("autonomy") if isinstance(raw.get("autonomy"), dict) else {}
    nested = raw.get("AUTONOMY SERVICE") if isinstance(raw.get("AUTONOMY SERVICE"), dict) else {}
    src = block or nested
    health = src.get("health") if isinstance(src.get("health"), dict) else {}
    out["service_status"] = _str_or_none(src.get("service_status") or health.get("service_status"))
    out["last_cycle"] = _str_or_none(src.get("last_cycle") or health.get("last_cycle_completed_at"))
    out["next_cycle"] = _str_or_none(src.get("next_cycle") or health.get("next_cycle_due_at"))
    out["cycles_24h"] = _num(src.get("cycles_24h") if src.get("cycles_24h") is not None else health.get("cycles_24h"))
    out["errors_24h"] = _num(src.get("errors_24h") if src.get("errors_24h") is not None else health.get("errors_24h"))
    op = src.get("open_position") if src.get("open_position") is not None else health.get("open_position")
    out["open_position"] = bool(op) if op is not None else None
    out["exchange_connectivity"] = _str_or_none(
        src.get("exchange_connectivity") or health.get("exchange_connectivity")
    )
    out["market_data_health"] = _str_or_none(src.get("market_data_health") or health.get("market_data_health"))
    out["runtime_location"] = _str_or_none(
        src.get("runtime_location") or health.get("runtime_location") or raw.get("runtime_location")
    )
    out["worker_instance_id"] = _str_or_none(src.get("worker_instance_id") or health.get("worker_instance_id"))
    wmv = src.get("waiting_market_valid")
    if wmv is None:
        wmv = health.get("waiting_market_valid")
    out["waiting_market_valid"] = bool(wmv) if wmv is not None else None
    reasons = src.get("top_rejection_reasons") or health.get("top_rejection_reasons")
    out["top_rejection_reasons"] = list(reasons) if isinstance(reasons, list) else None
    return out


def map_ai_health(raw: dict[str, Any]) -> dict[str, Any]:
    out = empty_ai_health()
    block = raw.get("ai_health") if isinstance(raw.get("ai_health"), dict) else {}
    nested = raw.get("AI HEALTH") if isinstance(raw.get("AI HEALTH"), dict) else {}
    src = block or nested
    if not src and isinstance(raw.get("autonomy"), dict):
        src = raw["autonomy"].get("ai") if isinstance(raw["autonomy"].get("ai"), dict) else {}
    out["provider"] = _str_or_none(src.get("provider"))
    out["model"] = _str_or_none(src.get("model"))
    out["configured"] = src.get("configured") if src.get("configured") is not None else None
    out["credential_present"] = (
        src.get("credential_present") if src.get("credential_present") is not None else None
    )
    out["ai_state"] = _str_or_none(src.get("ai_state"))
    out["last_request"] = _str_or_none(src.get("last_request") or src.get("last_request_at"))
    out["last_success"] = _str_or_none(
        src.get("last_success") or src.get("last_success_at") or src.get("last_successful_ai_call")
    )
    for k in (
        "requests_24h",
        "successes_24h",
        "rate_limits_24h",
        "quota_errors_24h",
        "auth_errors_24h",
        "timeouts_24h",
    ):
        out[k] = _num(src.get(k))
    out["last_error"] = _str_or_none(src.get("last_error") or src.get("last_error_code"))
    qe = src.get("quota_exhausted")
    out["quota_exhausted"] = qe if qe in (True, False, "UNKNOWN") else (bool(qe) if qe is not None else None)
    out["rate_limited"] = bool(src.get("rate_limited")) if src.get("rate_limited") is not None else None
    out["ai_calls_working"] = (
        bool(src.get("ai_calls_working")) if src.get("ai_calls_working") is not None else None
    )
    out["ai_required_for_v30_entry"] = (
        bool(src.get("ai_required_for_v30_entry"))
        if src.get("ai_required_for_v30_entry") is not None
        else None
    )
    out["fallback_used"] = bool(src.get("fallback_used")) if src.get("fallback_used") is not None else None
    return out


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

    # V29 best-effort fields (may be absent on older feeds).
    out["direction_score_delta"] = _num(nested.get("direction_score_delta") or block.get("direction_score_delta"))
    out["direction_ambiguity_supported"] = nested.get("direction_ambiguity_supported") or block.get(
        "direction_ambiguity_supported"
    )
    out["last_entry_class"] = _str_or_none(nested.get("last_entry_class") or block.get("last_entry_class"))
    out["stop_distance_pct"] = _num(nested.get("stop_distance_pct") or block.get("stop_distance_pct"))
    out["fee_to_stop_loss_ratio"] = _num(nested.get("fee_to_stop_loss_ratio") or block.get("fee_to_stop_loss_ratio"))

    out["profit_lock_state"] = nested.get("profit_lock_state") or block.get("profit_lock_state")
    out["profit_lock_level"] = _num(nested.get("profit_lock_level") or block.get("profit_lock_level"))
    out["protected_pnl_floor"] = _num(nested.get("protected_pnl_floor") or block.get("protected_pnl_floor"))
    out["profit_lock_started_at"] = _num(nested.get("profit_lock_started_at") or block.get("profit_lock_started_at"))
    out["adaptive_action"] = _str_or_none(nested.get("adaptive_action") or block.get("adaptive_action"))
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

    if isinstance(block.get("last_10"), dict):
        out["last_10"] = block.get("last_10")
    if isinstance(block.get("last_30"), dict):
        out["last_30"] = block.get("last_30")
    out["expectancy"] = _num(block.get("expectancy"))
    out["average_win"] = _num(block.get("average_win"))
    out["average_loss"] = _num(block.get("average_loss"))
    out["max_drawdown"] = _num(block.get("max_drawdown") or block.get("max_drawdown_usdt"))
    out["sample_status"] = _str_or_none(block.get("sample_status") or block.get("win_rate_claim_status"))
    out["accounting_complete_trades"] = _num(
        block.get("accounting_complete_trades") or block.get("n")
    )
    out["average_MFE_capture"] = _num(block.get("average_MFE_capture"))
    if out["average_MFE_capture"] is None and isinstance(block.get("last_10"), dict):
        out["average_MFE_capture"] = _num(block["last_10"].get("avg_mfe_capture_ratio"))
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
    pipeline = block.get("lesson_pipeline")
    if isinstance(pipeline, dict):
        out["lesson_pipeline"] = pipeline
    out["repeat_after_validated_lesson"] = _num(block.get("repeat_after_validated_lesson"))
    return out
