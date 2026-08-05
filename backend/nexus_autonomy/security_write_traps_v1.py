"""Runtime monkeypatch traps for exchange write / mutation methods."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator
from unittest.mock import patch

from backend.nexus_autonomy.security_constants_v1 import EXCHANGE_WRITE_METHODS, WRITE_PATH_FRAGMENTS
from backend.nexus_autonomy.security_exceptions_v1 import ExchangeWriteForbidden


@dataclass
class WriteAttemptCounters:
    exchange_write_attempt_count: int = 0
    order_write_attempt_count: int = 0
    position_mutation_attempt_count: int = 0
    transfer_attempt_count: int = 0
    withdrawal_attempt_count: int = 0
    mainnet_client_created_count: int = 0
    trapped_methods: list[str] = field(default_factory=list)

    ORDER_METHODS = frozenset(
        {
            "create_order",
            "create_market_order",
            "amend_order",
            "cancel_order",
            "cancel_all",
            "cancel_all_orders",
            "place_order",
            "submit_order",
            "close_reduce_only",
        }
    )
    POSITION_METHODS = frozenset(
        {
            "set_leverage",
            "switch_margin_mode",
            "set_trading_stop",
        }
    )
    TRANSFER_METHODS = frozenset(
        {
            "transfer",
            "internal_transfer",
            "subaccount_transfer",
        }
    )
    WITHDRAW_METHODS = frozenset({"withdraw"})

    def record(self, method: str) -> None:
        self.exchange_write_attempt_count += 1
        self.trapped_methods.append(method)
        if method in self.ORDER_METHODS:
            self.order_write_attempt_count += 1
        if method in self.POSITION_METHODS:
            self.position_mutation_attempt_count += 1
        if method in self.TRANSFER_METHODS:
            self.transfer_attempt_count += 1
        if method in self.WITHDRAW_METHODS:
            self.withdrawal_attempt_count += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
            "order_write_attempt_count": self.order_write_attempt_count,
            "position_mutation_attempt_count": self.position_mutation_attempt_count,
            "transfer_attempt_count": self.transfer_attempt_count,
            "withdrawal_attempt_count": self.withdrawal_attempt_count,
            "mainnet_client_created_count": self.mainnet_client_created_count,
            "trapped_methods": list(self.trapped_methods),
        }

    def assert_zero(self) -> None:
        if self.exchange_write_attempt_count or self.withdrawal_attempt_count or self.transfer_attempt_count:
            raise AssertionError(f"write_attempts_nonzero:{self.to_dict()}")


def _make_trap(counters: WriteAttemptCounters, method: str) -> Callable[..., Any]:
    def _trap(*_a: Any, **_kw: Any) -> Any:
        counters.record(method)
        raise ExchangeWriteForbidden(method)

    _trap.__name__ = f"trap_{method}"
    return _trap


def discover_write_targets() -> list[tuple[str, str]]:
    """Return (dotted_path, method) pairs for known write-capable clients."""
    targets: list[tuple[str, str]] = []
    client_paths = (
        "backend.nexus_demo_execution.demo_write_client.DemoWriteClient",
    )
    methods = sorted(EXCHANGE_WRITE_METHODS | {"_post"})
    for base in client_paths:
        for method in methods:
            targets.append((f"{base}.{method}", method if method != "_post" else "_post"))
    # Standalone stubs often used in tests / adapters
    for method in sorted(EXCHANGE_WRITE_METHODS):
        targets.append((f"builtins.__dict__.{method}", method))  # placeholder; filtered at install
    return [(p, m) for p, m in targets if not p.startswith("builtins")]


class WriteTrapRegistry:
    """Install patches that raise EXCHANGE_WRITE_FORBIDDEN on write methods."""

    def __init__(self) -> None:
        self.counters = WriteAttemptCounters()
        self._patches: list[Any] = []
        self.write_method_trap_count = 0
        self.authenticated_write_method_count = 0
        self.install_ok = False

    def install(self) -> WriteAttemptCounters:
        self.uninstall()
        self.counters = WriteAttemptCounters()
        self.install_ok = False
        # Patch DemoWriteClient methods that exist.
        try:
            from backend.nexus_demo_execution import demo_write_client as dwc

            client = dwc.DemoWriteClient
            for method in sorted(EXCHANGE_WRITE_METHODS | {"_post"}):
                if hasattr(client, method):
                    self.authenticated_write_method_count += 1
                    trap = _make_trap(
                        self.counters,
                        method if method != "_post" else "create_order",
                    )
                    p = patch.object(client, method, trap)
                    p.start()
                    self._patches.append(p)
                    self.write_method_trap_count += 1
        except Exception:  # noqa: BLE001 — trap install must not crash audit
            pass

        # Also patch module-level helpers if present on write_adapter / transport.
        for mod_path, attr in (
            ("backend.nexus_research.demo_autonomous.write_adapter", "create_order"),
            ("backend.nexus_research.demo_autonomous.write_adapter", "cancel_order"),
            ("backend.nexus_research.demo_autonomous.write_transport", "post_signed"),
        ):
            try:
                p = patch(f"{mod_path}.{attr}", _make_trap(self.counters, attr))
                p.start()
                self._patches.append(p)
                self.write_method_trap_count += 1
                self.authenticated_write_method_count += 1
            except Exception:  # noqa: BLE001
                continue

        armed = self.write_method_trap_count > 0 or len(self._patches) > 0
        self.install_ok = armed
        # Fail-closed: never claim a successful arming when nothing was patched.
        # (AST noop mutants that `return True` skip this path and are detect-killed.)
        if not armed:
            raise ExchangeWriteForbidden("write_trap_install_unarmed")
        return self.counters

    def uninstall(self) -> None:
        for p in reversed(self._patches):
            try:
                p.stop()
            except RuntimeError:
                pass
        self._patches.clear()

    def trap_callable(self, method: str) -> Callable[..., Any]:
        return _make_trap(self.counters, method)


@contextmanager
def exchange_write_traps() -> Iterator[WriteAttemptCounters]:
    registry = WriteTrapRegistry()
    counters = registry.install()
    try:
        yield counters
    finally:
        registry.uninstall()


def path_is_exchange_write(url_or_path: str) -> bool:
    lowered = (url_or_path or "").lower()
    return any(frag in lowered for frag in WRITE_PATH_FRAGMENTS)
