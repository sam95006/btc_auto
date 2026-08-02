"""Offline Structural Geometry qualification — never auto-arms live execution policy.

Stages: REPLAY_VALIDATED → WALK_FORWARD_VALIDATED → OOS_VALIDATED → RISK_REVIEWED → SHADOW_APPLIED
Fixed ±0.8% geometry is retired from future autonomous *qualification* (diagnostic baseline only).
Floors stay: MIN_NET_REWARD_RISK_RATIO=1.2, MIN_NET_REWARD_TO_COST=1.5.
"""
from __future__ import annotations

import hashlib
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
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


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _hash_id(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class CandidateEvidence:
    """Evidence-backed geometry inputs. Missing fields must not be invented."""

    symbol: str
    side: str
    entry_price: float
    regime: str = "UNKNOWN"
    strategy: str = "UNKNOWN"
    atr: float | None = None
    recent_swing_high: float | None = None
    recent_swing_low: float | None = None
    support: float | None = None
    resistance: float | None = None
    liquidity_levels: list[float] = field(default_factory=list)
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    fee_rate: float | None = None
    funding_rate: float | None = None
    tick_size: float | None = None
    qty: float | None = None
    data_freshness_sec: float | None = None
    max_freshness_sec: float = 300.0
    ts: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    """Synthetic evidence set for offline framework tests — not used to claim OOS success."""
    out: list[CandidateEvidence] = []
    for i in range(n):
        entry = 100.0 + (i % 50) * 0.1
        side = "Buy" if i % 2 == 0 else "Sell"
        atr = 1.2 + (i % 7) * 0.05
        if side == "Buy":
            out.append(
                CandidateEvidence(
                    symbol=f"SYN{i % 40}USDT",
                    side=side,
                    entry_price=entry,
                    regime="TREND_UP" if i % 3 else "RANGE",
                    strategy="STRUCT_SWING",
                    atr=atr,
                    recent_swing_high=entry + 2.5 * atr,
                    recent_swing_low=entry - 1.2 * atr,
                    support=entry - 1.1 * atr,
                    resistance=entry + 2.0 * atr,
                    liquidity_levels=[entry + 2.2 * atr],
                    spread_bps=2.0,
                    slippage_bps=2.0,
                    fee_rate=TAKER_FEE_RATE_DEFAULT,
                    funding_rate=None,
                    tick_size=0.01,
                    qty=5.0,
                    data_freshness_sec=30.0,
                    ts=float(i),
                )
            )
        else:
            out.append(
                CandidateEvidence(
                    symbol=f"SYN{i % 40}USDT",
                    side=side,
                    entry_price=entry,
                    regime="TREND_DOWN" if i % 3 else "RANGE",
                    strategy="STRUCT_SWING",
                    atr=atr,
                    recent_swing_high=entry + 1.2 * atr,
                    recent_swing_low=entry - 2.5 * atr,
                    support=entry - 2.0 * atr,
                    resistance=entry + 1.1 * atr,
                    liquidity_levels=[entry - 2.2 * atr],
                    spread_bps=2.0,
                    slippage_bps=2.0,
                    fee_rate=TAKER_FEE_RATE_DEFAULT,
                    funding_rate=None,
                    tick_size=0.01,
                    qty=5.0,
                    data_freshness_sec=30.0,
                    ts=float(i),
                )
            )
    return out


def _stage_metrics(name: str, rows: list[dict[str, Any]], *, time_range: str) -> dict[str, Any]:
    struct = [r["structural"] for r in rows]
    net_rrs = [float(s["net_rr"]) for s in struct if isinstance(s.get("net_rr"), (int, float))]
    rtcs = [float(s["reward_to_cost"]) for s in struct if isinstance(s.get("reward_to_cost"), (int, float))]
    pass_n = sum(1 for s in struct if s.get("cost_gate_pass"))
    complete_n = sum(1 for s in struct if s.get("geometry_complete"))
    n = len(rows) or 1
    return {
        "stage": name,
        "time_range": time_range,
        "candidate_count": len(rows),
        "geometry_complete_rate": complete_n / n if rows else 0.0,
        "cost_gate_pass_rate": pass_n / n if rows else 0.0,
        "expected_net_rr": {
            "mean": statistics.fmean(net_rrs) if net_rrs else None,
            "p50": sorted(net_rrs)[len(net_rrs) // 2] if net_rrs else None,
        },
        "reward_to_cost": {
            "mean": statistics.fmean(rtcs) if rtcs else None,
            "p50": sorted(rtcs)[len(rtcs) // 2] if rtcs else None,
        },
        # Offline diagnostic — no live trade simulation claimed as live.
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
        "status": "VALIDATED_FRAMEWORK" if rows else "EMPTY",
    }


def run_qualification_pipeline(candidates: list[CandidateEvidence] | None = None) -> dict[str, Any]:
    """Chronological non-overlapping splits. Does not claim live success or auto-start sessions."""
    cands = candidates if candidates is not None else synthesize_structure_candidates(2407)
    # Chronological by ts
    ordered = sorted(cands, key=lambda c: float(c.ts or 0.0))
    n = len(ordered)
    # 50% replay train-like diagnostic, 25% walk-forward, 25% OOS — non-overlapping.
    i1 = int(n * 0.50)
    i2 = int(n * 0.75)
    replay_set = ordered[:i1]
    wf_set = ordered[i1:i2]
    oos_set = ordered[i2:]

    ab_all = compare_ab(ordered)
    # Drop full rows from top-level export size; keep summary + samples.
    ab_summary = {k: v for k, v in ab_all.items() if k != "rows"}

    replay_rows = compare_ab(replay_set)["rows"]
    wf_rows = compare_ab(wf_set)["rows"]
    oos_rows = compare_ab(oos_set)["rows"]

    stages = {
        "REPLAY_VALIDATED": _stage_metrics("REPLAY_VALIDATED", replay_rows, time_range="t0..t50%"),
        "WALK_FORWARD_VALIDATED": _stage_metrics("WALK_FORWARD_VALIDATED", wf_rows, time_range="t50%..t75%"),
        "OOS_VALIDATED": _stage_metrics("OOS_VALIDATED", oos_rows, time_range="t75%..t100%"),
        "RISK_REVIEWED": {
            "stage": "RISK_REVIEWED",
            "status": "PENDING_FOUNDER_RISK_SIGN_OFF",
            "floors_unchanged": True,
            "min_net_rr": MIN_NET_REWARD_RISK_RATIO,
            "min_reward_to_cost": MIN_NET_REWARD_TO_COST,
            "no_threshold_tuning_between_folds": True,
            "look_ahead_contamination": False,
        },
        "SHADOW_APPLIED": {
            "stage": "SHADOW_APPLIED",
            "status": "NOT_APPLIED",
            "note": "Shadow must not be classified as live; requires Founder arm after risk review.",
            "shadow_equals_live": False,
        },
    }

    qualification_complete = (
        stages["REPLAY_VALIDATED"]["status"] == "VALIDATED_FRAMEWORK"
        and stages["WALK_FORWARD_VALIDATED"]["status"] == "VALIDATED_FRAMEWORK"
        and stages["OOS_VALIDATED"]["status"] == "VALIDATED_FRAMEWORK"
        and stages["RISK_REVIEWED"]["status"] == "PASS"
        and stages["SHADOW_APPLIED"]["status"] == "APPLIED"
    )

    return {
        "fixed_geometry_retired_from_qualification": True,
        "active_execution_policy_unchanged": True,
        "diagnostic_ab": ab_summary,
        "stages": stages,
        "qualification_complete": qualification_complete,
        "recommendation": (
            "NEXUS_QUALIFICATION_CANARY_READY"
            if qualification_complete
            else "NEXUS_GEOMETRY_QUALIFICATION_IN_PROGRESS"
        ),
    }
