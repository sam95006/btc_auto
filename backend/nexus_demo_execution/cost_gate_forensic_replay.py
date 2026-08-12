"""Replay Cost Gate over geometry-complete candidates without lowering floors."""
from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
from backend.nexus_demo_execution.session_limits import (
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
    TAKER_FEE_RATE_DEFAULT,
)

# Engine-fixed geometry used by BoundedAutonomousSessionEngine (must not silently change).
FIXED_SL_FRAC = 0.008
FIXED_TP_FRAC = 0.008


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, str) and v.strip().upper() in {"MISSING", "UNKNOWN", "UNAVAILABLE", "N/A"}:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return s[idx]


def _dist(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"count": 0, "status": "NOT_APPLICABLE"}
    return {
        "count": len(vals),
        "status": "AVAILABLE",
        "min": min(vals),
        "p25": _pct(vals, 25),
        "p50": _pct(vals, 50),
        "p75": _pct(vals, 75),
        "p95": _pct(vals, 95),
        "max": max(vals),
        "mean": statistics.fmean(vals),
    }


def reconstruct_candidate_geometry(row: dict[str, Any]) -> dict[str, Any]:
    """Build forensic fields from a cost_gate / candidate persistence row."""
    bd = row.get("breakdown") if isinstance(row.get("breakdown"), dict) else {}
    entry = _f(row.get("entry_price") or bd.get("entry_price"))
    stop = _f(row.get("stop_price") or row.get("stop_loss") or bd.get("stop_loss"))
    tp = _f(row.get("take_profit_price") or row.get("take_profit") or bd.get("take_profit"))
    side = str(row.get("side") or row.get("direction") or "Buy")
    qty = _f(row.get("qty") or bd.get("qty"))
    notional = _f(bd.get("notional"))
    if entry and entry > 0 and (stop is None or tp is None):
        # Reconstruct engine-fixed ±0.8% geometry when only entry known.
        if side.lower() == "buy":
            stop = stop if stop is not None else entry * (1.0 - FIXED_SL_FRAC)
            tp = tp if tp is not None else entry * (1.0 + FIXED_TP_FRAC)
        else:
            stop = stop if stop is not None else entry * (1.0 + FIXED_SL_FRAC)
            tp = tp if tp is not None else entry * (1.0 - FIXED_TP_FRAC)
    if qty is None and notional and entry and entry > 0:
        qty = notional / entry
    if qty is None:
        qty = 1.0  # unit analysis; ratios are scale-invariant for linear costs
    fee_rate = _f(bd.get("fee_rate") or row.get("fee_rate")) or TAKER_FEE_RATE_DEFAULT
    funding = _f(row.get("funding_rate") or bd.get("funding_rate"))
    slip_bps = _f(row.get("slippage_bps") or row.get("spread_bps") or bd.get("slippage_bps")) or 0.0

    gate = evaluate_cost_gate(
        entry_price=float(entry or 0.0),
        stop_loss=float(stop or 0.0),
        take_profit=float(tp or 0.0),
        qty=float(qty),
        side=side,
        fee_rate=fee_rate,
        funding_rate=funding,
        slippage_bps=float(slip_bps),
        fee_meta=row.get("fee_meta") if isinstance(row.get("fee_meta"), dict) else {},
    )
    gbd = gate.breakdown if isinstance(gate.breakdown, dict) else {}
    gross_reward = _f(gbd.get("gross_take_profit_pnl")) or 0.0
    gross_risk = _f(gbd.get("gross_stop_loss_pnl")) or 0.0
    total_cost = _f(gate.estimated_total_cost) if isinstance(gate.estimated_total_cost, (int, float)) else 0.0
    net_reward = _f(gate.estimated_net_reward) if isinstance(gate.estimated_net_reward, (int, float)) else 0.0
    net_risk = _f(gate.estimated_net_risk) if isinstance(gate.estimated_net_risk, (int, float)) else 0.0
    gross_rr = (gross_reward / gross_risk) if gross_risk > 0 else 0.0
    net_rr = float(gate.net_reward_risk_ratio) if isinstance(gate.net_reward_risk_ratio, (int, float)) else 0.0
    reward_to_cost = (net_reward / total_cost) if total_cost > 0 else 0.0
    expected_move = abs((tp or 0) - (entry or 0)) / entry if entry else 0.0
    labels = list(gate.labels or [])
    sub = "unknown"
    for key in ("net_reward_risk_ratio_low", "fee_churn_candidate", "gross_edge_insufficient"):
        if key in labels:
            sub = key
            break

    return {
        "symbol": row.get("symbol") or "UNKNOWN",
        "side": side,
        "regime": row.get("regime") or "UNKNOWN",
        "strategy": row.get("strategy") or "UNKNOWN",
        "entry_price": entry,
        "stop_price": stop,
        "take_profit_price": tp,
        "gross_reward": gross_reward,
        "gross_risk": gross_risk,
        "gross_rr": gross_rr,
        "estimated_entry_fee": gbd.get("estimated_entry_fee"),
        "estimated_exit_fee": gbd.get("estimated_exit_fee"),
        "spread_cost": None,  # engine passes spread via slippage_bps only
        "slippage_cost": gbd.get("estimated_slippage"),
        "funding_cost": gbd.get("estimated_funding"),
        "total_expected_cost": total_cost,
        "net_reward": net_reward,
        "net_risk": net_risk,
        "net_rr": net_rr,
        "reward_to_cost": reward_to_cost,
        "expected_move": expected_move,
        "exact_block_reason": gate.reason,
        "block_subreason": sub,
        "allowed": gate.allowed,
        "labels": labels,
        "floors": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
    }


