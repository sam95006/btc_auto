"""Cost gate diagnosis helpers — analysis only, never mutates runtime."""
from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any


def _num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def diagnose_blocked_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Build cost-gate diagnosis from candidate records (export or live snapshot)."""
    rows: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    gross_rewards: list[float] = []
    total_costs: list[float] = []
    net_rewards: list[float] = []
    fee_dominated = 0
    slip_dominated = 0
    funding_unknown = 0
    net_rr_below = 0

    for c in candidates:
        reason = str(c.get("block_reason") or c.get("gate") or c.get("verdict") or "UNKNOWN")
        reasons[reason] += 1
        gross = _num(c.get("estimated_gross_reward") or c.get("gross_reward"))
        fee = _num(c.get("estimated_total_fee") or c.get("total_fee"))
        slip = _num(c.get("estimated_slippage") or c.get("slippage"))
        fund = c.get("funding")
        fund_n = _num(fund)
        if fund is None or str(fund).upper() in {"UNAVAILABLE", "UNKNOWN", "N/A", ""}:
            funding_unknown += 1
            fund_out: float | str = "UNAVAILABLE"
        else:
            fund_out = fund_n if fund_n is not None else "UNAVAILABLE"
            if fund_out == "UNAVAILABLE":
                funding_unknown += 1
        buffer = _num(c.get("cost_uncertainty_buffer") or c.get("funding_buffer")) or 0.0
        cost = None
        if fee is not None or slip is not None:
            cost = (fee or 0.0) + (slip or 0.0) + buffer
            if isinstance(fund_out, float):
                cost += abs(fund_out)
        net = None
        if gross is not None and cost is not None:
            net = gross - cost
        risk = _num(c.get("estimated_gross_risk") or c.get("gross_risk"))
        rr = None
        if net is not None and risk and risk > 0:
            rr = net / risk
            threshold = _num(c.get("net_reward_risk_threshold")) or 0.0
            if rr < threshold:
                net_rr_below += 1
        if gross is not None:
            gross_rewards.append(gross)
        if cost is not None:
            total_costs.append(cost)
            if fee is not None and fee >= (cost * 0.5):
                fee_dominated += 1
            if slip is not None and slip >= (cost * 0.5):
                slip_dominated += 1
        if net is not None:
            net_rewards.append(net)

        rows.append(
            {
                "symbol": c.get("symbol"),
                "direction": c.get("direction") or c.get("side"),
                "strategy": c.get("strategy"),
                "entry_price": c.get("entry_price"),
                "target_price": c.get("target_price"),
                "stop_price": c.get("stop_price"),
                "estimated_gross_reward": gross if gross is not None else "UNAVAILABLE",
                "estimated_gross_risk": risk if risk is not None else "UNAVAILABLE",
                "entry_fee": c.get("entry_fee", "UNAVAILABLE"),
                "exit_fee": c.get("exit_fee", "UNAVAILABLE"),
                "estimated_total_fee": fee if fee is not None else "UNAVAILABLE",
                "estimated_slippage": slip if slip is not None else "UNAVAILABLE",
                "funding": fund_out,
                "funding_buffer": c.get("funding_buffer", "UNAVAILABLE"),
                "cost_uncertainty_buffer": buffer,
                "estimated_net_reward": net if net is not None else "UNAVAILABLE",
                "net_reward_risk_ratio": rr if rr is not None else "UNAVAILABLE",
                "block_reason": reason,
                "data_quality": c.get("data_quality") or c.get("quality") or "UNKNOWN",
            }
        )

    def _med(vals: list[float]) -> float | str:
        return float(median(vals)) if vals else "UNAVAILABLE"

    ratios = []
    for g, c in zip(gross_rewards, total_costs):
        if g and g > 0:
            ratios.append(c / g)

    return {
        "candidates_analyzed": len(candidates),
        "blocked_rows": rows,
        "block_reason_distribution": dict(reasons),
        "median_gross_reward": _med(gross_rewards),
        "median_total_cost": _med(total_costs),
        "median_net_reward": _med(net_rewards),
        "cost_to_gross_reward_ratio": _med(ratios),
        "fee_dominated_count": fee_dominated,
        "slippage_dominated_count": slip_dominated,
        "funding_unknown_count": funding_unknown,
        "net_rr_below_threshold_count": net_rr_below,
        "note": "Diagnosis only — do not mutate live session gates",
        "session_modification_forbidden": True,
    }


def why_no_trade_message(*, candidates_total: int, cost_gate_blocks: int, entries: int) -> dict[str, Any]:
    if entries > 0:
        return {
            "active": False,
            "headline": None,
            "detail": None,
        }
    if candidates_total > 0 and cost_gate_blocks >= candidates_total:
        return {
            "active": True,
            "headline": "NO_TRADE_COST_GATE",
            "detail": (
                f"目前沒有交易，因全部 {candidates_total} 個候選在扣除 Fee／Slippage／Funding Buffer 後，"
                "預估淨報酬未達安全標準。系統仍在掃描；這不是停機。"
            ),
            "gate_breakdown": {
                "candidates_total": candidates_total,
                "cost_gate_blocks": cost_gate_blocks,
            },
        }
    if candidates_total == 0:
        return {
            "active": True,
            "headline": "NO_TRADE_NO_CANDIDATES",
            "detail": "目前沒有交易，因尚未產生有效候選。系統可能仍在掃描。",
        }
    return {
        "active": True,
        "headline": "NO_TRADE_GATED",
        "detail": "目前沒有交易；請檢視 Gate Breakdown。系統並未停止運作。",
        "gate_breakdown": {
            "candidates_total": candidates_total,
            "cost_gate_blocks": cost_gate_blocks,
        },
    }
