"""Security boundary for the V1.1 execution simulator.

Guarantees:
    * No module in ``backend.nexus_execution`` may instantiate an authenticated
      exchange-write client.
    * Any attempt to call a network write method (create_order, place_order,
      cancel_order, ...) on a monkey-patched client raises
      :class:`ExchangeWriteAttempted` and bumps the module-level counter.
    * Callers can obtain the current attempt count via
      :func:`exchange_write_attempt_count`.

The simulator does not import ``ccxt`` at runtime. The trap installer only
patches classes that the caller explicitly hands it, so importing this module
by itself has zero side effects.
"""
from __future__ import annotations

from typing import Any, Iterable

EXECUTION_MODE = "SIMULATED_NO_EXCHANGE_WRITE"
"""Fixed banner recorded in every readiness artifact."""

_ATTEMPT_COUNT = 0
_DEMO_ORDER_COUNT = 0
_MAINNET = False
_REAL_MONEY = False


class ExchangeWriteAttempted(RuntimeError):
    """Raised when a simulator code path tries to touch a live exchange."""


def record_exchange_write_attempt(method: str, *, source: str = "unknown") -> None:
    """Increment the attempt counter and raise ``ExchangeWriteAttempted``.

    ``method`` and ``source`` are captured in the exception message so the
    failing test can point at the offending call site.
    """
    global _ATTEMPT_COUNT
    _ATTEMPT_COUNT += 1
    raise ExchangeWriteAttempted(
        f"exchange_write_attempt method={method} source={source} mode={EXECUTION_MODE}"
    )


def exchange_write_attempt_count() -> int:
    return _ATTEMPT_COUNT


def demo_order_count() -> int:
    return _DEMO_ORDER_COUNT


def is_mainnet() -> bool:
    return _MAINNET


def is_real_money() -> bool:
    return _REAL_MONEY


def reset_counters() -> None:
    """Reset counters. Intended for test setup only."""
    global _ATTEMPT_COUNT, _DEMO_ORDER_COUNT
    _ATTEMPT_COUNT = 0
    _DEMO_ORDER_COUNT = 0


def assert_no_exchange_write() -> None:
    if _ATTEMPT_COUNT != 0:
        raise ExchangeWriteAttempted(
            f"exchange_write_attempt_count={_ATTEMPT_COUNT} mode={EXECUTION_MODE}"
        )
    if _DEMO_ORDER_COUNT != 0:
        raise ExchangeWriteAttempted(
            f"demo_order_count={_DEMO_ORDER_COUNT} mode={EXECUTION_MODE}"
        )
    if _MAINNET:
        raise ExchangeWriteAttempted("mainnet flag set unexpectedly")
    if _REAL_MONEY:
        raise ExchangeWriteAttempted("real_money flag set unexpectedly")


# Method names that must never execute on any exchange client during simulation.
FORBIDDEN_WRITE_METHODS: tuple[str, ...] = (
    "create_order",
    "place_order",
    "create_market_order",
    "create_limit_order",
    "create_stop_order",
    "create_stop_market_order",
    "create_take_profit_order",
    "cancel_order",
    "cancel_all_orders",
    "edit_order",
    "amend_order",
    "modify_order",
    "set_leverage",
    "set_margin_mode",
    "set_position_mode",
    "transfer",
    "withdraw",
    "deposit",
    "borrow",
    "repay",
    "add_margin",
    "reduce_margin",
    "close_position",
    "close_all_positions",
)


def install_exchange_write_traps(clients: Iterable[Any]) -> int:
    """Monkey-patch ``FORBIDDEN_WRITE_METHODS`` on each provided client.

    Each patched method raises :class:`ExchangeWriteAttempted` and bumps the
    counter when invoked. Returns the number of methods trapped.

    Intended to be used from tests like::

        client = SomeExchangeClient()  # never authenticated
        install_exchange_write_traps([client])

    Because :class:`AutonomousExecutionSimulatorV11` does not import any
    exchange SDK, tests can also invoke this on freshly-created stubs.
    """
    trapped = 0
    for client in clients:
        for name in FORBIDDEN_WRITE_METHODS:
            if hasattr(client, name):
                def _trap(*_a: Any, _method: str = name, _client: Any = client, **_kw: Any) -> Any:
                    record_exchange_write_attempt(_method, source=type(_client).__name__)
                try:
                    setattr(client, name, _trap)
                    trapped += 1
                except (AttributeError, TypeError):  # pragma: no cover - hardened C types
                    continue
    return trapped
