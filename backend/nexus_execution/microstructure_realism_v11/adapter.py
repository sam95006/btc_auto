"""Adapter: microstructure book → canonical AutonomousExecutionSimulatorV11.

Session / research traffic must not invent a second fill authority. This
adapter derives ``BarContext`` bid/ask from a validated synthetic book, then
routes orders exclusively through ``NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1`` /
``AutonomousExecutionSimulatorV11``.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.nexus_execution.book_model_v11 import (
    FILL_ACCURACY_CLAIM,
    OrderBookSnapshot,
    market_impact,
    validate_book,
)
from backend.nexus_execution.fill_engine import BarContext
from backend.nexus_execution.orchestrator_adapter_v1 import (
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
    NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1,
    build_session_execution_adapter,
)
from backend.nexus_execution.execution_simulator_v1_1 import AutonomousExecutionSimulatorV11

# Re-export canonical identity for readiness artifacts.
assert CANONICAL_EXECUTION_ENGINE_COUNT == 1


class MicrostructureExecutionAdapterV11:
    """Book-aware wrapper over the single canonical execution engine."""

    def __init__(
        self,
        *,
        simulator: AutonomousExecutionSimulatorV11 | None = None,
        session_adapter: NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1 | None = None,
    ) -> None:
        self._session = session_adapter or build_session_execution_adapter(simulator=simulator)
        self._sim = self._session.canonical_engine
        self.last_book_reject: dict[str, Any] | None = None
        self.last_impact: dict[str, Any] | None = None
        self.fill_accuracy_claim = FILL_ACCURACY_CLAIM

    @property
    def canonical_engine(self) -> AutonomousExecutionSimulatorV11:
        return self._sim

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    @property
    def canonical_execution_engine(self) -> str:
        return CANONICAL_EXECUTION_ENGINE

    def bar_from_book(
        self,
        book: OrderBookSnapshot,
        *,
        bar_index: int = 1,
        open_price: Decimal | None = None,
        high: Decimal | None = None,
        low: Decimal | None = None,
        close: Decimal | None = None,
        same_bar_stop: Decimal | None = None,
        same_bar_target: Decimal | None = None,
        tick: Decimal | None = None,
    ) -> BarContext | dict[str, Any]:
        """Build a fill-engine bar from a validated book (fail-closed)."""
        reject = validate_book(book)
        if reject is not None:
            self.last_book_reject = reject.as_dict()
            return self.last_book_reject

        bid = book.best_bid.price  # type: ignore[union-attr]
        ask = book.best_ask.price  # type: ignore[union-attr]
        mid = (bid + ask) / Decimal(2)
        mark = book.mark_price if book.mark_price is not None else mid
        # Candle extremes must trade *through* limits — never touch-equals-fill.
        # Widen high/low by at least one tick beyond TOB when tick known.
        pad = tick if tick is not None else (ask - bid)
        hi = high if high is not None else (ask + pad)
        lo = low if low is not None else (bid - pad)
        self.last_book_reject = None
        return BarContext(
            bar_index=bar_index,
            open_price=open_price if open_price is not None else mid,
            high=hi,
            low=lo,
            close=close if close is not None else mid,
            mark_price=mark,
            index_price=book.index_price,
            bid=bid,
            ask=ask,
            mark_price_age_ms=book.age_ms,
            same_bar_stop=same_bar_stop,
            same_bar_target=same_bar_target,
        )

    def create_order(self, req: dict[str, Any], *, mark_price: Decimal) -> dict[str, Any]:
        return self._sim.create_order(req, mark_price=mark_price)

    def try_fill_with_book(
        self,
        order_id: str,
        book: OrderBookSnapshot | None,
        *,
        bar_index: int = 1,
        partial_ratio: Decimal | None = None,
        apply_impact: bool = False,
        tick: Decimal | None = None,
        same_bar_stop: Decimal | None = None,
        same_bar_target: Decimal | None = None,
        high: Decimal | None = None,
        low: Decimal | None = None,
    ) -> dict[str, Any]:
        """Validate book, optionally walk depth for impact, then fill via canonical sim."""
        if book is None:
            reject = validate_book(None)
            assert reject is not None
            self.last_book_reject = reject.as_dict()
            return {**self.last_book_reject, "order_id": order_id}

        bar_or_reject = self.bar_from_book(
            book,
            bar_index=bar_index,
            tick=tick,
            same_bar_stop=same_bar_stop,
            same_bar_target=same_bar_target,
            high=high,
            low=low,
        )
        if isinstance(bar_or_reject, dict):
            # Fail-closed: book gate rejects before any fill authority runs.
            # Leave order state unchanged (retryable on a healthy book), but
            # never emit fills.
            self.last_book_reject = bar_or_reject
            if bar_or_reject.get("reason") == "STALE_BOOK":
                self._sim.counters.stale_mark_reject_count += 1
            return {**bar_or_reject, "order_id": order_id}

        order = self._sim.orders.get(order_id)
        if order is not None and apply_impact and order.intent.order_type == "MARKET":
            impact = market_impact(book, side=order.intent.side, qty=order.intent.qty - order.filled_qty)
            self.last_impact = impact
            if impact.get("status") == "PARTIALLY_FILLED" and partial_ratio is None:
                req = Decimal(impact["filled_qty"])
                total = order.intent.qty
                if total > 0 and req < total:
                    partial_ratio = req / total
            elif not impact.get("ok") and impact.get("reason") == "INSUFFICIENT_DEPTH":
                return {"status": "REJECTED", "reason": "INSUFFICIENT_DEPTH", "order_id": order_id}
        else:
            self.last_impact = None

        return self._sim.try_fill(order_id, bar_or_reject, partial_ratio=partial_ratio)

    def cancel(self, order_id: str, *, reason: str = "operator") -> dict[str, Any]:
        return self._sim.cancel(order_id, reason=reason)

    def cancel_replace(
        self,
        order_id: str,
        new_req: dict[str, Any],
        *,
        mark_price: Decimal,
    ) -> dict[str, Any]:
        return self._sim.cancel_replace(order_id, new_req, mark_price=mark_price)


__all__ = [
    "ADAPTER_ID",
    "CANONICAL_EXECUTION_ENGINE",
    "CANONICAL_EXECUTION_ENGINE_COUNT",
    "MicrostructureExecutionAdapterV11",
]
