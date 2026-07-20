"""Phase 5 Gate C — Gate B → Gate C Integration Bridge.

Provides try_simulate_decision(decision) which:
  1. Takes a Gate B ResearchDecision (READY_FOR_SIMULATION status)
  2. Runs risk check → capital allocation → simulator order submission
  3. Returns a SimulationAttemptResult (never touches real execution)

Also provides read_sim_closed_positions_for_reflection() for the
Reflection role analyst to read closed simulation positions.

CONSTRAINTS:
  - Never calls real exchange API
  - Never modifies production code / scoring formulas
  - READY_FOR_SIMULATION is the only decision status that qualifies
  - Any exception during simulation is silently caught and returned as
    an error result (must never break Gate B review cycle)
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# Decision statuses that qualify for simulation
_SIM_ELIGIBLE_STATUSES = {"READY_FOR_SIMULATION"}


class SimulationAttemptResult:
    """Result of a try_simulate_decision call."""

    def __init__(
        self,
        decision_id: str,
        symbol: str,
        side: str,
        attempted: bool,
        success: bool,
        order_id: str | None,
        risk_verdict: str | None,
        allocation_qty: float | None,
        allocation_notional: float | None,
        skip_reason: str | None,
        error: str | None,
    ) -> None:
        self.decision_id = decision_id
        self.symbol = symbol
        self.side = side
        self.attempted = attempted
        self.success = success
        self.order_id = order_id
        self.risk_verdict = risk_verdict
        self.allocation_qty = allocation_qty
        self.allocation_notional = allocation_notional
        self.skip_reason = skip_reason
        self.error = error
        self.created_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisionId": self.decision_id,
            "symbol": self.symbol,
            "side": self.side,
            "attempted": self.attempted,
            "success": self.success,
            "orderId": self.order_id,
            "riskVerdict": self.risk_verdict,
            "allocationQty": self.allocation_qty,
            "allocationNotional": self.allocation_notional,
            "skipReason": self.skip_reason,
            "error": self.error,
            "createdAtMs": self.created_at_ms,
            "researchOnly": True,
            "privateApi": False,
        }


def try_simulate_decision(
    decision: dict[str, Any],
    *,
    account_id: str | None = None,
    activation_session_id: str | None = None,
) -> SimulationAttemptResult:
    """Gate B → Gate C bridge. Never throws; errors returned in result.

    Call this from Gate B after READY_FOR_SIMULATION decision is produced.
    Example:
        from backend.nexus_research.gate_b_to_gate_c import try_simulate_decision
        result = try_simulate_decision(decision.to_dict())

    Args:
        decision: dict from ResearchDecision.to_dict() or equivalent.
                  Must have: decisionId, symbol, side, status, score.
        account_id: durable paper ledger account (default PAPER_RUNTIME_DEFAULT;
                    Phase 6.3 natural PAPER uses NEXUS_PAPER_MAIN_V1).
    """
    decision_id = decision.get("decisionId") or str(uuid.uuid4())
    symbol = decision.get("symbol", "UNKNOWN")
    side = decision.get("side", "LONG")
    status = decision.get("status", "")

    # Only attempt simulation for READY_FOR_SIMULATION decisions
    if status not in _SIM_ELIGIBLE_STATUSES:
        return SimulationAttemptResult(
            decision_id=decision_id, symbol=symbol, side=side,
            attempted=False, success=False,
            order_id=None, risk_verdict=None,
            allocation_qty=None, allocation_notional=None,
            skip_reason=f"status {status!r} not eligible (need READY_FOR_SIMULATION)",
            error=None,
        )

    try:
        from backend.nexus_research.simulator import get_simulator, ORDER_MARKET
        from backend.nexus_research.sim_ledger import get_sim_ledger
        from backend.nexus_research.risk_engine import RiskRequest, get_risk_engine
        from backend.nexus_research.capital_allocator import get_capital_allocator
        from backend.nexus_research.storage import get_research_store
        from backend.nexus_research.config import resolve_limits
        from backend.nexus_research.durable_ledger import ACCOUNT_PAPER_DEFAULT

        sim = get_simulator()
        ledger_account = account_id or ACCOUNT_PAPER_DEFAULT
        ledger = get_sim_ledger(account_id=ledger_account)
        risk = get_risk_engine()
        allocator = get_capital_allocator()
        store = get_research_store()
        limits = resolve_limits()
        max_leverage = float((limits.get("maxLeverage") or {}).get("effective") or 3)
        max_margin = float((limits.get("maxMarginUsd") or {}).get("effective") or 20)
        max_open = int((limits.get("maxOpenPositions") or {}).get("effective") or 1)

        # Derive entry price from decision evidence or fallback
        evidence = decision.get("evidence") or {}
        entry_price = float(
            evidence.get("price")
            or evidence.get("lastPrice")
            or evidence.get("markPrice")
            or 65_000.0  # fallback for testing
        )
        score = float(decision.get("score", 60.0))
        leverage = min(float(decision.get("leverage", max_leverage)), max_leverage)

        open_positions = sim.list_open_positions()
        if len(open_positions) >= max_open:
            return SimulationAttemptResult(
                decision_id=decision_id, symbol=symbol, side=side,
                attempted=True, success=False,
                order_id=None, risk_verdict="MAX_OPEN_POSITIONS",
                allocation_qty=None, allocation_notional=None,
                skip_reason=f"max open positions reached ({max_open})",
                error=None,
            )

        # Ledger snapshot for equity
        snap = ledger.snapshot(unrealised_pnl=sim.total_unrealised_pnl())
        equity = snap.get("equity", 10_000.0)
        closed_count = store.count("sim_reflections")

        # Capital allocation
        existing_sym_notional = sum(
            p.get("notional", 0.0)
            for p in sim.list_open_positions(symbol=symbol)
        )
        existing_portfolio_notional = sum(
            p.get("notional", 0.0) for p in sim.list_open_positions()
        )

        alloc = allocator.allocate(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            candidate={"score": score, "side": side},
            equity=equity,
            leverage=leverage,
            existing_symbol_notional=existing_sym_notional,
            existing_portfolio_notional=existing_portfolio_notional,
            closed_trades_count=closed_count,
        )

        # Enforce max margin (notional / leverage ≈ margin)
        if alloc.notional > 0 and alloc.leverage > 0:
            margin = alloc.notional / max(alloc.leverage, 1e-9)
            if margin > max_margin:
                scale = max_margin / margin
                alloc.suggested_qty = round(alloc.suggested_qty * scale, 6)
                alloc.notional = round(alloc.notional * scale, 4)

        if alloc.suggested_qty <= 0:
            return SimulationAttemptResult(
                decision_id=decision_id, symbol=symbol, side=side,
                attempted=True, success=False,
                order_id=None, risk_verdict="ALLOCATOR_ZERO",
                allocation_qty=0.0, allocation_notional=0.0,
                skip_reason=f"allocator returned 0 qty: {alloc.reason}",
                error=None,
            )

        # Risk check
        req = RiskRequest(
            symbol=symbol,
            side=side,
            qty=alloc.suggested_qty,
            entry_price=entry_price,
            leverage=min(float(alloc.leverage), max_leverage),
            candidate={"score": score, "side": side},
        )
        verdict = risk.check(req, sim=sim, ledger=ledger)

        if not verdict.allowed:
            return SimulationAttemptResult(
                decision_id=decision_id, symbol=symbol, side=side,
                attempted=True, success=False,
                order_id=None, risk_verdict=verdict.verdict,
                allocation_qty=alloc.suggested_qty,
                allocation_notional=alloc.notional,
                skip_reason=f"risk blocked: {'; '.join(verdict.reasons)}",
                error=None,
            )

        # Submit simulated order
        qty = verdict.suggested_qty if verdict.suggested_qty else alloc.suggested_qty
        order_id = sim.submit_order(
            symbol=symbol,
            side=side,
            order_type=ORDER_MARKET,
            qty=qty,
            leverage=min(float(alloc.leverage), max_leverage),
            correlation_id=decision_id,
        )

        evidence_id = str(uuid.uuid4())
        evidence_bundle = {
            "evidenceId": evidence_id,
            "evidence_id": evidence_id,
            "sessionId": activation_session_id,
            "accountId": ledger_account,
            "candidateId": decision.get("candidateId"),
            "caseId": decision.get("caseId"),
            "decisionId": decision_id,
            "riskVerdict": verdict.verdict,
            "allocationQty": qty,
            "allocationNotional": alloc.notional,
            "simulatedOrderId": order_id,
            "entryPrice": entry_price,
            "leverage": min(float(alloc.leverage), max_leverage),
            "status": "ORDER_SUBMITTED",
            "stream": "NATURAL_PAPER",
            "researchOnly": True,
            "privateApi": False,
            "createdAtMs": int(time.time() * 1000),
        }

        # Record in research store
        store.append("sim_attempts", {
            "decisionId": decision_id,
            "symbol": symbol,
            "side": side,
            "orderId": order_id,
            "riskVerdict": verdict.verdict,
            "qty": qty,
            "entryPrice": entry_price,
            "score": score,
            "accountId": ledger_account,
            "activationSessionId": activation_session_id,
            "evidenceId": evidence_id,
            "createdAtMs": int(time.time() * 1000),
            "researchOnly": True,
            "stream": "NATURAL_PAPER",
        })
        try:
            store.append("paper_trade_evidence", evidence_bundle)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[gate_b_c] evidence persist deferred: %s", exc)

        logger.info(
            "[gate_b_c] decision %s → sim order %s %s %s qty=%s account=%s",
            decision_id, order_id, symbol, side, qty, ledger_account,
        )

        return SimulationAttemptResult(
            decision_id=decision_id, symbol=symbol, side=side,
            attempted=True, success=True,
            order_id=order_id, risk_verdict=verdict.verdict,
            allocation_qty=qty, allocation_notional=alloc.notional,
            skip_reason=None, error=None,
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning("[gate_b_c] simulation attempt failed for %s: %s", decision_id, exc)
        return SimulationAttemptResult(
            decision_id=decision_id, symbol=symbol, side=side,
            attempted=True, success=False,
            order_id=None, risk_verdict=None,
            allocation_qty=None, allocation_notional=None,
            skip_reason=None, error=str(exc),
        )


def read_sim_closed_positions_for_reflection(
    symbol: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Read closed simulation positions for the Gate B Reflection role analyst.

    Returns an empty list silently on any error (must never break Gate B).
    """
    try:
        from backend.nexus_research.simulator import get_simulator
        sim = get_simulator()
        return sim.list_closed_positions(symbol=symbol, limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[gate_b_c] read_sim_closed_positions failed: %s", exc)
        return []
