"""NEXUS Autonomous Execution Simulator V1.1 — local deterministic simulated broker.

HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE only.
Never instantiates an authenticated exchange-write client.
No exchange write methods exist on this path.

Fill policy (documented):
  - Candle touch alone NEVER equals a fill.
  - Limit fills require trade-through of the limit by ≥1 tick (queue-aware conservative).
  - Queue-ahead volume reduces fillable qty (partial fills).
  - Market fills use bid/ask after latency adverse move.
  - Stops trigger on mark price through-level; same-bar stop+target → BLOCKED_AMBIGUOUS.
  - Index price must be present when mark is derived / validated.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from backend.nexus_autonomy.execution_models_v1_1 import (
    FILL_POLICY_DOC,
    FillEventV11,
    InstrumentSpec,
    SimOrderV11,
    SimPositionV11,
)

TAKER_FEE = 0.00055
MAKER_FEE = 0.00020
DEFAULT_SPREAD_BPS = 1.0
DEFAULT_SLIP_BPS = 2.0
MAX_LEVERAGE_CEILING = 50
DEFAULT_LEVERAGE = 25
MARGIN_MODE = "ISOLATED"
FORBIDDEN_ACTIONS = frozenset(
    {"risk_increase", "stop_widening", "leverage_increase", "martingale", "averaging_down"}
)
FORBIDDEN_LEVERAGE = frozenset({100})


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:24]


def _round_tick(price: float, tick: float) -> float:
    if tick <= 0:
        return price
    return round(round(price / tick) * tick, 12)


def _floor_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    return math.floor(qty / step + 1e-15) * step


class AutonomousExecutionSimulatorV1_1:
    """Conservative queue-aware execution realism simulator (V1.1)."""

    VERSION = "NEXUS_AUTONOMOUS_EXECUTION_SIMULATOR_V1_1"

    def __init__(
        self,
        *,
        max_positions: int = 2,
        max_intents: int = 2,
        leverage: int = DEFAULT_LEVERAGE,
        margin_usdt: float = 20.0,
        tick_size: float = 0.1,
        qty_step: float = 0.001,
        min_notional: float = 5.0,
        maint_margin_rate: float = 0.005,
        instrument_status: str = "TRADING",
        now_ms: int = 0,
    ) -> None:
        if leverage in FORBIDDEN_LEVERAGE or leverage > MAX_LEVERAGE_CEILING:
            raise ValueError("leverage_forbidden_or_exceeds_ceiling")
        if leverage <= 0:
            raise ValueError("leverage_invalid")
        self.max_positions = int(max_positions)
        self.max_intents = int(max_intents)
        self.leverage = int(leverage)
        self.margin_usdt = float(margin_usdt)
        self.tick_size = float(tick_size)
        self.qty_step = float(qty_step)
        self.min_notional = float(min_notional)
        self.maint_margin_rate = float(maint_margin_rate)
        self.now_ms = int(now_ms)
        self.default_instrument = InstrumentSpec(
            symbol="*",
            tick_size=self.tick_size,
            qty_step=self.qty_step,
            min_notional=self.min_notional,
            status=instrument_status,
            maint_margin_rate=self.maint_margin_rate,
            max_leverage=MAX_LEVERAGE_CEILING,
        )
        self.instruments: dict[str, InstrumentSpec] = {}
        self.orders: dict[str, SimOrderV11] = {}
        self.positions: dict[str, SimPositionV11] = {}
        self.intent_owners: dict[str, str] = {}
        self.trades: list[dict[str, Any]] = []
        self.exchange_write_attempt_count = 0
        self.demo_order_count = 0
        self.counts = {
            "order_created_count": 0,
            "partially_filled_count": 0,
            "filled_count": 0,
            "cancelled_count": 0,
            "rejected_count": 0,
            "expired_count": 0,
            "replaced_count": 0,
            "unfilled_count": 0,
            "simulated_position_open_count": 0,
            "simulated_position_closed_count": 0,
            "simulated_liquidation_count": 0,
            "funding_events_count": 0,
        }
        self.audit: list[dict[str, Any]] = []

    # --- intentionally NO exchange write methods ---
    # place_order_on_exchange / submit_bybit / authenticated_write are forbidden and absent.

    def set_instrument(self, spec: InstrumentSpec) -> None:
        self.instruments[spec.symbol] = spec

    def _instrument(self, symbol: str) -> InstrumentSpec:
        return self.instruments.get(symbol, self.default_instrument)

    def advance_time(self, delta_ms: int) -> None:
        self.now_ms += int(delta_ms)
        self._expire_orders()

    def _open_position_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.state in {"OPEN", "OPENING", "REDUCING"})

    def _pending_intent_count(self) -> int:
        return sum(
            1
            for o in self.orders.values()
            if o.state in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED", "CANCEL_PENDING"}
        )

    def _symbol_exposure(self, symbol: str) -> float:
        return sum(
            p.qty for p in self.positions.values() if p.symbol == symbol and p.state in {"OPEN", "OPENING", "REDUCING"}
        )

    def _apply_costs(self, *, notional: float, is_taker: bool) -> dict[str, float]:
        fee_rate = TAKER_FEE if is_taker else MAKER_FEE
        return {
            "entry_fee": notional * fee_rate,
            "fee": notional * fee_rate,
            "spread_cost": notional * (DEFAULT_SPREAD_BPS / 10000.0),
            "slippage_cost": notional * (DEFAULT_SLIP_BPS / 10000.0),
            "fee_rate": fee_rate,
        }

    def _liquidation_price(self, *, side: str, entry: float, leverage: int) -> float:
        # Isolated approx: long liq below entry, short above.
        # distance ≈ entry * (1/leverage - maint_margin_rate)
        mm = self.maint_margin_rate
        buffer = max(1.0 / max(leverage, 1) - mm, mm)
        if side.upper() in {"LONG", "BUY"}:
            return max(_round_tick(entry * (1.0 - buffer), self.tick_size), self.tick_size)
        return _round_tick(entry * (1.0 + buffer), self.tick_size)

    def _liquidation_distance(self, *, side: str, entry: float, mark: float, leverage: int) -> float:
        liq = self._liquidation_price(side=side, entry=entry, leverage=leverage)
        return abs(mark - liq)

    def create_order(self, req: dict[str, Any]) -> dict[str, Any]:
        intent_key = str(req["idempotency_key"])
        if intent_key in self.intent_owners:
            return {
                "status": "DUPLICATE_IGNORED",
                "order_id": self.intent_owners[intent_key],
                "canonical_owner": self.intent_owners[intent_key],
            }

        actions = set(req.get("requested_actions") or [])
        if actions & FORBIDDEN_ACTIONS:
            self.counts["rejected_count"] += 1
            return {
                "status": "REJECTED",
                "reason": "HARD_RISK_OVERRIDE_REJECTED",
                "order_or_policy_mutation": False,
            }

        margin_mode = str(req.get("margin_mode", MARGIN_MODE)).upper()
        if margin_mode == "CROSS":
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "CROSS_MARGIN_FORBIDDEN"}
        if margin_mode != "ISOLATED":
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "MARGIN_MODE_MUST_BE_ISOLATED"}

        lev = int(req.get("leverage") or self.leverage)
        if lev in FORBIDDEN_LEVERAGE or lev > MAX_LEVERAGE_CEILING:
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "LEVERAGE_CEILING"}

        symbol = str(req["symbol"])
        inst = self._instrument(symbol)
        if inst.status != "TRADING":
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "INSTRUMENT_NOT_TRADING", "instrument_status": inst.status}

        reduce_only = bool(req.get("reduce_only"))
        if self._open_position_count() >= self.max_positions and not reduce_only:
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "MAX_POSITIONS"}
        if self._pending_intent_count() >= self.max_intents:
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "MAX_INTENTS"}

        tick = inst.tick_size or self.tick_size
        step = inst.qty_step or self.qty_step
        min_notional = inst.min_notional or self.min_notional

        qty = _floor_step(float(req["qty"]), step)
        px_raw = req.get("price")
        mark = req.get("mark_price")
        index_price = req.get("index_price")
        if mark is None and index_price is not None:
            mark = float(index_price)  # mark may derive from index
        px = float(px_raw if px_raw is not None else (mark or 0.0))
        if px_raw is not None:
            px = _round_tick(float(px_raw), tick)

        if qty <= 0 or px * qty < min_notional:
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "LOT_OR_NOTIONAL"}

        if reduce_only:
            exposure = self._symbol_exposure(symbol)
            side = str(req["side"]).upper()
            # reduce-only must not increase exposure
            if exposure <= 0 and side == "BUY":
                self.counts["rejected_count"] += 1
                return {"status": "REJECTED", "reason": "REDUCE_ONLY_NO_POSITION"}
            # clamp qty to exposure
            open_long = sum(
                p.qty
                for p in self.positions.values()
                if p.symbol == symbol and p.state == "OPEN" and p.side in {"LONG", "BUY"}
            )
            open_short = sum(
                p.qty
                for p in self.positions.values()
                if p.symbol == symbol and p.state == "OPEN" and p.side in {"SHORT", "SELL"}
            )
            if side == "SELL" and open_long <= 0:
                self.counts["rejected_count"] += 1
                return {"status": "REJECTED", "reason": "REDUCE_ONLY_NO_LONG"}
            if side == "BUY" and open_short <= 0:
                self.counts["rejected_count"] += 1
                return {"status": "REJECTED", "reason": "REDUCE_ONLY_NO_SHORT"}
            max_reduce = open_long if side == "SELL" else open_short
            qty = min(qty, _floor_step(max_reduce, step))
            if qty <= 0:
                self.counts["rejected_count"] += 1
                return {"status": "REJECTED", "reason": "REDUCE_ONLY_ZERO_QTY"}

        tif = str(req.get("time_in_force", "GTC")).upper()
        if tif not in {"GTC", "IOC", "FOK", "GTD"}:
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "INVALID_TIF"}

        expires_at_ms = req.get("expires_at_ms")
        if tif == "GTD" and expires_at_ms is None:
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": "GTD_REQUIRES_EXPIRES_AT"}

        stop_price = req.get("stop_price")
        if stop_price is not None:
            stop_price = _round_tick(float(stop_price), tick)

        oid = _sha(f"{intent_key}|{symbol}|{qty}|{req.get('order_type')}|{self.now_ms}")
        order = SimOrderV11(
            order_id=oid,
            intent_key=intent_key,
            symbol=symbol,
            side=str(req["side"]).upper(),
            order_type=str(req.get("order_type", "market")).lower(),
            qty=qty,
            price=px if req.get("price") is not None else (float(px_raw) if px_raw is not None else None),
            stop_price=float(stop_price) if stop_price is not None else None,
            reduce_only=reduce_only,
            time_in_force=tif,
            expires_at_ms=int(expires_at_ms) if expires_at_ms is not None else None,
            state="ACCEPTED",
            created_at_ms=self.now_ms,
            replace_of=req.get("replace_of"),
            latency_ms=int(req.get("latency_ms") or 0),
            queue_ahead_qty=float(req.get("queue_ahead_qty") or 0.0),
        )
        if order.price is not None:
            order.price = _round_tick(float(order.price), tick)

        self.orders[oid] = order
        self.intent_owners[intent_key] = oid
        self.counts["order_created_count"] += 1
        self.audit.append({"event": "ORDER_ACCEPTED", "order_id": oid, "ts_ms": self.now_ms})
        return {"status": "ACCEPTED", "order_id": oid, "state": order.state, "qty": qty}

    def cancel(self, order_id: str) -> dict[str, Any]:
        order = self.orders[order_id]
        if order.state in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED", "REPLACED"}:
            return {"status": order.state, "order_id": order_id}
        order.state = "CANCELLED"
        self.counts["cancelled_count"] += 1
        self.audit.append({"event": "CANCELLED", "order_id": order_id, "ts_ms": self.now_ms})
        return {"status": "CANCELLED", "order_id": order_id, "filled_qty": order.filled_qty, "remaining_qty": order.remaining_qty}

    def replace_order(self, order_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Cancel/replace: cancel working order, create new intent-linked order."""
        order = self.orders[order_id]
        if order.state not in {"ACCEPTED", "PARTIALLY_FILLED"}:
            return {"status": "REJECTED", "reason": "REPLACE_NOT_ALLOWED", "order_state": order.state}
        # forbid stop widening via replace
        if order.stop_price is not None and patch.get("stop_price") is not None:
            old = order.stop_price
            new = float(patch["stop_price"])
            if order.side == "SELL" and new < old:  # long stop moved further
                self.counts["rejected_count"] += 1
                return {"status": "REJECTED", "reason": "STOP_WIDENING_FORBIDDEN"}
            if order.side == "BUY" and new > old:
                self.counts["rejected_count"] += 1
                return {"status": "REJECTED", "reason": "STOP_WIDENING_FORBIDDEN"}

        cancel_res = self.cancel(order_id)
        if cancel_res["status"] != "CANCELLED":
            return {"status": "REJECTED", "reason": "REPLACE_CANCEL_FAILED", "cancel": cancel_res}
        order.state = "REPLACED"
        self.counts["replaced_count"] += 1
        # free intent key so replacement can bind (or use new key)
        old_key = order.intent_key
        new_key = str(patch.get("idempotency_key") or f"{old_key}|replace|{self.now_ms}")
        if old_key in self.intent_owners and self.intent_owners[old_key] == order_id:
            del self.intent_owners[old_key]

        remaining = order.remaining_qty
        req = {
            "idempotency_key": new_key,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": patch.get("order_type", order.order_type),
            "qty": float(patch.get("qty", remaining)),
            "price": patch.get("price", order.price),
            "stop_price": patch.get("stop_price", order.stop_price),
            "reduce_only": order.reduce_only,
            "margin_mode": MARGIN_MODE,
            "leverage": self.leverage,
            "mark_price": patch.get("mark_price"),
            "index_price": patch.get("index_price"),
            "time_in_force": patch.get("time_in_force", order.time_in_force),
            "expires_at_ms": patch.get("expires_at_ms", order.expires_at_ms),
            "latency_ms": patch.get("latency_ms", order.latency_ms),
            "queue_ahead_qty": patch.get("queue_ahead_qty", order.queue_ahead_qty),
            "replace_of": order_id,
        }
        created = self.create_order(req)
        return {"status": "REPLACED", "old_order_id": order_id, "new": created}

    def _expire_orders(self) -> None:
        for order in self.orders.values():
            if order.state not in {"ACCEPTED", "PARTIALLY_FILLED"}:
                continue
            if order.expires_at_ms is not None and self.now_ms >= order.expires_at_ms:
                order.state = "EXPIRED"
                self.counts["expired_count"] += 1
                self.audit.append({"event": "EXPIRED", "order_id": order.order_id, "ts_ms": self.now_ms})

    def try_fill(
        self,
        order_id: str,
        *,
        market_bid: float,
        market_ask: float,
        last_price: float,
        path_low: float,
        path_high: float,
        mark_price: float | None = None,
        index_price: float | None = None,
        same_bar_stop: float | None = None,
        same_bar_target: float | None = None,
        partial_ratio: float | None = None,
        opposite_volume: float | None = None,
        latency_adverse_bps: float = 0.0,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        if now_ms is not None:
            self.now_ms = int(now_ms)
            self._expire_orders()

        order = self.orders[order_id]
        if order.state in {"FILLED", "CANCELLED", "REJECTED", "EXPIRED", "REPLACED"}:
            return {"status": order.state, "order_id": order_id}

        if order.expires_at_ms is not None and self.now_ms >= order.expires_at_ms:
            order.state = "EXPIRED"
            self.counts["expired_count"] += 1
            return {"status": "EXPIRED", "order_id": order_id}

        inst = self._instrument(order.symbol)
        if inst.status != "TRADING":
            return {"status": "UNFILLED", "reason": "INSTRUMENT_NOT_TRADING", "order_id": order_id}

        # Index dependency: if mark provided without index when required flag set via index_price=None & mark set is OK;
        # but if caller asks for mark derivation and index missing while mark is None → reject fill attempt.
        if mark_price is None:
            if index_price is None:
                return {"status": "UNFILLED", "reason": "INDEX_OR_MARK_REQUIRED", "order_id": order_id}
            mark_price = float(index_price)
        else:
            mark_price = float(mark_price)
            if index_price is not None:
                # sanity: mark should be near index (basis check) — do not fill if absurdly detached
                idx = float(index_price)
                if idx > 0 and abs(mark_price - idx) / idx > 0.05:
                    return {"status": "UNFILLED", "reason": "MARK_INDEX_BASIS_EXCEEDED", "order_id": order_id}

        # Adverse-first same-bar ambiguity
        if same_bar_stop is not None and same_bar_target is not None:
            hit_stop = path_low <= same_bar_stop <= path_high
            hit_target = path_low <= same_bar_target <= path_high
            if hit_stop and hit_target:
                order.state = "REJECTED"
                order.reject_reason = "SAME_BAR_STOP_TARGET_ADVERSE_FIRST"
                self.counts["rejected_count"] += 1
                return {"status": "BLOCKED_AMBIGUOUS", "reason": order.reject_reason}

        # Latency: adverse move against order before fill
        adv = float(latency_adverse_bps) / 10000.0
        if order.latency_ms > 0 and adv == 0.0:
            adv = (order.latency_ms / 1000.0) * 0.0001  # 1 bps per 10s default scale
        bid = float(market_bid)
        ask = float(market_ask)
        if order.side == "BUY":
            ask = ask * (1.0 + adv)
        else:
            bid = bid * (1.0 - adv)

        fill_px: float | None = None
        is_taker = True
        ot = order.order_type
        tick = inst.tick_size or self.tick_size

        if ot == "market":
            fill_px = ask if order.side == "BUY" else bid
            # marketability: crossed book required
            if ask < bid:
                order.state = "REJECTED"
                order.reject_reason = "LOCKED_OR_CROSSED_BOOK_INVALID"
                self.counts["rejected_count"] += 1
                return {"status": "REJECTED", "reason": order.reject_reason}
        elif ot == "limit":
            assert order.price is not None
            # TRADE-THROUGH required: touch alone insufficient.
            if order.side == "BUY":
                # path must trade at or below limit - 1 tick
                if path_low <= (order.price - tick):
                    fill_px = order.price
                    is_taker = False
                # marketable limit (aggressive): price >= ask → taker
                elif order.price >= ask and path_low <= order.price:
                    # still require trade-through for passive; aggressive marketable takes ask
                    fill_px = ask
                    is_taker = True
            else:
                if path_high >= (order.price + tick):
                    fill_px = order.price
                    is_taker = False
                elif order.price <= bid and path_high >= order.price:
                    fill_px = bid
                    is_taker = True
        elif ot in {"stop-market", "take-profit-market"}:
            assert order.stop_price is not None
            # Mark-price trigger (not candle touch)
            if order.side == "SELL" and mark_price <= (order.stop_price - tick):
                fill_px = bid
            elif order.side == "BUY" and mark_price >= (order.stop_price + tick):
                fill_px = ask
            # last-path confirmation still needs trade-through for realism
            elif order.side == "SELL" and path_low <= (order.stop_price - tick) and mark_price <= order.stop_price:
                fill_px = bid
            elif order.side == "BUY" and path_high >= (order.stop_price + tick) and mark_price >= order.stop_price:
                fill_px = ask
        else:
            order.state = "REJECTED"
            order.reject_reason = "UNSUPPORTED_ORDER_TYPE"
            self.counts["rejected_count"] += 1
            return {"status": "REJECTED", "reason": order.reject_reason}

        if fill_px is None:
            if order.time_in_force == "IOC":
                order.state = "CANCELLED"
                self.counts["cancelled_count"] += 1
                return {"status": "CANCELLED", "reason": "IOC_UNFILLED", "order_id": order_id}
            if order.time_in_force == "FOK":
                order.state = "CANCELLED"
                self.counts["cancelled_count"] += 1
                return {"status": "CANCELLED", "reason": "FOK_UNFILLED", "order_id": order_id}
            self.counts["unfilled_count"] += 1
            return {"status": "UNFILLED", "order_id": order_id, "state": order.state}

        fill_px = _round_tick(fill_px, tick)
        remaining = order.remaining_qty
        fill_qty = remaining

        # Queue-aware conservative limit: only fill qty that traded through beyond queue
        if ot == "limit" and not is_taker:
            traded_through = 0.0
            if opposite_volume is not None:
                traded_through = max(0.0, float(opposite_volume) - order.queue_ahead_qty)
            else:
                # conservative default: assume thin trade-through = 50% remaining after queue haircut
                traded_through = max(0.0, remaining * 0.5 - order.queue_ahead_qty * 0.0)
                if order.queue_ahead_qty > 0:
                    traded_through = max(0.0, remaining * 0.25)
            fill_qty = min(fill_qty, traded_through)

        if partial_ratio is not None and 0 < partial_ratio < 1:
            fill_qty = min(fill_qty, remaining * float(partial_ratio))

        step = inst.qty_step or self.qty_step
        fill_qty = _floor_step(fill_qty, step)

        if order.time_in_force == "FOK" and fill_qty + 1e-12 < remaining:
            order.state = "CANCELLED"
            self.counts["cancelled_count"] += 1
            return {"status": "CANCELLED", "reason": "FOK_PARTIAL_NOT_ALLOWED", "order_id": order_id}

        if fill_qty <= 0:
            self.counts["unfilled_count"] += 1
            return {"status": "UNFILLED", "order_id": order_id, "reason": "QUEUE_OR_PARTIAL_ZERO"}

        return self._commit_fill(order, fill_qty=fill_qty, fill_px=fill_px, is_taker=is_taker, mark_price=mark_price)

    def _commit_fill(
        self,
        order: SimOrderV11,
        *,
        fill_qty: float,
        fill_px: float,
        is_taker: bool,
        mark_price: float,
    ) -> dict[str, Any]:
        assert fill_qty > 0
        assert fill_qty <= order.remaining_qty + 1e-12

        notional = fill_px * fill_qty
        costs = self._apply_costs(notional=notional, is_taker=is_taker)
        prev_filled = order.filled_qty
        new_filled = prev_filled + fill_qty
        if prev_filled <= 0:
            order.avg_fill_price = fill_px
        else:
            order.avg_fill_price = (order.avg_fill_price * prev_filled + fill_px * fill_qty) / new_filled
        order.filled_qty = new_filled

        fe = FillEventV11(
            order_id=order.order_id,
            fill_qty=fill_qty,
            fill_price=fill_px,
            is_taker=is_taker,
            fee=costs["fee"],
            spread_cost=costs["spread_cost"],
            slippage_cost=costs["slippage_cost"],
            ts_ms=self.now_ms,
            reason="SIMULATED_FILL",
        )
        order.fills.append(
            {
                "fill_qty": fe.fill_qty,
                "fill_price": fe.fill_price,
                "is_taker": fe.is_taker,
                "fee": fe.fee,
                "spread_cost": fe.spread_cost,
                "slippage_cost": fe.slippage_cost,
                "ts_ms": fe.ts_ms,
            }
        )
        self.trades.append({"order_id": order.order_id, "qty": fill_qty, "price": fill_px, "intent_key": order.intent_key})

        fully = order.filled_qty + 1e-12 >= order.qty
        if fully:
            order.state = "FILLED"
            self.counts["filled_count"] += 1
        else:
            order.state = "PARTIALLY_FILLED"
            self.counts["partially_filled_count"] += 1
            if order.time_in_force == "IOC":
                # cancel residual
                order.state = "CANCELLED"
                self.counts["cancelled_count"] += 1

        if order.reduce_only:
            return self._apply_reduce(order, fill_qty=fill_qty, fill_px=fill_px, costs=costs, fully=fully)

        # Position keyed by intent — duplicate intents never create a second position
        # (idempotency enforced in create_order). Partial fills accumulate on same id.
        # Averaging-down across intents is forbidden by risk policy at create_order.
        pid = _sha(f"pos|{order.intent_key}")
        side = "LONG" if order.side == "BUY" else "SHORT"
        if pid in self.positions and self.positions[pid].state in {"OPENING", "OPEN"}:
            pos = self.positions[pid]
            new_qty = pos.qty + fill_qty
            pos.entry_price = (pos.entry_price * pos.qty + fill_px * fill_qty) / new_qty
            pos.qty = new_qty
            pos.entry_fee += costs["fee"]
            pos.spread_cost += costs["spread_cost"]
            pos.slippage_cost += costs["slippage_cost"]
            pos.state = "OPEN" if fully else "OPENING"
            pos.liquidation_price = self._liquidation_price(side=side, entry=pos.entry_price, leverage=self.leverage)
        else:
            pos = SimPositionV11(
                position_id=pid,
                symbol=order.symbol,
                side=side,
                qty=fill_qty,
                entry_price=fill_px,
                leverage=self.leverage,
                margin_usdt=self.margin_usdt,
                state="OPEN" if fully else "OPENING",
                entry_fee=costs["fee"],
                spread_cost=costs["spread_cost"],
                slippage_cost=costs["slippage_cost"],
            )
            pos.liquidation_price = self._liquidation_price(side=side, entry=fill_px, leverage=self.leverage)
            self.positions[pid] = pos
            self.counts["simulated_position_open_count"] += 1

        liq_dist = self._liquidation_distance(
            side=side, entry=pos.entry_price, mark=mark_price, leverage=self.leverage
        )
        # mark-triggered liquidation check
        liq_event = self._maybe_liquidate(pos, mark_price=mark_price)

        status = "FILLED" if fully else "PARTIALLY_FILLED"
        if order.state == "CANCELLED":
            status = "PARTIALLY_FILLED_IOC_CANCELLED"
        return {
            "status": status,
            "order_id": order.order_id,
            "position_id": pid,
            "fill_price": fill_px,
            "fill_qty": fill_qty,
            "filled_qty": order.filled_qty,
            "remaining_qty": order.remaining_qty,
            "costs": costs,
            "liquidation_distance": liq_dist,
            "liquidation_price": pos.liquidation_price,
            "liquidation": liq_event,
            "reconcile_ok": abs((order.filled_qty + order.remaining_qty) - order.qty) < 1e-9,
        }

    def _apply_reduce(
        self,
        order: SimOrderV11,
        *,
        fill_qty: float,
        fill_px: float,
        costs: dict[str, float],
        fully: bool,
    ) -> dict[str, Any]:
        closed = None
        for p in self.positions.values():
            if p.symbol != order.symbol or p.state not in {"OPEN", "OPENING", "REDUCING"}:
                continue
            # reduce-only never increases exposure
            if fill_qty > p.qty + 1e-12:
                fill_qty = p.qty
            prev_qty = p.qty
            p.qty = _floor_step(max(0.0, p.qty - fill_qty), self.qty_step)
            if p.qty < 0:
                p.qty = 0.0
            p.state = "REDUCING" if p.qty > 0 else "CLOSED"
            p.exit_fee += costs["fee"]
            p.spread_cost += costs["spread_cost"]
            p.slippage_cost += costs["slippage_cost"]

            if p.side in {"LONG", "BUY"}:
                gross = (fill_px - p.entry_price) * (prev_qty - p.qty)
            else:
                gross = (p.entry_price - fill_px) * (prev_qty - p.qty)

            if p.state == "CLOSED":
                net = (
                    gross
                    - p.entry_fee
                    - p.exit_fee
                    - p.spread_cost
                    - p.slippage_cost
                    - p.funding_paid
                )
                # gross - all costs == net
                all_costs = p.entry_fee + p.exit_fee + p.spread_cost + p.slippage_cost + p.funding_paid
                assert abs((gross - all_costs) - net) < 1e-9
                p.realized_pnl = net
                p.residual_qty = p.qty
                self.counts["simulated_position_closed_count"] += 1
                closed = {
                    "position_id": p.position_id,
                    "gross_pnl": gross,
                    "entry_fee": p.entry_fee,
                    "exit_fee": p.exit_fee,
                    "spread_cost": p.spread_cost,
                    "slippage_cost": p.slippage_cost,
                    "funding_cost": p.funding_paid,
                    "all_costs": all_costs,
                    "net_pnl": net,
                    "residual_qty": p.residual_qty,
                    "cost_identity_ok": abs((gross - all_costs) - net) < 1e-9,
                }
            break

        status = "FILLED" if fully else "PARTIALLY_FILLED"
        return {
            "status": status,
            "order_id": order.order_id,
            "fill_price": fill_px,
            "fill_qty": fill_qty,
            "filled_qty": order.filled_qty,
            "remaining_qty": order.remaining_qty,
            "close": closed,
            "costs": costs,
            "reconcile_ok": abs((order.filled_qty + order.remaining_qty) - order.qty) < 1e-9,
        }

    def _maybe_liquidate(self, pos: SimPositionV11, *, mark_price: float) -> dict[str, Any] | None:
        if pos.state not in {"OPEN", "OPENING", "REDUCING"} or pos.liquidation_price is None:
            return None
        hit = False
        if pos.side in {"LONG", "BUY"} and mark_price <= pos.liquidation_price:
            hit = True
        if pos.side in {"SHORT", "SELL"} and mark_price >= pos.liquidation_price:
            hit = True
        if not hit:
            return None
        pos.state = "LIQUIDATED_SIMULATED"
        pos.qty = 0.0
        pos.residual_qty = 0.0
        self.counts["simulated_liquidation_count"] += 1
        return {"status": "LIQUIDATED_SIMULATED", "position_id": pos.position_id, "mark_price": mark_price}

    def apply_funding(self, position_id: str, rate: float, *, mark_price: float | None = None) -> dict[str, Any]:
        """Signed funding: positive rate → long pays (debit); negative → long receives (credit)."""
        p = self.positions[position_id]
        if p.state not in {"OPEN", "OPENING", "REDUCING"}:
            return {"status": "SKIP", "reason": "POSITION_NOT_OPEN"}
        px = float(mark_price if mark_price is not None else p.entry_price)
        notional = px * p.qty
        # long: funding_paid += notional * rate; short opposite
        signed = notional * float(rate)
        if p.side in {"SHORT", "SELL"}:
            signed = -signed
        p.funding_paid += signed  # debit positive, credit negative
        self.counts["funding_events_count"] += 1
        return {"status": "OK", "funding_delta": signed, "funding_paid": p.funding_paid}

    def check_maintenance_margin(self, position_id: str, *, mark_price: float) -> dict[str, Any]:
        p = self.positions[position_id]
        notional = abs(mark_price * p.qty)
        maint = notional * self.maint_margin_rate
        ok = p.margin_usdt + p.unrealized_pnl >= maint
        if p.side in {"LONG", "BUY"}:
            p.unrealized_pnl = (mark_price - p.entry_price) * p.qty
        else:
            p.unrealized_pnl = (p.entry_price - mark_price) * p.qty
        ok = (p.margin_usdt + p.unrealized_pnl) >= maint
        liq = None
        if not ok:
            liq = self._maybe_liquidate(p, mark_price=mark_price)
            if liq is None:
                # force liquidate on maint breach
                p.liquidation_price = mark_price
                liq = self._maybe_liquidate(p, mark_price=mark_price)
        return {
            "ok": ok,
            "maintenance_margin": maint,
            "equity": p.margin_usdt + p.unrealized_pnl,
            "liquidation": liq,
            "liquidation_distance": self._liquidation_distance(
                side=p.side, entry=p.entry_price, mark=mark_price, leverage=p.leverage
            ),
        }

    def open_ambiguous_position_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.state == "BLOCKED_AMBIGUOUS")

    def unclosed_intent_count(self) -> int:
        return self._pending_intent_count()

    def assert_no_exchange_write_api(self) -> None:
        forbidden_names = {
            "place_order_on_exchange",
            "submit_bybit",
            "authenticated_write",
            "exchange_write",
            "bybit_private_post",
            "create_order_exchange",
        }
        for name in forbidden_names:
            if hasattr(self, name) and callable(getattr(self, name)):
                raise AssertionError(f"forbidden_exchange_write_method:{name}")

    def report(self) -> dict[str, Any]:
        return {
            **self.counts,
            "open_ambiguous_position_count": self.open_ambiguous_position_count(),
            "unclosed_intent_count": self.unclosed_intent_count(),
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
            "demo_order_count": self.demo_order_count,
            "max_positions": self.max_positions,
            "max_intents": self.max_intents,
            "leverage": self.leverage,
            "margin_mode": MARGIN_MODE,
            "margin_usdt": self.margin_usdt,
            "fill_policy": FILL_POLICY_DOC,
            "fee_policy": {"taker": TAKER_FEE, "maker": MAKER_FEE},
            "spread_bps": DEFAULT_SPREAD_BPS,
            "slippage_bps": DEFAULT_SLIP_BPS,
            "version": self.VERSION,
            "trade_count": len(self.trades),
        }


# Alias for importers
ExecutionSimulatorV1_1 = AutonomousExecutionSimulatorV1_1
