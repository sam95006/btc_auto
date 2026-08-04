"""V1.1 Autonomous Execution Simulator.

Wires together:

  * :mod:`backend.nexus_execution.contracts`      — versioned execution contract
  * :mod:`backend.nexus_execution.instrument`     — tick/lot/notional validation
  * :mod:`backend.nexus_execution.risk_gates`     — immutable risk gates
  * :mod:`backend.nexus_execution.fill_engine`    — conservative fill semantics
  * :mod:`backend.nexus_execution.cost_model`     — exact-decimal cost bridge
  * :mod:`backend.nexus_execution.security_boundary` — no-exchange-write guard

The simulator is entirely local. It never imports an exchange SDK. It does
not spawn threads, sockets or subprocesses. Every method is deterministic
given (intent, bar, config).

Compatibility:
  Agent B's V1 session orchestrator still imports the V1 simulator directly.
  V1.1 lives alongside V1 without changing the V1 module's public API.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from backend.nexus_execution import security_boundary
from backend.nexus_execution.contracts import (
    CONTRACT_VERSION,
    CompletedTrade,
    CostBridge,
    FillEvent,
    InstrumentSpec,
    OrderIntent,
    OrderRecord,
    PositionRecord,
)
from backend.nexus_execution.cost_model import (
    COST_MODEL_VERSION,
    DEFAULT_CANCEL_REPLACE_PENALTY,
    DEFAULT_PARTIAL_FILL_PENALTY,
    DEFAULT_SLIPPAGE_BPS,
    DEFAULT_SPREAD_BPS,
    cancel_replace_component,
    compose_cost_bridge,
    entry_leg_cost,
    exit_leg_cost,
    funding_component,
    partial_fill_component,
)
from backend.nexus_execution.fill_engine import BarContext, FillOutcome, try_fill
from backend.nexus_execution.instrument import DEFAULT_INSTRUMENTS, validate_intent
from backend.nexus_execution.risk_gates import (
    RiskDecision,
    RiskLimits,
    RiskState,
    evaluate_intent,
)

EXECUTION_MODE = security_boundary.EXECUTION_MODE
SIMULATOR_VERSION = "autonomous_execution_simulator_v1_1"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _order_id_for(intent: OrderIntent) -> str:
    h = hashlib.sha256(
        f"{intent.idempotency_key}|{intent.symbol}|{intent.side}|{intent.order_type}|"
        f"{intent.qty}|{intent.price}|{intent.stop_price}".encode()
    ).hexdigest()
    return h[:24]


def _position_id_for(intent: OrderIntent) -> str:
    return hashlib.sha256(f"pos|{intent.idempotency_key}".encode()).hexdigest()[:24]


def _fill_to_dict(fill: FillEvent) -> dict[str, Any]:
    return {
        "order_id": fill.order_id,
        "fill_id": fill.fill_id,
        "qty": format(fill.qty, "f"),
        "price": format(fill.price, "f"),
        "fee": format(fill.fee, "f"),
        "is_taker": fill.is_taker,
        "bar_index": fill.bar_index,
    }


@dataclass
class SimulatorCounters:
    """Every counter surfaced in the readiness report."""

    order_created_count: int = 0
    partially_filled_count: int = 0
    filled_count: int = 0
    cancelled_count: int = 0
    rejected_count: int = 0
    expired_count: int = 0
    unfilled_count: int = 0
    position_open_count: int = 0
    position_closed_count: int = 0
    simulated_liquidation_count: int = 0
    duplicate_position_count: int = 0
    residual_exposure_count: int = 0
    cost_bridge_failure_count: int = 0
    risk_limit_bypass_count: int = 0
    reduce_only_violation_count: int = 0
    tick_size_violation_count: int = 0
    quantity_step_violation_count: int = 0
    min_notional_violation_count: int = 0
    instrument_halted_count: int = 0
    stale_mark_reject_count: int = 0
    missing_index_reject_count: int = 0
    funding_debit_count: int = 0
    funding_credit_count: int = 0
    same_bar_ambiguous_count: int = 0
    cancel_replace_count: int = 0
    duplicate_intent_ignored_count: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


class AutonomousExecutionSimulatorV11:
    """Founder-only conservative deterministic execution simulator."""

    def __init__(
        self,
        *,
        max_positions: int = 2,
        max_intents: int = 2,
        leverage: int = 25,
        margin_usdt: Decimal | float | int = Decimal("20"),
        instruments: dict[str, InstrumentSpec] | None = None,
        spread_bps: Decimal | None = None,
        slippage_bps: Decimal | None = None,
    ) -> None:
        margin = margin_usdt if isinstance(margin_usdt, Decimal) else Decimal(str(margin_usdt))
        self.limits = RiskLimits(
            max_positions=max_positions,
            max_intents=max_intents,
            leverage=leverage,
            margin_usdt=margin,
        )
        self.instruments = instruments or dict(DEFAULT_INSTRUMENTS)
        self.spread_bps = spread_bps or DEFAULT_SPREAD_BPS
        self.slippage_bps = slippage_bps or DEFAULT_SLIPPAGE_BPS
        self.orders: dict[str, OrderRecord] = {}
        self.positions: dict[str, PositionRecord] = {}
        self.completed_trades: list[CompletedTrade] = []
        self.intent_owners: dict[str, str] = {}
        # Track pending cancel-replace cycles per intent key so we can charge the
        # penalty exactly once per replacement.
        self.cancel_replace_cycles: dict[str, int] = {}
        # Extra fills (beyond the first) per opened position, for partial-fill cost.
        self.partial_fill_extras: dict[str, int] = {}
        self.counters = SimulatorCounters()
        self.audit: list[dict[str, Any]] = []
        # Position -> exit order tracker for reduce-only accounting
        self._exit_intent_key: dict[str, str] = {}
        # Position -> funding intervals accumulator (signed)
        self._funding: dict[str, tuple[Decimal, int]] = {}

    # --- introspection helpers -------------------------------------------

    def _open_positions(self) -> list[PositionRecord]:
        return [p for p in self.positions.values() if p.state in {"OPEN", "OPENING", "REDUCING"}]

    def _pending_orders(self) -> list[OrderRecord]:
        return [
            o
            for o in self.orders.values()
            if o.state in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED", "CANCEL_PENDING"}
        ]

    def _risk_state(self) -> RiskState:
        open_positions = self._open_positions()
        return RiskState(
            open_position_count=len(open_positions),
            pending_intent_count=len(self._pending_orders()),
            open_position_symbols=frozenset(p.symbol for p in open_positions),
        )

    def report(self) -> dict[str, Any]:
        residual = sum(
            1
            for p in self.positions.values()
            if p.state in {"OPEN", "OPENING", "REDUCING"} and p.qty != 0
        )
        self.counters.residual_exposure_count = residual
        return {
            "schema": SIMULATOR_VERSION,
            "contract_version": CONTRACT_VERSION,
            "cost_model_version": COST_MODEL_VERSION,
            "execution_mode": EXECUTION_MODE,
            "max_positions": self.limits.max_positions,
            "max_intents": self.limits.max_intents,
            "leverage": self.limits.leverage,
            "margin_usdt": format(self.limits.margin_usdt, "f"),
            "margin_mode": self.limits.margin_mode,
            "max_leverage_ceiling": self.limits.max_leverage_ceiling,
            "spread_bps": format(self.spread_bps, "f"),
            "slippage_bps": format(self.slippage_bps, "f"),
            "counters": self.counters.as_dict(),
            "open_position_count": len(self._open_positions()),
            "pending_order_count": len(self._pending_orders()),
            "completed_trade_count": len(self.completed_trades),
            "exchange_write_attempt_count": security_boundary.exchange_write_attempt_count(),
            "demo_order_count": security_boundary.demo_order_count(),
            "mainnet": security_boundary.is_mainnet(),
            "real_money": security_boundary.is_real_money(),
            "fill_policy": (
                "TRADE_THROUGH_ONE_TICK_REQUIRED; TOUCH_ALONE_INSUFFICIENT; "
                "SAME_BAR_STOP_TARGET=BLOCKED_AMBIGUOUS; STOP_ARM_ON_MARK_OR_PATH"
            ),
            "created_at": _utc(),
        }

    # --- order lifecycle -------------------------------------------------

    def _resolve_intent(self, req: dict[str, Any]) -> OrderIntent:
        def _dec(v: Any) -> Decimal:
            if v is None:
                return None  # type: ignore[return-value]
            if isinstance(v, Decimal):
                return v
            return Decimal(str(v))

        return OrderIntent(
            idempotency_key=str(req["idempotency_key"]),
            symbol=str(req["symbol"]),
            side=str(req["side"]).upper(),
            order_type=str(req["order_type"]).upper(),
            qty=_dec(req["qty"]),
            price=_dec(req.get("price")) if req.get("price") is not None else None,
            stop_price=_dec(req.get("stop_price")) if req.get("stop_price") is not None else None,
            reduce_only=bool(req.get("reduce_only")),
            leverage=int(req.get("leverage") or self.limits.leverage),
            margin_mode=str(req.get("margin_mode") or self.limits.margin_mode).upper(),
            time_in_force=str(req.get("time_in_force") or "GTC").upper(),
            expires_at_bar=req.get("expires_at_bar"),
            requested_actions=tuple(req.get("requested_actions") or ()),
            client_tag=req.get("client_tag"),
        )

    def create_order(self, req: dict[str, Any], *, mark_price: Decimal | float | int) -> dict[str, Any]:
        """Register a new order intent.

        Returns a dict with:
          * ``status``   ACCEPTED | REJECTED | DUPLICATE_IGNORED
          * ``order_id`` deterministic hash of the intent
          * ``reason``   present on REJECTED
        """
        intent = self._resolve_intent(req)
        mark = mark_price if isinstance(mark_price, Decimal) else Decimal(str(mark_price))

        if intent.idempotency_key in self.intent_owners:
            self.counters.duplicate_intent_ignored_count += 1
            existing_id = self.intent_owners[intent.idempotency_key]
            self.audit.append(
                {
                    "ts": _utc(),
                    "action": "duplicate_intent_ignored",
                    "idempotency_key": intent.idempotency_key,
                    "canonical_order_id": existing_id,
                }
            )
            return {
                "status": "DUPLICATE_IGNORED",
                "order_id": existing_id,
                "canonical_owner": existing_id,
                "state": self.orders[existing_id].state,
            }

        spec = self.instruments.get(intent.symbol)
        if spec is None:
            self.counters.rejected_count += 1
            return {"status": "REJECTED", "reason": "UNKNOWN_INSTRUMENT"}

        # Risk gate first (immutable limits — cannot be overridden).
        decision = evaluate_intent(self.limits, self._risk_state(), req)
        if not decision.allowed:
            self.counters.rejected_count += 1
            self.audit.append(
                {
                    "ts": _utc(),
                    "action": "risk_reject",
                    "reason": decision.reason,
                    "detail": decision.detail,
                    "idempotency_key": intent.idempotency_key,
                }
            )
            payload: dict[str, Any] = {
                "status": "REJECTED",
                "reason": decision.reason,
                "order_or_policy_mutation": decision.order_or_policy_mutation,
            }
            if decision.detail is not None:
                payload["detail"] = decision.detail
            return payload

        # Instrument gate (tick/lot/notional/status/stale mark).
        v = validate_intent(
            spec,
            qty=intent.qty,
            price=intent.price,
            stop_price=intent.stop_price,
            mark_price=mark,
            order_type=intent.order_type,
        )
        if v is not None:
            self.counters.rejected_count += 1
            reason = v["reason"]
            if reason == "TICK_SIZE_VIOLATION":
                self.counters.tick_size_violation_count += 1
            elif reason == "QUANTITY_STEP_VIOLATION":
                self.counters.quantity_step_violation_count += 1
            elif reason == "MIN_NOTIONAL_VIOLATION":
                self.counters.min_notional_violation_count += 1
            elif reason == "INSTRUMENT_HALTED":
                self.counters.instrument_halted_count += 1
            self.audit.append(
                {
                    "ts": _utc(),
                    "action": "instrument_reject",
                    **v,
                    "idempotency_key": intent.idempotency_key,
                }
            )
            return {"status": "REJECTED", **v}

        oid = _order_id_for(intent)
        record = OrderRecord(order_id=oid, intent=intent, state="CREATED")
        record.advance_state("ACCEPTED")
        self.orders[oid] = record
        self.intent_owners[intent.idempotency_key] = oid
        self.counters.order_created_count += 1
        return {"status": "ACCEPTED", "order_id": oid, "state": record.state}

    def cancel(self, order_id: str, *, reason: str = "operator") -> dict[str, Any]:
        order = self.orders.get(order_id)
        if order is None:
            return {"status": "REJECTED", "reason": "UNKNOWN_ORDER"}
        if order.state in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}:
            return {"status": order.state}
        if order.state == "PARTIALLY_FILLED":
            order.advance_state("CANCEL_PENDING")
        else:
            order.advance_state("CANCEL_PENDING")
        order.advance_state("CANCELLED")
        order.cancel_reason = reason
        self.counters.cancelled_count += 1
        return {"status": "CANCELLED", "order_id": order_id, "reason": reason}

    def cancel_replace(
        self,
        order_id: str,
        new_intent: dict[str, Any],
        *,
        mark_price: Decimal | float | int,
    ) -> dict[str, Any]:
        """Cancel ``order_id`` and register ``new_intent`` (charges cancel-replace penalty)."""
        cancelled = self.cancel(order_id, reason="cancel_replace")
        if cancelled.get("status") != "CANCELLED":
            return cancelled
        prior = self.orders[order_id]
        # Preserve the cancel-replace charge scoped to the *replacement's* intent key so
        # the eventual completed trade absorbs it.
        replacement_key = str(new_intent.get("idempotency_key"))
        self.cancel_replace_cycles[replacement_key] = (
            self.cancel_replace_cycles.get(replacement_key, 0) + 1
        )
        # Also credit the prior key for observability.
        prior_key = prior.intent.idempotency_key
        self.cancel_replace_cycles[prior_key] = self.cancel_replace_cycles.get(prior_key, 0) + 1
        prior.cancel_replace_count += 1
        self.counters.cancel_replace_count += 1
        created = self.create_order(new_intent, mark_price=mark_price)
        created["prior_order_id"] = order_id
        return created

    def expire(self, order_id: str, *, reason: str = "GTC_EXPIRY") -> dict[str, Any]:
        order = self.orders.get(order_id)
        if order is None:
            return {"status": "REJECTED", "reason": "UNKNOWN_ORDER"}
        if order.state in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}:
            return {"status": order.state}
        order.advance_state("EXPIRED")
        order.cancel_reason = reason
        self.counters.expired_count += 1
        return {"status": "EXPIRED", "order_id": order_id, "reason": reason}

    # --- fill lifecycle --------------------------------------------------

    def try_fill(
        self,
        order_id: str,
        bar: BarContext,
        *,
        partial_ratio: Decimal | float | int | None = None,
    ) -> dict[str, Any]:
        order = self.orders.get(order_id)
        if order is None:
            return {"status": "REJECTED", "reason": "UNKNOWN_ORDER"}
        spec = self.instruments[order.intent.symbol]

        ratio = None
        if partial_ratio is not None:
            ratio = partial_ratio if isinstance(partial_ratio, Decimal) else Decimal(str(partial_ratio))

        outcome = try_fill(order, spec, bar, partial_ratio=ratio)

        if outcome.status == "REJECTED":
            order.reject_reason = outcome.reject_reason
            # Track bar-level rejection reasons; do not double-count risk rejects.
            if outcome.reject_reason == "STALE_MARK_PRICE":
                self.counters.stale_mark_reject_count += 1
            elif outcome.reject_reason == "INDEX_PRICE_MISSING":
                self.counters.missing_index_reject_count += 1
            # Note: the ORDER remains in its current state — engine rejects the bar, not
            # the order intent, so the caller can retry on a healthy bar. We still
            # surface a "REJECTED" outcome to the caller for this bar.
            return {"status": "REJECTED", "reason": outcome.reject_reason, "order_id": order_id}

        if outcome.status == "BLOCKED_AMBIGUOUS":
            self.counters.same_bar_ambiguous_count += 1
            # Mark the entry order as rejected so it cannot flow into a trade.
            if order.state != "REJECTED":
                order.advance_state("REJECTED")
                order.reject_reason = outcome.reject_reason
                self.counters.rejected_count += 1
            # If this is a stop/tp against an open position, mark that position ambiguous.
            for pos in self._open_positions():
                if pos.symbol == order.intent.symbol and pos.side == (
                    "LONG" if order.intent.side == "SELL" else "SHORT"
                ):
                    pos.advance_state("BLOCKED_AMBIGUOUS")
            return {"status": "BLOCKED_AMBIGUOUS", "reason": outcome.reject_reason}

        if outcome.status == "EXPIRED":
            order.advance_state("EXPIRED")
            order.cancel_reason = outcome.reject_reason or "EXPIRED"
            self.counters.expired_count += 1
            return {"status": "EXPIRED", "order_id": order_id}

        if outcome.status == "UNFILLED":
            self.counters.unfilled_count += 1
            return {"status": "UNFILLED", "order_id": order_id, "state": order.state}

        # A concrete fill occurred (PARTIALLY_FILLED or FILLED).
        assert outcome.fills
        for fill in outcome.fills:
            self._apply_fill(order, fill)

        if outcome.status == "PARTIALLY_FILLED":
            self.counters.partially_filled_count += 1
            order.partial_fill_count += 1
            order.advance_state("PARTIALLY_FILLED")
            return {
                "status": "PARTIALLY_FILLED",
                "order_id": order_id,
                "filled_qty": format(order.filled_qty, "f"),
                "fills": [_fill_to_dict(f) for f in outcome.fills],
            }

        # Fully filled — must transition through PARTIALLY_FILLED if it wasn't there.
        if order.state == "PARTIALLY_FILLED":
            order.advance_state("FILLED")
        else:
            order.advance_state("FILLED")
        self.counters.filled_count += 1

        # Attach a position or close one, depending on reduce_only.
        return self._materialise_position(order, outcome)

    def _apply_fill(self, order: OrderRecord, fill: FillEvent) -> None:
        prev_filled = order.filled_qty
        prev_notional = order.avg_fill_price * prev_filled
        new_notional = prev_notional + fill.price * fill.qty
        new_filled = prev_filled + fill.qty
        order.filled_qty = new_filled
        order.avg_fill_price = new_notional / new_filled if new_filled != 0 else Decimal(0)
        order.fills.append(fill)
        order.accumulated_fee = order.accumulated_fee + fill.fee

    # --- position materialisation ---------------------------------------

    def _materialise_position(self, order: OrderRecord, outcome: FillOutcome) -> dict[str, Any]:
        intent = order.intent
        spec = self.instruments[intent.symbol]
        if intent.reduce_only:
            return self._close_position_via(order, spec)
        return self._open_position_via(order, spec)

    def _open_position_via(self, order: OrderRecord, spec: InstrumentSpec) -> dict[str, Any]:
        intent = order.intent
        pid = _position_id_for(intent)
        if pid in self.positions and self.positions[pid].state in {"OPEN", "OPENING", "REDUCING"}:
            # Should be impossible thanks to idempotency, but guard anyway.
            self.counters.duplicate_position_count += 1
            return {
                "status": "FILLED",
                "order_id": order.order_id,
                "position_id": pid,
                "duplicate": True,
            }
        side = "LONG" if intent.side == "BUY" else "SHORT"
        pos = PositionRecord(
            position_id=pid,
            symbol=intent.symbol,
            side=side,
            qty=order.filled_qty,
            avg_entry_price=order.avg_fill_price,
            leverage=intent.leverage,
            margin_usdt=self.limits.margin_usdt,
        )
        pos.advance_state("OPEN")
        # Liquidation distance for isolated margin (rough): margin covers ~50% MMR buffer.
        # We keep it conservative and only use it as an *availability* signal, never to
        # simulate real liquidation without an explicit trigger.
        try:
            liq_buffer = (self.limits.margin_usdt * Decimal("0.5")) / order.filled_qty
            if intent.side == "BUY":
                pos.liquidation_price = order.avg_fill_price - liq_buffer
            else:
                pos.liquidation_price = order.avg_fill_price + liq_buffer
        except Exception:  # pragma: no cover — defensive
            pos.liquidation_price = None
        self.positions[pid] = pos
        self.counters.position_open_count += 1
        # Track any partial-fill extras that will contribute to the eventual trade cost.
        if order.partial_fill_count > 0:
            self.partial_fill_extras[pid] = order.partial_fill_count
        return {
            "status": "FILLED",
            "order_id": order.order_id,
            "position_id": pid,
            "fill_price": format(order.avg_fill_price, "f"),
            "liquidation_price": format(pos.liquidation_price, "f") if pos.liquidation_price else None,
        }

    def _close_position_via(self, order: OrderRecord, spec: InstrumentSpec) -> dict[str, Any]:
        intent = order.intent
        # Locate the matching open position (same symbol, opposite side).
        target = None
        for pos in self._open_positions():
            if pos.symbol != intent.symbol:
                continue
            if pos.side == "LONG" and intent.side == "SELL":
                target = pos
                break
            if pos.side == "SHORT" and intent.side == "BUY":
                target = pos
                break
        if target is None:
            self.counters.reduce_only_violation_count += 1
            return {
                "status": "REJECTED",
                "reason": "REDUCE_ONLY_WITHOUT_POSITION",
                "order_id": order.order_id,
            }
        close_qty = min(order.filled_qty, target.qty)
        if close_qty <= 0:
            self.counters.reduce_only_violation_count += 1
            return {"status": "REJECTED", "reason": "REDUCE_ONLY_NON_POSITIVE"}

        entry_orders = self._find_entry_orders(target.position_id)
        entry_order = entry_orders[-1] if entry_orders else None
        exit_price = order.avg_fill_price
        # Cost legs.
        entry_is_taker = True
        if entry_order and entry_order.fills:
            entry_is_taker = any(f.is_taker for f in entry_order.fills)
        exit_is_taker = any(f.is_taker for f in order.fills) if order.fills else True

        entry_fee, entry_spread, entry_slippage = entry_leg_cost(
            spec,
            price=target.avg_entry_price,
            qty=close_qty,
            is_taker=entry_is_taker,
            spread_bps=self.spread_bps,
            slippage_bps=self.slippage_bps,
        )
        exit_fee, exit_spread, exit_slippage = exit_leg_cost(
            spec,
            price=exit_price,
            qty=close_qty,
            is_taker=exit_is_taker,
            spread_bps=self.spread_bps,
            slippage_bps=self.slippage_bps,
        )
        funding = self._consume_funding(target.position_id)
        partial = partial_fill_component(
            extra_fills=self.partial_fill_extras.get(target.position_id, 0)
            + max(0, order.partial_fill_count),
        )
        cancels = self.cancel_replace_cycles.pop(intent.idempotency_key, 0)
        cancel_cost = cancel_replace_component(cycles=cancels)
        cost_bridge = compose_cost_bridge(
            side=target.side,
            qty=close_qty,
            entry_price=target.avg_entry_price,
            exit_price=exit_price,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            entry_spread=entry_spread,
            exit_spread=exit_spread,
            entry_slippage=entry_slippage,
            exit_slippage=exit_slippage,
            funding=funding,
            partial_fill=partial,
            cancel_replace=cancel_cost,
        )
        if not cost_bridge.verify():  # pragma: no cover — arithmetic must hold
            self.counters.cost_bridge_failure_count += 1

        # Update position.
        residual = target.qty - close_qty
        if residual == 0:
            target.advance_state("REDUCING") if target.state == "OPEN" else None
            target.qty = Decimal(0)
            target.realized_pnl = target.realized_pnl + cost_bridge.net_pnl
            target.advance_state("CLOSED")
            self.counters.position_closed_count += 1
        else:
            if target.state == "OPEN":
                target.advance_state("REDUCING")
            target.qty = residual
            target.realized_pnl = target.realized_pnl + cost_bridge.net_pnl
            # Reducing back to OPEN allows further reduce-only orders later.
            target.advance_state("OPEN")

        trade = CompletedTrade(
            position_id=target.position_id,
            symbol=target.symbol,
            side=target.side,
            qty=close_qty,
            entry_price=target.avg_entry_price,
            exit_price=exit_price,
            entry_order_id=entry_order.order_id if entry_order else "UNKNOWN",
            exit_order_id=order.order_id,
            cost_bridge=cost_bridge,
            open_bar=entry_order.fills[0].bar_index if (entry_order and entry_order.fills) else 0,
            close_bar=order.fills[-1].bar_index if order.fills else 0,
            liquidated=False,
        )
        self.completed_trades.append(trade)
        return {
            "status": "FILLED",
            "order_id": order.order_id,
            "position_id": target.position_id,
            "close": trade.to_json(),
        }

    def _find_entry_orders(self, position_id: str) -> list[OrderRecord]:
        return [
            o
            for o in self.orders.values()
            if not o.intent.reduce_only
            and o.state == "FILLED"
            and _position_id_for(o.intent) == position_id
        ]

    # --- funding & liquidation -------------------------------------------

    def apply_funding(self, position_id: str, rate: Decimal | float | int, *, intervals: int = 1) -> None:
        pos = self.positions.get(position_id)
        if pos is None:
            return
        r = rate if isinstance(rate, Decimal) else Decimal(str(rate))
        notional = pos.avg_entry_price * pos.qty
        component = funding_component(notional=notional, funding_rate=r, intervals=intervals)
        prev, prev_intervals = self._funding.get(position_id, (Decimal(0), 0))
        self._funding[position_id] = (prev + component, prev_intervals + intervals)
        if component > 0:
            pos.funding_debit = pos.funding_debit + component
            self.counters.funding_debit_count += 1
        elif component < 0:
            pos.funding_credit = pos.funding_credit + (-component)
            self.counters.funding_credit_count += 1

    def _consume_funding(self, position_id: str) -> Decimal:
        component, _ = self._funding.pop(position_id, (Decimal(0), 0))
        return component

    def force_liquidation(self, position_id: str, *, mark_price: Decimal | float | int) -> dict[str, Any]:
        pos = self.positions.get(position_id)
        if pos is None or pos.state not in {"OPEN", "OPENING", "REDUCING"}:
            return {"status": "REJECTED", "reason": "POSITION_NOT_OPEN"}
        px = mark_price if isinstance(mark_price, Decimal) else Decimal(str(mark_price))
        spec = self.instruments[pos.symbol]
        entry_orders = self._find_entry_orders(position_id)
        entry_order = entry_orders[-1] if entry_orders else None
        entry_is_taker = any(f.is_taker for f in entry_order.fills) if entry_order else True
        entry_fee, entry_spread, entry_slippage = entry_leg_cost(
            spec,
            price=pos.avg_entry_price,
            qty=pos.qty,
            is_taker=entry_is_taker,
            spread_bps=self.spread_bps,
            slippage_bps=self.slippage_bps,
        )
        exit_fee, exit_spread, exit_slippage = exit_leg_cost(
            spec, price=px, qty=pos.qty, is_taker=True,
            spread_bps=self.spread_bps, slippage_bps=self.slippage_bps,
        )
        funding = self._consume_funding(position_id)
        partial = partial_fill_component(extra_fills=self.partial_fill_extras.get(position_id, 0))
        cost_bridge = compose_cost_bridge(
            side=pos.side,
            qty=pos.qty,
            entry_price=pos.avg_entry_price,
            exit_price=px,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            entry_spread=entry_spread,
            exit_spread=exit_spread,
            entry_slippage=entry_slippage,
            exit_slippage=exit_slippage,
            funding=funding,
            partial_fill=partial,
            cancel_replace=Decimal(0),
        )
        trade = CompletedTrade(
            position_id=position_id,
            symbol=pos.symbol,
            side=pos.side,
            qty=pos.qty,
            entry_price=pos.avg_entry_price,
            exit_price=px,
            entry_order_id=entry_order.order_id if entry_order else "UNKNOWN",
            exit_order_id=f"LIQ:{position_id}",
            cost_bridge=cost_bridge,
            open_bar=entry_order.fills[0].bar_index if (entry_order and entry_order.fills) else 0,
            close_bar=0,
            liquidated=True,
        )
        pos.qty = Decimal(0)
        pos.realized_pnl = pos.realized_pnl + cost_bridge.net_pnl
        if pos.state == "OPEN":
            pos.advance_state("REDUCING")
        pos.advance_state("LIQUIDATED_SIMULATED")
        self.counters.simulated_liquidation_count += 1
        self.completed_trades.append(trade)
        return {"status": "LIQUIDATED_SIMULATED", "close": trade.to_json()}


# --- backwards-compatible construction helper -------------------------------


def build_default_simulator(**overrides: Any) -> AutonomousExecutionSimulatorV11:
    """Return a simulator configured with the bounded validation defaults."""
    kwargs = {
        "max_positions": 2,
        "max_intents": 2,
        "leverage": 25,
        "margin_usdt": Decimal("20"),
    }
    kwargs.update(overrides)
    return AutonomousExecutionSimulatorV11(**kwargs)


__all__ = [
    "AutonomousExecutionSimulatorV11",
    "BarContext",
    "SIMULATOR_VERSION",
    "SimulatorCounters",
    "build_default_simulator",
]
