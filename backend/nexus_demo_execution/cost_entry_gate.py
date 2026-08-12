"""Cost-adjusted entry gate — blocks fee-churn / cost-dominated setups."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_demo_execution.session_limits import (
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
)
from backend.nexus_execution.cost_model import (
    COST_MODEL_VERSION,
    estimate_round_trip_costs_float,
)


MISSING = "MISSING"
UNAVAILABLE = "UNAVAILABLE"


@dataclass
class CostGateResult:
    allowed: bool
    reason: str
    fee_rate_status: str
    funding_status: str
    estimated_net_reward: float | str = UNAVAILABLE
    estimated_net_risk: float | str = UNAVAILABLE
    estimated_total_cost: float | str = UNAVAILABLE
    net_reward_risk_ratio: float | str = UNAVAILABLE
    cost_to_gross_reward_ratio: float | str = UNAVAILABLE
    labels: list[str] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)
    fee_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "fee_rate_status": self.fee_rate_status,
            "funding_status": self.funding_status,
            "estimated_net_reward": self.estimated_net_reward,
            "estimated_net_risk": self.estimated_net_risk,
            "estimated_total_cost": self.estimated_total_cost,
            "net_reward_risk_ratio": self.net_reward_risk_ratio,
            "cost_to_gross_reward_ratio": self.cost_to_gross_reward_ratio,
            "labels": list(self.labels),
            "breakdown": dict(self.breakdown),
            "fee_meta": dict(self.fee_meta),
        }


def evaluate_cost_gate(
    *,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    qty: float,
    side: str,
    fee_rate: float | None,
    funding_rate: float | None,
    slippage_bps: float,
    fee_meta: dict[str, Any] | None = None,
) -> CostGateResult:
    labels: list[str] = []
    meta = dict(fee_meta or {})
    funding_status = UNAVAILABLE if funding_rate is None else "KNOWN"

    if fee_rate is None or fee_rate <= 0:
        status = str(meta.get("status") or "FEE_RATE_UNAVAILABLE")
        return CostGateResult(
            allowed=False,
            reason="FEE_RATE_UNKNOWN",
            fee_rate_status=status,
            funding_status=funding_status,
            estimated_net_reward=UNAVAILABLE,
            estimated_net_risk=UNAVAILABLE,
            estimated_total_cost=UNAVAILABLE,
            net_reward_risk_ratio=UNAVAILABLE,
            cost_to_gross_reward_ratio=UNAVAILABLE,
            labels=["FEE_RATE_UNKNOWN", "NEW_ENTRY_BLOCKED", status],
            breakdown={
                "gross_take_profit_pnl": UNAVAILABLE,
                "gross_stop_loss_pnl": UNAVAILABLE,
                "estimated_entry_fee": UNAVAILABLE,
                "estimated_exit_fee": UNAVAILABLE,
                "estimated_round_trip_fee": UNAVAILABLE,
                "estimated_slippage": UNAVAILABLE,
                "estimated_funding": UNAVAILABLE,
                "cost_uncertainty_buffer": UNAVAILABLE,
                "fee_rate": UNAVAILABLE,
                "notional": UNAVAILABLE,
                "fee_source": meta.get("fee_source", MISSING),
                "fee_fetch_error": meta.get("fee_fetch_error", MISSING),
                "fee_fetched_at": meta.get("fee_fetched_at", MISSING),
                "maker_fee_rate": meta.get("maker_fee_rate", UNAVAILABLE),
                "taker_fee_rate": meta.get("taker_fee_rate", UNAVAILABLE),
            },
            fee_meta=meta,
        )

    notional = abs(entry_price * qty)
    if notional <= 0 or entry_price <= 0:
        return CostGateResult(
            allowed=False,
            reason="INVALID_PRICE_QTY",
            fee_rate_status=str(meta.get("status") or "KNOWN"),
            funding_status=funding_status,
            estimated_net_reward=UNAVAILABLE,
            estimated_net_risk=UNAVAILABLE,
            estimated_total_cost=UNAVAILABLE,
            net_reward_risk_ratio=UNAVAILABLE,
            cost_to_gross_reward_ratio=UNAVAILABLE,
            labels=["INVALID_NOTIONAL"],
            breakdown={"notional": notional, "entry_price": entry_price, "qty": qty},
            fee_meta=meta,
        )

    if side.lower() == "buy":
        gross_tp = (take_profit - entry_price) * qty
        gross_sl = (entry_price - stop_loss) * qty
    else:
        gross_tp = (entry_price - take_profit) * qty
        gross_sl = (stop_loss - entry_price) * qty

    # Market impact bps are applied per leg by the canonical cost authority.
    costs = estimate_round_trip_costs_float(
        notional=notional,
        fee_rate=float(fee_rate),
        spread_bps=0.0,
        slippage_bps=max(float(slippage_bps), 0.0),
        funding_rate=funding_rate,
        include_uncertainty_buffer=True,
    )
    entry_fee = costs["entry_fee"]
    exit_fee = costs["exit_fee"]
    round_trip_fee = entry_fee + exit_fee
    slippage = costs["slippage"]
    funding_cost = costs["funding"]
    if funding_rate is None:
        labels.append("FUNDING_UNAVAILABLE_USING_CONSERVATIVE_BUFFER")
    uncertainty = costs["uncertainty"]
    total_cost = costs["total_cost"]
    net_reward = gross_tp - total_cost
    net_risk = gross_sl + total_cost
    rr = (net_reward / net_risk) if net_risk > 0 else 0.0
    cost_to_gross = (total_cost / gross_tp) if gross_tp > 0 else 999.0

    fee_status = str(meta.get("status") or "FEE_RATE_LIVE")
    breakdown = {
        "gross_take_profit_pnl": round(gross_tp, 6),
        "gross_stop_loss_pnl": round(gross_sl, 6),
        "estimated_entry_fee": round(entry_fee, 6),
        "estimated_exit_fee": round(exit_fee, 6),
        "estimated_round_trip_fee": round(round_trip_fee, 6),
        "estimated_slippage": round(slippage, 6),
        "estimated_funding": round(funding_cost, 6),
        "cost_uncertainty_buffer": round(uncertainty, 6),
        "fee_rate": fee_rate,
        "notional": round(notional, 6),
        "fee_source": meta.get("fee_source", MISSING),
        "fee_fetch_error": meta.get("fee_fetch_error"),
        "fee_fetched_at": meta.get("fee_fetched_at"),
        "maker_fee_rate": meta.get("maker_fee_rate"),
        "taker_fee_rate": meta.get("taker_fee_rate", fee_rate),
        "default_fee_fallback_used": fee_status == "FEE_RATE_CONFIGURED_CONSERVATIVE",
        "cost_model_version": COST_MODEL_VERSION,
    }

    if net_reward <= 0:
        labels.extend(["BLOCK_COST_DOMINATED_ENTRY", "gross_edge_insufficient"])
        return CostGateResult(
            False,
            "BLOCK_COST_DOMINATED_ENTRY",
            fee_status,
            funding_status,
            net_reward,
            net_risk,
            total_cost,
            rr,
            cost_to_gross,
            labels,
            breakdown,
            meta,
        )
    if net_reward < MIN_NET_REWARD_TO_COST * total_cost:
        labels.extend(["BLOCK_COST_DOMINATED_ENTRY", "fee_churn_candidate"])
        return CostGateResult(
            False,
            "BLOCK_COST_DOMINATED_ENTRY",
            fee_status,
            funding_status,
            net_reward,
            net_risk,
            total_cost,
            rr,
            cost_to_gross,
            labels,
            breakdown,
            meta,
        )
    if rr < MIN_NET_REWARD_RISK_RATIO:
        labels.extend(["BLOCK_COST_DOMINATED_ENTRY", "net_reward_risk_ratio_low"])
        return CostGateResult(
            False,
            "BLOCK_COST_DOMINATED_ENTRY",
            fee_status,
            funding_status,
            net_reward,
            net_risk,
            total_cost,
            rr,
            cost_to_gross,
            labels,
            breakdown,
            meta,
        )

    return CostGateResult(
        True,
        "COST_GATE_PASS",
        fee_status,
        funding_status,
        net_reward,
        net_risk,
        total_cost,
        rr,
        cost_to_gross,
        labels,
        breakdown,
        meta,
    )