def replay_cost_gates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reconstructed = [reconstruct_candidate_geometry(r) for r in rows]
    pass_n = sum(1 for r in reconstructed if r.get("allowed"))
    block_n = len(reconstructed) - pass_n
    sub_counts = Counter(str(r.get("block_subreason")) for r in reconstructed if not r.get("allowed"))
    reason_counts = Counter(str(r.get("exact_block_reason")) for r in reconstructed if not r.get("allowed"))

    gross_rrs = [float(r["gross_rr"]) for r in reconstructed]
    net_rrs = [float(r["net_rr"]) for r in reconstructed]
    rtc = [float(r["reward_to_cost"]) for r in reconstructed]
    moves = [float(r["expected_move"]) for r in reconstructed]
    costs = [float(r["total_expected_cost"]) for r in reconstructed]

    # Analytic root-cause for engine-fixed ±0.8% geometry:
    # gross_rr ≡ 1.0; with any positive cost, net_rr < 1.0 < MIN 1.2 ⇒ systematic zero pass.
    all_gross_near_one = bool(gross_rrs) and all(abs(g - 1.0) < 1e-6 for g in gross_rrs)
    max_net = max(net_rrs) if net_rrs else None
    causes: list[str] = []
    if pass_n == 0 and all_gross_near_one:
        causes.append("B")
        causes.append("F")
    if pass_n == 0 and max_net is not None and max_net < MIN_NET_REWARD_RISK_RATIO:
        causes.append("E")  # conservative costs + floors make ±0.8% impossible
    if pass_n == 0 and not causes:
        causes.append("A")
    # Double-count probe: spread_cost always None; slippage may include spread_bps once.
    double_count_suspect = any(r.get("spread_cost") is not None and r.get("slippage_cost") for r in reconstructed)
    if double_count_suspect:
        causes.append("C")
    unit_wrong = any(float(r["expected_move"]) > 0.5 for r in reconstructed)  # >50% move would be absurd
    if unit_wrong:
        causes.append("D")

    primary = causes[0] if causes else "G"
    letter_map = {
        "A": "Market conditions legitimately produced zero passes",
        "B": "Geometry systematically produced targets too close (fixed ±0.8% ⇒ gross_rr=1.0)",
        "C": "Fee/spread/slippage were double-counted",
        "D": "Unit or percentage conversion is wrong",
        "E": "Conservative fee/funding/uncertainty policy made all candidates impossible under floors",
        "F": "Cost Gate implementation is functioning as designed",
        "G": "Other evidence-backed cause",
    }

    return {
        "candidates_replayed": len(reconstructed),
        "cost_gate_pass_total": pass_n,
        "cost_gate_block_total": block_n,
        "block_reason_distribution": dict(reason_counts),
        "block_subreason_distribution": dict(sub_counts),
        "distributions": {
            "gross_rr": _dist(gross_rrs),
            "net_rr": _dist(net_rrs),
            "reward_to_cost": _dist(rtc),
            "expected_move": _dist(moves),
            "total_expected_cost": _dist(costs),
        },
        "floors_unchanged": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
        "root_cause_codes": sorted(set(causes)),
        "primary_root_cause": primary,
        "primary_root_cause_text": letter_map.get(primary, letter_map["G"]),
        "root_cause_detail": [letter_map[c] for c in sorted(set(causes)) if c in letter_map],
        "threshold_change_allowed": False,
        "required_before_any_threshold_change": [
            "Replay",
            "Walk-forward",
            "OOS",
            "Risk Review",
            "Shadow validation",
        ],
        "sample_rows": reconstructed[:5],
    }


def synthesize_fixed_geometry_rows(n: int, *, fee_rate: float = TAKER_FEE_RATE_DEFAULT, spread_bps: float = 2.0) -> list[dict[str, Any]]:
    """When live cost_gate rows cannot be exported, synthesize engine-equivalent rows for forensic proof."""
    rows = []
    entry = 100.0
    for i in range(max(0, n)):
        side = "Buy" if i % 2 == 0 else "Sell"
        rows.append(
            {
                "symbol": f"SYN{i % 50}USDT",
                "side": side,
                "regime": "SYNTH",
                "strategy": "FIXED_08PCT",
                "entry_price": entry,
                "qty": 5.0,
                "slippage_bps": spread_bps,
                "funding_rate": None,
                "breakdown": {"fee_rate": fee_rate, "notional": entry * 5.0},
            }
        )
    return rows
