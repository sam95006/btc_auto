"""Cost-adjusted entry gate — blocks fee-churn / cost-dominated setups."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_demo_execution.session_limits import (
    COST_UNCERTAINTY_BUFFER_RATE,
    FUNDING_CONSERVATIVE_BUFFER_RATE,
    MIN_NET_REWARD_RISK_RATIO,
    MIN_NET_REWARD_TO_COST,
    TAKER_FEE_RATE_DEFAULT,
)


@dataclass
class CostGateResult:
    allowed: bool
    reason: str
    fee_rate_status: str
    funding_status: str
    estimated_net_reward: float = 0.0
    estimated_net_risk: float = 0.0
    estimated_total_cost: float = 0.0
    net_reward_risk_ratio: float = 0.0
    cost_to_gross_reward_ratio: float = 0.0
    labels: list[str] = field(default_factory=list)
    breakdown: dict[str, Any] = field(default_factory=dict)

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
) -> CostGateResult:
    labels: list[str] = []
    if fee_rate is None or fee_rate <= 0:
        return CostGateResult(
            allowed=False,
            reason="FEE_RATE_UNKNOWN",
            fee_rate_status="UNKNOWN",
            funding_status="UNAVAILABLE" if funding_rate is None else "KNOWN",
            labels=["FEE_RATE_UNKNOWN", "NEW_ENTRY_BLOCKED"],
        )

    notional = abs(entry_price * qty)
    if notional <= 0 or entry_price <= 0:
        return CostGateResult(
            allowed=False,
            reason="INVALID_PRICE_QTY",
            fee_rate_status="KNOWN",
            funding_status="UNAVAILABLE" if funding_rate is None else "KNOWN",
            labels=["INVALID_NOTIONAL"],
        )

    # Gross TP / SL PnL (price move * qty)
    if side.lower() == "buy":
        gross_tp = (take_profit - entry_price) * qty
        gross_sl = (entry_price - stop_loss) * qty
    else:
        gross_tp = (entry_price - take_profit) * qty
        gross_sl = (stop_loss - entry_price) * qty

    entry_fee = notional * fee_rate
    exit_fee = notional * fee_rate
    round_trip_fee = entry_fee + exit_fee
    slippage = notional * (slippage_bps / 10000.0)

    funding_status = "KNOWN"
    if funding_rate is None:
        funding_status = "UNAVAILABLE"
        funding_cost = notional * FUNDING_CONSERVATIVE_BUFFER_RATE
        labels.append("FUNDING_UNAVAILABLE_USING_CONSERVATIVE_BUFFER")
    else:
        funding_cost = abs(notional * funding_rate)

    uncertainty = notional * COST_UNCERTAINTY_BUFFER_RATE
    total_cost = round_trip_fee + slippage + funding_cost + uncertainty
    net_reward = gross_tp - total_cost
    net_risk = gross_sl + total_cost
    rr = (net_reward / net_risk) if net_risk > 0 else 0.0
    cost_to_gross = (total_cost / gross_tp) if gross_tp > 0 else 999.0

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
        "default_fee_fallback_used": fee_rate == TAKER_FEE_RATE_DEFAULT,
    }

    if net_reward <= 0:
        labels.extend(["BLOCK_COST_DOMINATED_ENTRY", "gross_edge_insufficient"])
        return CostGateResult(
            False,
            "BLOCK_COST_DOMINATED_ENTRY",
            "KNOWN",
            funding_status,
            net_reward,
            net_risk,
            total_cost,
            rr,
            cost_to_gross,
            labels,
            breakdown,
        )
    if net_reward < MIN_NET_REWARD_TO_COST * total_cost:
        labels.extend(["BLOCK_COST_DOMINATED_ENTRY", "fee_churn_candidate"])
        return CostGateResult(
            False,
            "BLOCK_COST_DOMINATED_ENTRY",
            "KNOWN",
            funding_status,
            net_reward,
            net_risk,
            total_cost,
            rr,
            cost_to_gross,
            labels,
            breakdown,
        )
    if rr < MIN_NET_REWARD_RISK_RATIO:
        labels.extend(["BLOCK_COST_DOMINATED_ENTRY", "net_reward_risk_ratio_low"])
        return CostGateResult(
            False,
            "BLOCK_COST_DOMINATED_ENTRY",
            "KNOWN",
            funding_status,
            net_reward,
            net_risk,
            total_cost,
            rr,
            cost_to_gross,
            labels,
            breakdown,
        )

    return CostGateResult(
        True,
        "COST_GATE_PASS",
        "KNOWN",
        funding_status,
        net_reward,
        net_risk,
        total_cost,
        rr,
        cost_to_gross,
        labels,
        breakdown,
    )
