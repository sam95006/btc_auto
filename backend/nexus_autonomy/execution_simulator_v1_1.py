"""COMPATIBILITY ADAPTER ONLY — not an independent execution authority.

Canonical execution engine (exactly one):
  ``backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11``

Session / cross-lane traffic MUST use:
  ``backend.nexus_execution.orchestrator_adapter_v1.NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1``

This module remains for legacy unit tests and historical readiness artifacts.
It may only translate, adapt, and validate. It must NOT independently:

  * fill orders
  * calculate costs
  * apply risk decisions
  * update position quantity
  * decide same-bar stop/target outcomes

All of the above are delegated to the canonical engine. CI authority traps
(``tools/architecture/ci_gate_execution_shim_authority.py``) fail if fill /
cost / risk / position authority logic is re-introduced here.

HISTORICAL_REPLAY_SIMULATED_NO_EXCHANGE_WRITE only.
Never instantiates an authenticated exchange-write client.
No exchange write methods exist on this path.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from backend.nexus_autonomy.execution_models_v1_1 import FILL_POLICY_DOC, InstrumentSpec
from backend.nexus_execution.contracts import InstrumentSpec as CanonicalInstrumentSpec
from backend.nexus_execution.execution_simulator_v1_1 import AutonomousExecutionSimulatorV11
from backend.nexus_execution.orchestrator_adapter_v1 import (
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
    NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1,
)
from backend.nexus_execution.risk_gates import (
    FORBIDDEN_ACTIONS,
    FORBIDDEN_LEVERAGE_VALUES,
    MAX_LEVERAGE_CEILING,
)

# Compat aliases — re-exported from canonical risk gates (not local authority).
FORBIDDEN_LEVERAGE = FORBIDDEN_LEVERAGE_VALUES
DEFAULT_LEVERAGE = 25
MARGIN_MODE = "ISOLATED"

CANONICAL_FILL_ENGINE = "backend.nexus_execution.fill_engine.try_fill"
CANONICAL_FILL_AUTHORITY_COUNT = 1


def _dec(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _to_canonical_instrument(spec: InstrumentSpec) -> CanonicalInstrumentSpec:
    status = str(spec.status or "TRADING").upper()
    if status == "HALT":
        status = "HALTED"
    return CanonicalInstrumentSpec(
        symbol=str(spec.symbol),
        tick_size=_dec(spec.tick_size),
        lot_size=_dec(spec.qty_step),
        min_notional=_dec(spec.min_notional),
        status=status if status in {"TRADING", "HALTED", "AUCTION_ONLY"} else "TRADING",
    )


class AutonomousExecutionSimulatorV1_1:
    """Thin translate/adapt/validate shim over AutonomousExecutionSimulatorV11."""

    VERSION = "NEXUS_AUTONOMOUS_EXECUTION_SIMULATOR_V1_1_SHIM"
    CANONICAL_ENGINE = CANONICAL_EXECUTION_ENGINE

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
        simulator: AutonomousExecutionSimulatorV11 | None = None,
    ) -> None:
        # Construction-time validation only — risk decisions stay in canonical gates.
        if leverage in FORBIDDEN_LEVERAGE or leverage > MAX_LEVERAGE_CEILING:
            raise ValueError("leverage_forbidden_or_exceeds_ceiling")
        if leverage <= 0:
            raise ValueError("leverage_invalid")

        self._tick_size = float(tick_size)
        self._qty_step = float(qty_step)
        self._min_notional = float(min_notional)
        self._maint_margin_rate = float(maint_margin_rate)
        self.now_ms = int(now_ms)
        self.default_instrument = InstrumentSpec(
            symbol="*",
            tick_size=self._tick_size,
            qty_step=self._qty_step,
            min_notional=self._min_notional,
            status=instrument_status,
            maint_margin_rate=self._maint_margin_rate,
            max_leverage=MAX_LEVERAGE_CEILING,
        )
        self._legacy_instruments: dict[str, InstrumentSpec] = {}

        self._adapter = NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1(
            max_positions=max_positions,
            max_intents=max_intents,
            leverage=leverage,
            margin_usdt=margin_usdt,
            tick_size=tick_size,
            simulator=simulator,
        )
        if not isinstance(self._adapter.canonical_engine, AutonomousExecutionSimulatorV11):
            raise TypeError("shim_requires_canonical_AutonomousExecutionSimulatorV11")

        self.max_positions = int(max_positions)
        self.max_intents = int(max_intents)
        self.leverage = int(self._adapter.leverage)
        self.margin_usdt = float(self._adapter.margin_usdt)
        self.tick_size = float(tick_size)
        self.qty_step = float(qty_step)
        self.min_notional = float(min_notional)
        self.maint_margin_rate = float(maint_margin_rate)
        self.exchange_write_attempt_count = 0
        self.demo_order_count = 0
        self.audit: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []

    # --- intentionally NO exchange write methods ---
    # place_order_on_exchange / submit_bybit / authenticated_write are forbidden and absent.

    @property
    def canonical_engine(self) -> AutonomousExecutionSimulatorV11:
        return self._adapter.canonical_engine

    @property
    def instruments(self) -> dict[str, InstrumentSpec]:
        return self._legacy_instruments

    @property
    def orders(self) -> Any:
        return self._adapter.orders

    @property
    def positions(self) -> Any:
        return self._adapter.positions

    @property
    def intent_owners(self) -> dict[str, str]:
        """Expose canonical intent map for mutation/red-team harnesses."""
        return self.canonical_engine.intent_owners

    @property
    def counts(self) -> dict[str, int]:
        c = self.canonical_engine.counters.as_dict()
        return {
            "order_created_count": c.get("order_created_count", 0),
            "partially_filled_count": c.get("partially_filled_count", 0),
            "filled_count": c.get("filled_count", 0),
            "cancelled_count": c.get("cancelled_count", 0),
            "rejected_count": c.get("rejected_count", 0),
            "expired_count": c.get("expired_count", 0),
            "replaced_count": c.get("cancel_replace_count", 0),
            "unfilled_count": c.get("unfilled_count", 0),
            "simulated_position_open_count": c.get("position_open_count", 0),
            "simulated_position_closed_count": c.get("position_closed_count", 0),
            "simulated_liquidation_count": c.get("simulated_liquidation_count", 0),
            "funding_events_count": c.get("funding_debit_count", 0) + c.get("funding_credit_count", 0),
        }

    def set_instrument(self, spec: InstrumentSpec) -> None:
        """Adapt legacy InstrumentSpec onto the canonical engine instrument table."""
        self._legacy_instruments[spec.symbol] = spec
        self.canonical_engine.instruments[spec.symbol] = _to_canonical_instrument(spec)

    def _ensure_instrument(self, symbol: str) -> None:
        """Adapt: register a tradable instrument when callers use ad-hoc symbols."""
        if symbol in self.canonical_engine.instruments:
            return
        legacy = self._legacy_instruments.get(symbol) or InstrumentSpec(
            symbol=symbol,
            tick_size=self._tick_size,
            qty_step=self._qty_step,
            min_notional=self._min_notional,
            status=self.default_instrument.status,
            maint_margin_rate=self._maint_margin_rate,
            max_leverage=MAX_LEVERAGE_CEILING,
        )
        self.set_instrument(legacy)

    def advance_time(self, delta_ms: int) -> None:
        """Validate-only time cursor for legacy callers (no fill authority)."""
        self.now_ms += int(delta_ms)

    def create_order(self, req: dict[str, Any]) -> dict[str, Any]:
        """Translate legacy req → canonical adapter create_order (no local risk fill)."""
        symbol = str(req.get("symbol") or "BTCUSDT")
        self._ensure_instrument(symbol)
        normalized = dict(req)
        normalized.setdefault("order_type", "market")
        result = self._adapter.create_order(normalized)
        self.audit.append(
            {
                "event": "CREATE_ORDER_DELEGATED",
                "status": result.get("status"),
                "order_id": result.get("order_id"),
                "ts_ms": self.now_ms,
                "canonical_engine": CANONICAL_EXECUTION_ENGINE,
            }
        )
        return result

    def cancel(self, order_id: str) -> dict[str, Any]:
        return self._adapter.cancel(order_id)

    def replace_order(self, order_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Translate cancel-replace into canonical cancel_replace (no local risk)."""
        order_view = self.orders[order_id]
        remaining = float(order_view.qty) - float(order_view.filled_qty)
        old_key = None
        for k, oid in list(self.intent_owners.items()):
            if oid == order_id:
                old_key = k
                break
        new_key = str(patch.get("idempotency_key") or f"{old_key or order_id}|replace|{self.now_ms}")
        mark = patch.get("mark_price")
        if mark is None:
            mark = patch.get("price") or order_view.avg_fill_price or 100.0
        req = {
            "idempotency_key": new_key,
            "symbol": order_view.symbol,
            "side": order_view.side,
            "order_type": patch.get("order_type", order_view.order_type),
            "qty": float(patch.get("qty", remaining)),
            "price": patch.get("price"),
            "stop_price": patch.get("stop_price"),
            "reduce_only": order_view.reduce_only,
            "margin_mode": MARGIN_MODE,
            "leverage": self.leverage,
            "time_in_force": patch.get("time_in_force", "GTC"),
            "mark_price": mark,
            "index_price": patch.get("index_price"),
        }
        self._ensure_instrument(str(req["symbol"]))
        created = self.canonical_engine.cancel_replace(order_id, req, mark_price=_dec(mark))
        return {"status": "REPLACED", "old_order_id": order_id, "new": created}

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
        """Translate legacy bar kwargs → canonical fill engine via adapter.

        Keywords ``opposite_volume`` / ``latency_adverse_bps`` / ``now_ms`` are
        accepted for API compatibility and ignored at the translation layer —
        fill / same-bar / cost / position authority lives only in the canonical
        engine.
        """
        _ = (opposite_volume, latency_adverse_bps)
        if now_ms is not None:
            self.now_ms = int(now_ms)

        # Adapt mark into last_price when callers supply mark without last.
        effective_last = float(last_price if last_price is not None else (mark_price or 0.0))
        if mark_price is not None and last_price == 0:
            effective_last = float(mark_price)

        result = self._adapter.try_fill(
            order_id,
            market_bid=float(market_bid),
            market_ask=float(market_ask),
            last_price=effective_last,
            path_low=float(path_low),
            path_high=float(path_high),
            same_bar_stop=same_bar_stop,
            same_bar_target=same_bar_target,
            partial_ratio=partial_ratio,
            index_price=index_price if index_price is not None else mark_price,
        )

        # Observe canonical outcomes for legacy trade list (no independent accounting).
        if result.get("status") in {"FILLED", "PARTIALLY_FILLED", "PARTIALLY_FILLED_IOC_CANCELLED"}:
            observed_qty = result.get("fill_qty") or result.get("filled_qty")
            observed_px = result.get("fill_price")
            if observed_qty is not None and observed_px is not None:
                self.trades.append(
                    {
                        "order_id": order_id,
                        "qty": float(observed_qty),
                        "price": float(observed_px),
                        "source": "canonical_delegate",
                    }
                )
            elif result.get("fills"):
                for f in result["fills"]:
                    self.trades.append(
                        {
                            "order_id": order_id,
                            "qty": float(f.get("qty") or 0),
                            "price": float(f.get("price") or 0),
                            "source": "canonical_delegate",
                        }
                    )

        self.audit.append(
            {
                "event": "TRY_FILL_DELEGATED",
                "order_id": order_id,
                "status": result.get("status"),
                "ts_ms": self.now_ms,
                "canonical_fill_engine": CANONICAL_FILL_ENGINE,
            }
        )
        return result

    def open_ambiguous_position_count(self) -> int:
        return self._adapter.open_ambiguous_position_count()

    def unclosed_intent_count(self) -> int:
        return self._adapter.unclosed_intent_count()

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
        base = self._adapter.report()
        base.update(
            {
                "version": self.VERSION,
                "shim_role": "translate_adapt_validate_only",
                "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
                "canonical_execution_engine_count": CANONICAL_EXECUTION_ENGINE_COUNT,
                "canonical_fill_engine": CANONICAL_FILL_ENGINE,
                "canonical_fill_authority_count": CANONICAL_FILL_AUTHORITY_COUNT,
                "shim_embedded_fill_authority_count": 0,
                "shim_embedded_cost_authority_count": 0,
                "shim_embedded_risk_authority_count": 0,
                "shim_embedded_position_authority_count": 0,
                "fill_policy": FILL_POLICY_DOC,
                "exchange_write_attempt_count": self.exchange_write_attempt_count,
                "demo_order_count": self.demo_order_count,
                "trade_count": len(self.trades),
                **self.counts,
            }
        )
        return base


# Alias for importers
ExecutionSimulatorV1_1 = AutonomousExecutionSimulatorV1_1

__all__ = [
    "AutonomousExecutionSimulatorV1_1",
    "CANONICAL_EXECUTION_ENGINE",
    "CANONICAL_EXECUTION_ENGINE_COUNT",
    "CANONICAL_FILL_AUTHORITY_COUNT",
    "CANONICAL_FILL_ENGINE",
    "DEFAULT_LEVERAGE",
    "ExecutionSimulatorV1_1",
    "FORBIDDEN_ACTIONS",
    "FORBIDDEN_LEVERAGE",
    "MARGIN_MODE",
    "MAX_LEVERAGE_CEILING",
]
