"""Demo order execution — first controlled demo order candidate.

Source: fixture data + strategy evaluator ranking from demo_strategy.
Isolated, single symbol (BTCUSDT), VALIDATION risk tier,
stop plan, close plan, idempotent clientOrderId.

ready_for_manual_authorization=True ONLY if ALL gates pass.
order_sent=False ALWAYS.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_execution.intent import DemoOrderIntent
from backend.nexus_research.demo_execution.preflight import DemoOrderPreflight, PreflightResult
from backend.nexus_research.demo_execution.state_machine import (
    DemoOrderState,
    DemoOrderStateMachine,
)
from backend.nexus_research.demo_strategy.capital_allocator import (
    AllocationDecision,
    DemoCapitalAllocator,
)
from backend.nexus_research.demo_strategy.market_features import FIXTURE_BTCUSDT, extract_features
from backend.nexus_research.demo_strategy.risk_tiers import RiskTierName
from backend.nexus_research.demo_strategy.strategy_evaluator import evaluate

RESEARCH_ONLY: bool = True
ORDER_SENT: bool = False

CANDIDATE_SYMBOL = "BTCUSDT"
CANDIDATE_FIXTURE_ENTRY_PRICE = 105_000.0
CANDIDATE_STOP_DISTANCE_PCT = 1.5
CANDIDATE_EQUITY = 10_000.0


@dataclass
class StopPlan:
    stop_loss_price: float
    stop_distance_pct: float
    stop_type: str = "FIXED_PERCENT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "stopLossPrice": self.stop_loss_price,
            "stopDistancePct": self.stop_distance_pct,
            "stopType": self.stop_type,
        }


@dataclass
class ClosePlan:
    close_strategy: str = "STOP_LOSS_OR_MANUAL"
    take_profit_price: float | None = None
    max_hold_duration_ms: int = 3_600_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "closeStrategy": self.close_strategy,
            "takeProfitPrice": self.take_profit_price,
            "maxHoldDurationMs": self.max_hold_duration_ms,
        }


@dataclass
class FirstControlledDemoOrderCandidate:
    """First controlled order candidate — all safety checks enforced.

    order_sent is ALWAYS False.
    ready_for_manual_authorization is True ONLY if all gates pass.
    """

    intent: DemoOrderIntent
    evaluation_result: dict[str, Any]
    allocation_decision: dict[str, Any]
    preflight_result: PreflightResult
    stop_plan: StopPlan
    close_plan: ClosePlan
    state_machine: DemoOrderStateMachine
    ready_for_manual_authorization: bool
    gate_summary: dict[str, bool]
    order_sent: bool = field(default=False, init=False)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.to_dict(),
            "evaluationResult": self.evaluation_result,
            "allocationDecision": self.allocation_decision,
            "preflightResult": self.preflight_result.to_dict(),
            "stopPlan": self.stop_plan.to_dict(),
            "closePlan": self.close_plan.to_dict(),
            "stateMachine": self.state_machine.to_dict(),
            "readyForManualAuthorization": self.ready_for_manual_authorization,
            "gateSummary": self.gate_summary,
            "orderSent": False,
            "createdAtMs": self.created_at_ms,
            "source": "fixture+strategy_evaluator",
            "candidateSymbol": CANDIDATE_SYMBOL,
            "riskTier": "VALIDATION",
            "researchOnly": True,
        }


def _generate_idempotent_client_order_id(
    symbol: str,
    side: str,
    qty: float,
    leverage: int,
) -> str:
    """Deterministic clientOrderId from order parameters."""
    raw = f"nxd-demo-candidate:{symbol}:{side}:{qty}:{leverage}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"nxd56-{digest}"


def build_first_controlled_candidate(
    *,
    equity: float = CANDIDATE_EQUITY,
    entry_price: float = CANDIDATE_FIXTURE_ENTRY_PRICE,
    stop_distance_pct: float = CANDIDATE_STOP_DISTANCE_PCT,
) -> FirstControlledDemoOrderCandidate:
    """Build the first controlled demo order candidate from fixture data.

    Uses BTCUSDT fixture, VALIDATION risk tier, strategy evaluator.
    order_sent=False always.
    """
    features = extract_features(FIXTURE_BTCUSDT, source="fixture")
    eval_result = evaluate(features, "LONG")

    allocator = DemoCapitalAllocator()
    allocation = allocator.allocate(
        symbol=CANDIDATE_SYMBOL,
        direction="LONG",
        entry_price=entry_price,
        stop_distance_pct=stop_distance_pct,
        equity=equity,
        tier=RiskTierName.VALIDATION,
        is_first_order=True,
        current_open_positions=0,
        source="fixture",
    )

    sl_price = entry_price * (1.0 - stop_distance_pct / 100.0)

    client_order_id = _generate_idempotent_client_order_id(
        symbol=CANDIDATE_SYMBOL,
        side="Buy",
        qty=allocation.qty,
        leverage=allocation.leverage,
    )

    intent = DemoOrderIntent(
        intent_id=f"intent-{uuid.uuid4().hex[:16]}",
        symbol=CANDIDATE_SYMBOL,
        side="Buy",
        qty=allocation.qty,
        leverage=allocation.leverage,
        entry_price=entry_price,
        stop_loss_price=sl_price,
        take_profit_price=None,
        risk_tier=RiskTierName.VALIDATION.value,
        client_order_id=client_order_id,
        source="fixture+strategy_evaluator",
    )

    preflight = DemoOrderPreflight(
        max_open_positions=1,
        current_open_positions=0,
        ambiguous_orders_exist=False,
    )
    preflight_result = preflight.check(intent)

    stop_plan = StopPlan(
        stop_loss_price=sl_price,
        stop_distance_pct=stop_distance_pct,
    )

    close_plan = ClosePlan(
        close_strategy="STOP_LOSS_OR_MANUAL",
        take_profit_price=None,
        max_hold_duration_ms=3_600_000,
    )

    sm = DemoOrderStateMachine()
    gate_summary = {
        "strategy_allows_trade": eval_result.allow_trade,
        "allocation_allows_trade": allocation.allow_trade,
        "preflight_all_passed": preflight_result.all_passed,
        "risk_tier_is_validation": allocation.risk_tier == RiskTierName.VALIDATION.value,
        "qty_positive": allocation.qty > 0,
        "stop_loss_set": sl_price > 0,
        "client_order_id_set": bool(client_order_id),
        "order_sent": False,
    }

    all_gates_pass = all(
        v for k, v in gate_summary.items() if k != "order_sent"
    )

    if all_gates_pass:
        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION, reason="all gates passed")
    else:
        sm.transition(DemoOrderState.PREFLIGHT_BLOCKED, reason="gate failure")

    return FirstControlledDemoOrderCandidate(
        intent=intent,
        evaluation_result=eval_result.to_dict(),
        allocation_decision=allocation.to_dict(),
        preflight_result=preflight_result,
        stop_plan=stop_plan,
        close_plan=close_plan,
        state_machine=sm,
        ready_for_manual_authorization=all_gates_pass,
        gate_summary=gate_summary,
    )
