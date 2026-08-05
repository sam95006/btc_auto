"""Offline Structural Geometry qualification — never auto-arms live execution policy.

Stages: REPLAY_VALIDATED → WALK_FORWARD_VALIDATED → OOS_VALIDATED → RISK_REVIEWED → SHADOW_APPLIED
Fixed ±0.8% geometry is retired from future autonomous *qualification* (diagnostic baseline only).
Floors stay: MIN_NET_REWARD_RISK_RATIO=1.2, MIN_NET_REWARD_TO_COST=1.5.
"""
from __future__ import annotations

import hashlib
import statistics
from collections import Counter
from typing import Any

from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
from backend.nexus_demo_execution.geometry_contracts import CandidateEvidence
from backend.nexus_demo_execution.session_limits import (
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
    TAKER_FEE_RATE_DEFAULT,
)
from backend.nexus_demo_execution.trade_geometry import compute_structure_geometry

FIXED_SL_FRAC = 0.008
FIXED_TP_FRAC = 0.008
STAGES = (
    "REPLAY_VALIDATED",
    "WALK_FORWARD_VALIDATED",
    "OOS_VALIDATED",
    "RISK_REVIEWED",
    "SHADOW_APPLIED",
)

# Re-export shared contract for existing callers.
__all__ = [
    "CandidateEvidence",
    "FIXED_SL_FRAC",
    "FIXED_TP_FRAC",
    "STAGES",
    "evaluate_fixed_geometry",
    "evaluate_structural_geometry",
    "compare_ab",
    "synthesize_structure_candidates",
    "stage_metrics",
]


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _hash_id(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def evaluate_fixed_geometry(c: CandidateEvidence) -> dict[str, Any]:
    entry = float(c.entry_price)
    side = c.side
    if side.lower() in {"buy", "long"}:
        stop, tp = entry * (1 - FIXED_SL_FRAC), entry * (1 + FIXED_TP_FRAC)
    else:
        stop, tp = entry * (1 + FIXED_SL_FRAC), entry * (1 - FIXED_TP_FRAC)
    qty = float(c.qty or 1.0)
    fee = c.fee_rate if c.fee_rate is not None else TAKER_FEE_RATE_DEFAULT
    gate = evaluate_cost_gate(
        entry_price=entry,
        stop_loss=stop,
        take_profit=tp,
        qty=qty,
        side=side,
        fee_rate=fee,
        funding_rate=c.funding_rate,
        slippage_bps=float(c.slippage_bps or c.spread_bps or 0.0),
    )
    bd = gate.breakdown if isinstance(gate.breakdown, dict) else {}
    gross_r = _f(bd.get("gross_take_profit_pnl")) or 0.0
    gross_k = _f(bd.get("gross_stop_loss_pnl")) or 0.0
    return {
        "geometry_source": "FIXED_08PCT",
        "geometry_complete": True,
        "geometry_missing": False,
        "geometry_invalid": False,
        "entry_price": entry,
        "stop_price": stop,
        "take_profit_price": tp,
        "gross_reward": gross_r,
        "gross_risk": gross_k,
        "gross_rr": (gross_r / gross_k) if gross_k > 0 else 0.0,
        "cost_gate_pass": bool(gate.allowed),
        "cost_gate_block": not bool(gate.allowed),
        "block_reason": gate.reason,
        "block_subreason": (gate.labels[-1] if gate.labels else ""),
        "net_rr": gate.net_reward_risk_ratio if isinstance(gate.net_reward_risk_ratio, (int, float)) else None,
        "reward_to_cost": (
            (float(gate.estimated_net_reward) / float(gate.estimated_total_cost))
            if isinstance(gate.estimated_net_reward, (int, float))
            and isinstance(gate.estimated_total_cost, (int, float))
            and float(gate.estimated_total_cost) > 0
            else None
        ),
        "breakdown": bd,
    }


def evaluate_structural_geometry(c: CandidateEvidence) -> dict[str, Any]:
    if c.data_freshness_sec is not None and c.data_freshness_sec > c.max_freshness_sec:
        return {
            "geometry_source": "STRUCTURE",
            "geometry_complete": False,
            "geometry_missing": False,
            "geometry_invalid": True,
            "block_reason": "GEOMETRY_STALE",
            "block_subreason": "data_freshness_exceeded",
            "cost_gate_pass": False,
            "cost_gate_block": True,
            "gross_rr": None,
            "net_rr": None,
            "reward_to_cost": None,
        }
    fee = c.fee_rate
    geo = compute_structure_geometry(
        side=c.side,
        entry_price=float(c.entry_price),
        atr=c.atr,
        recent_swing_high=c.recent_swing_high,
        recent_swing_low=c.recent_swing_low,
        support=c.support,
        resistance=c.resistance,
        liquidity_levels=list(c.liquidity_levels or []),
        spread_bps=float(c.spread_bps or 0.0),
        slippage_bps=float(c.slippage_bps or 0.0),
        fee_rate=fee,
        funding_rate=c.funding_rate,
        tick_size=c.tick_size,
        qty=c.qty,
    )
    missing = bool(geo.inputs_missing) or geo.block_reason == "GEOMETRY_INPUT_MISSING"
    invalid = (not geo.allowed) and geo.block_reason in {
        "BLOCK_INVALID_TRADE_GEOMETRY",
        "GEOMETRY_STALE",
        "FEE_RATE_UNKNOWN",
    }
    complete = (not missing) and geo.stop_loss not in ("UNAVAILABLE", None) and geo.take_profit not in (
        "UNAVAILABLE",
        None,
    )
    # Re-run cost gate on structural SL/TP for apples-to-apples block reasons.
    cost_pass = False
    cost_block = True
    reason = geo.block_reason
    sub = ",".join(geo.labels)
    net_rr = geo.net_rr if isinstance(geo.net_rr, (int, float)) else None
    rtc = None
    if complete and isinstance(geo.stop_loss, (int, float)) and isinstance(geo.take_profit, (int, float)):
        gate = evaluate_cost_gate(
            entry_price=float(c.entry_price),
            stop_loss=float(geo.stop_loss),
            take_profit=float(geo.take_profit),
            qty=float(c.qty or 1.0),
            side=c.side,
            fee_rate=fee if fee is not None else TAKER_FEE_RATE_DEFAULT,
            funding_rate=c.funding_rate,
            slippage_bps=float(c.slippage_bps or c.spread_bps or 0.0),
        )
        cost_pass = bool(gate.allowed)
        cost_block = not cost_pass
        reason = gate.reason if not cost_pass else "COST_GATE_PASS"
        sub = ",".join(gate.labels)
        if isinstance(gate.net_reward_risk_ratio, (int, float)):
            net_rr = float(gate.net_reward_risk_ratio)
        if (
            isinstance(gate.estimated_net_reward, (int, float))
            and isinstance(gate.estimated_total_cost, (int, float))
            and float(gate.estimated_total_cost) > 0
        ):
            rtc = float(gate.estimated_net_reward) / float(gate.estimated_total_cost)
    return {
        "geometry_source": "STRUCTURE",
        "geometry_complete": complete,
        "geometry_missing": missing,
        "geometry_invalid": invalid and not missing,
        "entry_price": c.entry_price,
        "stop_price": geo.stop_loss,
        "take_profit_price": geo.take_profit,
        "gross_reward": geo.gross_reward,
        "gross_risk": geo.gross_risk,
        "gross_rr": geo.gross_rr,
        "cost_gate_pass": cost_pass,
        "cost_gate_block": cost_block,
        "block_reason": reason,
        "block_subreason": sub,
        "net_rr": net_rr,
        "reward_to_cost": rtc,
        "invalidation_reason": geo.invalidation_reason,
        "target_reason": geo.target_reason,
        "inputs_missing": list(geo.inputs_missing or []),
        "floors": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
    }


def compare_ab(candidates: list[CandidateEvidence]) -> dict[str, Any]:
    rows = []
    for c in candidates:
        fixed = evaluate_fixed_geometry(c)
        structural = evaluate_structural_geometry(c)
        rows.append(
            {
                "symbol": c.symbol,
                "side": c.side,
                "regime": c.regime,
                "strategy": c.strategy,
                "candidate_id_hash": _hash_id(f"{c.symbol}|{c.side}|{c.entry_price}|{c.ts}"),
                "fixed": fixed,
                "structural": structural,
            }
        )
    fixed_pass = sum(1 for r in rows if r["fixed"].get("cost_gate_pass"))
    struct_pass = sum(1 for r in rows if r["structural"].get("cost_gate_pass"))
    n = len(rows) or 1
    return {
        "diagnostic_only": True,
        "oos_claim_forbidden": True,
        "candidates": n if rows else 0,
        "fixed_geometry_pass_rate": fixed_pass / n if rows else 0.0,
        "structural_geometry_pass_rate": struct_pass / n if rows else 0.0,
        "fixed_pass_count": fixed_pass,
        "structural_pass_count": struct_pass,
        "structural_geometry_complete": sum(1 for r in rows if r["structural"].get("geometry_complete")),
        "structural_geometry_missing": sum(1 for r in rows if r["structural"].get("geometry_missing")),
        "structural_geometry_invalid": sum(1 for r in rows if r["structural"].get("geometry_invalid")),
        "block_reason_fixed": dict(Counter(str(r["fixed"].get("block_reason")) for r in rows)),
        "block_reason_structural": dict(Counter(str(r["structural"].get("block_reason")) for r in rows)),
        "floors_unchanged": {
            "MIN_NET_REWARD_RISK_RATIO": MIN_NET_REWARD_RISK_RATIO,
            "MIN_NET_REWARD_TO_COST": MIN_NET_REWARD_TO_COST,
        },
        "sample": rows[:3],
        "rows": rows,
    }


def synthesize_structure_candidates(n: int = 2407) -> list[CandidateEvidence]:
    """Synthetic evidence set for offline framework tests — not used to claim OOS success.

    Mixes complete / missing / stale / tight-structure cases so pass rate is not artificial 100%.
    """
    out: list[CandidateEvidence] = []
    for i in range(n):
        entry = 100.0 + (i % 50) * 0.1
        side = "Buy" if i % 2 == 0 else "Sell"
        atr = 1.2 + (i % 7) * 0.05
        mode = i % 5  # 0-1 complete wide, 2 tight, 3 missing, 4 stale
        base = dict(
            symbol=f"SYN{i % 40}USDT",
            side=side,
            entry_price=entry,
            regime=("TREND_UP" if side == "Buy" else "TREND_DOWN") if i % 3 else "RANGE",
            strategy="STRUCT_SWING",
            spread_bps=2.0,
            slippage_bps=2.0,
            fee_rate=TAKER_FEE_RATE_DEFAULT,
            funding_rate=None,
            tick_size=0.01,
            qty=5.0,
            ts=float(i),
        )
        if mode == 3:
            out.append(CandidateEvidence(**base, atr=None, data_freshness_sec=30.0))
            continue
        if mode == 4:
            out.append(
                CandidateEvidence(
                    **base,
                    atr=atr,
                    recent_swing_high=entry + 2.0 * atr,
                    recent_swing_low=entry - 1.2 * atr,
                    support=entry - 1.1 * atr,
                    resistance=entry + 1.8 * atr,
                    data_freshness_sec=9999.0,
                    max_freshness_sec=300.0,
                )
            )
            continue
        # Tight structure: target barely beyond stop → often cost-blocked.
        if mode == 2:
            if side == "Buy":
                out.append(
                    CandidateEvidence(
                        **base,
                        atr=atr,
                        recent_swing_high=entry + 0.4 * atr,
                        recent_swing_low=entry - 0.35 * atr,
                        support=entry - 0.3 * atr,
                        resistance=entry + 0.35 * atr,
                        data_freshness_sec=30.0,
                    )
                )
            else:
                out.append(
                    CandidateEvidence(
                        **base,
                        atr=atr,
                        recent_swing_high=entry + 0.35 * atr,
                        recent_swing_low=entry - 0.4 * atr,
                        support=entry - 0.35 * atr,
                        resistance=entry + 0.3 * atr,
                        data_freshness_sec=30.0,
                    )
                )
            continue
        # Complete wide structure
        if side == "Buy":
            out.append(
                CandidateEvidence(
                    **base,
                    atr=atr,
                    recent_swing_high=entry + 2.5 * atr,
                    recent_swing_low=entry - 1.2 * atr,
                    support=entry - 1.1 * atr,
                    resistance=entry + 2.0 * atr,
                    liquidity_levels=[entry + 2.2 * atr],
                    data_freshness_sec=30.0,
                )
            )
        else:
            out.append(
                CandidateEvidence(
                    **base,
                    atr=atr,
                    recent_swing_high=entry + 1.2 * atr,
                    recent_swing_low=entry - 2.5 * atr,
                    support=entry - 2.0 * atr,
                    resistance=entry + 1.1 * atr,
                    liquidity_levels=[entry - 2.2 * atr],
                    data_freshness_sec=30.0,
                )
            )
    return out


def stage_metrics(name: str, rows: list[dict[str, Any]], *, time_range: str) -> dict[str, Any]:
    """Diagnostic Cost Gate metrics only — never claim trade performance here."""
    struct = [r["structural"] for r in rows]
    net_rrs = [float(s["net_rr"]) for s in struct if isinstance(s.get("net_rr"), (int, float))]
    rtcs = [float(s["reward_to_cost"]) for s in struct if isinstance(s.get("reward_to_cost"), (int, float))]
    pass_n = sum(1 for s in struct if s.get("cost_gate_pass"))
    complete_n = sum(1 for s in struct if s.get("geometry_complete"))
    n = len(rows) or 1
    # Honest: Cost Gate framework ≠ performance validation.
    framework_status = "COST_GATE_FRAMEWORK_VALIDATED" if rows else "EMPTY"
    if name.startswith("OOS"):
        framework_status = "OOS_FRAMEWORK_VALIDATED" if rows else "EMPTY"
    elif name.startswith("WALK_FORWARD"):
        framework_status = "WALK_FORWARD_FRAMEWORK_VALIDATED" if rows else "EMPTY"
    return {
        "stage": name,
        "time_range": time_range,
        "candidate_count": len(rows),
        "geometry_complete_rate": complete_n / n if rows else 0.0,
        "cost_gate_pass_rate": pass_n / n if rows else 0.0,
        "diagnostic_only": True,
        "cost_gate_pass_is_not_a_trade": True,
        "expected_net_rr": {
            "mean": statistics.fmean(net_rrs) if net_rrs else None,
            "p50": sorted(net_rrs)[len(net_rrs) // 2] if net_rrs else None,
        },
        "reward_to_cost": {
            "mean": statistics.fmean(rtcs) if rtcs else None,
            "p50": sorted(rtcs)[len(rtcs) // 2] if rtcs else None,
        },
        # Filled only by event-driven sim merge — default null/zero.
        "trade_simulation_count": 0,
        "gross_pnl": None,
        "fees": None,
        "slippage": None,
        "funding": None,
        "net_pnl": None,
        "profit_factor": None,
        "maximum_drawdown": None,
        "win_rate": None,
        "expectancy": None,
        "calibration": "NOT_APPLICABLE_NO_FILLS",
        "look_ahead_contamination": False,
        "status": framework_status,
    }
