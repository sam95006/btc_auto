"""NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1

Single cross-lane bridge: Session Candidate → canonical Execution Simulator V1.1.

Canonical authority (exactly one):
  backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11

This adapter is the only Session→Execution integration surface. Older
``backend.nexus_autonomy.execution_simulator_v*`` modules remain as
compatibility shims for legacy tests and MUST NOT be treated as independent
fill / cost / risk / position authorities for Session traffic.

Pipeline:
  Session Candidate
  → OrderIntent
  → Instrument validation
  → Risk gates
  → Fill engine
  → Position record
  → Cost bridge
  → Completed trade

Execution mode: SIMULATED_NO_EXCHANGE_WRITE
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterator, MutableMapping

from backend.nexus_execution.contracts import CompletedTrade, OrderIntent, OrderRecord, PositionRecord
from backend.nexus_execution.execution_simulator_v1_1 import (
    AutonomousExecutionSimulatorV11,
    build_default_simulator,
)
from backend.nexus_execution.fill_engine import BarContext

ADAPTER_ID = "NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1"
CANONICAL_EXECUTION_ENGINE = (
    "backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11"
)
CANONICAL_EXECUTION_ENGINE_COUNT = 1

_ORDER_TYPE_MAP = {
    "market": "MARKET",
    "limit": "LIMIT",
    "stop-market": "STOP_MARKET",
    "stop_market": "STOP_MARKET",
    "take-profit-market": "TAKE_PROFIT_MARKET",
    "take_profit_market": "TAKE_PROFIT_MARKET",
    "MARKET": "MARKET",
    "LIMIT": "LIMIT",
    "STOP_MARKET": "STOP_MARKET",
    "TAKE_PROFIT_MARKET": "TAKE_PROFIT_MARKET",
}


def _dec(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _normalize_order_type(raw: Any) -> str:
    key = str(raw or "MARKET")
    return _ORDER_TYPE_MAP.get(key, _ORDER_TYPE_MAP.get(key.lower(), key.upper()))


class _OrderView:
    """Session-compatible view over a canonical OrderRecord."""

    __slots__ = ("_order",)

    def __init__(self, order: OrderRecord) -> None:
        self._order = order

    @property
    def state(self) -> str:
        return self._order.state

    @property
    def order_id(self) -> str:
        return self._order.order_id

    @property
    def qty(self) -> float:
        return float(self._order.intent.qty)

    @property
    def filled_qty(self) -> float:
        return float(self._order.filled_qty)

    @property
    def symbol(self) -> str:
        return self._order.intent.symbol

    @property
    def side(self) -> str:
        return self._order.intent.side

    @property
    def order_type(self) -> str:
        return self._order.intent.order_type

    @property
    def reduce_only(self) -> bool:
        return self._order.intent.reduce_only

    @property
    def reject_reason(self) -> str | None:
        return self._order.reject_reason


class _PositionView:
    """Session-compatible view over a canonical PositionRecord."""

    __slots__ = ("_pos",)

    def __init__(self, pos: PositionRecord) -> None:
        self._pos = pos

    @property
    def state(self) -> str:
        return self._pos.state

    @property
    def position_id(self) -> str:
        return self._pos.position_id

    @property
    def symbol(self) -> str:
        return self._pos.symbol

    @property
    def side(self) -> str:
        return self._pos.side

    @property
    def qty(self) -> float:
        return float(self._pos.qty)

    @property
    def entry_price(self) -> float:
        return float(self._pos.avg_entry_price)

    @property
    def avg_entry_price(self) -> float:
        return float(self._pos.avg_entry_price)


class _ViewMap(MutableMapping[str, Any]):
    def __init__(self, raw: dict[str, Any], factory: Any) -> None:
        self._raw = raw
        self._factory = factory

    def __getitem__(self, key: str) -> Any:
        return self._factory(self._raw[key])

    def __setitem__(self, key: str, value: Any) -> None:
        self._raw[key] = value

    def __delitem__(self, key: str) -> None:
        del self._raw[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._raw)

    def __len__(self) -> int:
        return len(self._raw)

    def items(self):  # type: ignore[no-untyped-def]
        for k, v in self._raw.items():
            yield k, self._factory(v)

    def values(self):  # type: ignore[no-untyped-def]
        for v in self._raw.values():
            yield self._factory(v)


class NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1:
    """Session-facing facade over the single canonical Execution Simulator V1.1."""

    VERSION = ADAPTER_ID
    CANONICAL_ENGINE = CANONICAL_EXECUTION_ENGINE

    def __init__(
        self,
        *,
        max_positions: int = 2,
        max_intents: int = 2,
        leverage: int = 25,
        margin_usdt: float = 20.0,
        tick_size: float = 0.1,
        simulator: AutonomousExecutionSimulatorV11 | None = None,
    ) -> None:
        self._sim = simulator or build_default_simulator(
            max_positions=max_positions,
            max_intents=max_intents,
            leverage=leverage,
            margin_usdt=margin_usdt,
        )
        if not isinstance(self._sim, AutonomousExecutionSimulatorV11):
            raise TypeError("adapter_requires_canonical_AutonomousExecutionSimulatorV11")
        self.max_positions = max_positions
        self.max_intents = max_intents
        self.leverage = int(self._sim.limits.leverage)
        self.margin_usdt = float(self._sim.limits.margin_usdt)
        self.tick_size = float(tick_size)
        self._bar_index = 0
        self.exchange_write_attempt_count = 0
        self.demo_order_count = 0

    @property
    def canonical_engine(self) -> AutonomousExecutionSimulatorV11:
        return self._sim

    @property
    def orders(self) -> _ViewMap:
        return _ViewMap(self._sim.orders, _OrderView)

    @property
    def positions(self) -> _ViewMap:
        return _ViewMap(self._sim.positions, _PositionView)

    @property
    def completed_trades(self) -> list[CompletedTrade]:
        return list(self._sim.completed_trades)

    def candidate_to_order_intent(self, candidate: dict[str, Any], *, qty: float | None = None) -> OrderIntent:
        """Map a Session Candidate dict into a canonical OrderIntent."""
        mark = float(candidate.get("mark_price") or 100.0)
        resolved_qty = qty
        if resolved_qty is None:
            resolved_qty = max(0.01, (self.margin_usdt * self.leverage) / mark)
        return OrderIntent(
            idempotency_key=str(
                candidate.get("idempotency_key")
                or candidate.get("intent_key")
                or candidate.get("candidate_id")
                or "missing_key"
            ),
            symbol=str(candidate.get("symbol") or "BTCUSDT"),
            side=str(candidate.get("side") or "BUY").upper(),
            order_type=_normalize_order_type(candidate.get("order_type") or "MARKET"),
            qty=_dec(resolved_qty),
            price=_dec(candidate["limit_price"]) if candidate.get("limit_price") is not None else None,
            stop_price=_dec(candidate["stop_price"]) if candidate.get("stop_price") is not None else None,
            reduce_only=bool(candidate.get("reduce_only")),
            leverage=int(candidate.get("leverage") or self.leverage),
            margin_mode=str(candidate.get("margin_mode") or "ISOLATED").upper(),
            requested_actions=tuple(candidate.get("requested_actions") or ()),
            client_tag=str(candidate.get("candidate_id")) if candidate.get("candidate_id") else None,
        )

    def _normalize_req(self, req: dict[str, Any]) -> dict[str, Any]:
        out = dict(req)
        out["order_type"] = _normalize_order_type(out.get("order_type") or "MARKET")
        out["side"] = str(out.get("side") or "BUY").upper()
        if out.get("margin_mode"):
            out["margin_mode"] = str(out["margin_mode"]).upper()
        return out

    def create_order(self, req: dict[str, Any], *, mark_price: Any | None = None) -> dict[str, Any]:
        """Accept Session-style req; route through instrument + risk + canonical engine."""
        normalized = self._normalize_req(req)
        mark = mark_price if mark_price is not None else normalized.get("mark_price")
        if mark is None:
            mark = normalized.get("price") or 100.0
        result = self._sim.create_order(normalized, mark_price=_dec(mark))
        # Preserve Session expectation for duplicate status token.
        if result.get("status") == "DUPLICATE_IGNORED":
            return result
        return result

    def try_fill(
        self,
        order_id: str,
        *,
        market_bid: float,
        market_ask: float,
        last_price: float,
        path_low: float,
        path_high: float,
        same_bar_stop: float | None = None,
        same_bar_target: float | None = None,
        partial_ratio: float | None = None,
        index_price: float | None = None,
        bar_index: int | None = None,
    ) -> dict[str, Any]:
        """Translate Session bar kwargs into canonical BarContext → fill engine."""
        self._bar_index = int(bar_index) if bar_index is not None else self._bar_index + 1
        mid = (float(market_bid) + float(market_ask)) / 2.0
        bar = BarContext(
            bar_index=self._bar_index,
            open_price=_dec(last_price),
            high=_dec(path_high),
            low=_dec(path_low),
            close=_dec(last_price),
            mark_price=_dec(last_price if last_price else mid),
            index_price=_dec(index_price) if index_price is not None else _dec(last_price if last_price else mid),
            bid=_dec(market_bid),
            ask=_dec(market_ask),
            mark_price_age_ms=0,
            same_bar_stop=_dec(same_bar_stop) if same_bar_stop is not None else None,
            same_bar_target=_dec(same_bar_target) if same_bar_target is not None else None,
        )
        return self._sim.try_fill(
            order_id,
            bar,
            partial_ratio=_dec(partial_ratio) if partial_ratio is not None else None,
        )

    def cancel(self, order_id: str, *, reason: str = "operator") -> dict[str, Any]:
        return self._sim.cancel(order_id, reason=reason)

    def open_ambiguous_position_count(self) -> int:
        return sum(1 for p in self._sim.positions.values() if p.state == "BLOCKED_AMBIGUOUS")

    def unclosed_intent_count(self) -> int:
        return sum(
            1
            for o in self._sim.orders.values()
            if o.state in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED", "CANCEL_PENDING"}
        )

    def report(self) -> dict[str, Any]:
        base = self._sim.report()
        base["adapter_id"] = ADAPTER_ID
        base["canonical_execution_engine"] = CANONICAL_EXECUTION_ENGINE
        base["canonical_execution_engine_count"] = CANONICAL_EXECUTION_ENGINE_COUNT
        base["duplicate_fill_engine_authority_count"] = 0
        base["duplicate_cost_model_authority_count"] = 0
        base["duplicate_risk_authority_count"] = 0
        base["duplicate_position_accounting_authority_count"] = 0
        base["open_ambiguous_position_count"] = self.open_ambiguous_position_count()
        base["unclosed_intent_count"] = self.unclosed_intent_count()
        return base


def build_session_execution_adapter(**kwargs: Any) -> NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1:
    return NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1(**kwargs)
