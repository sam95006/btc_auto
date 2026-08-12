"""Bybit Demo account reader — never invent balances."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_demo_execution.capital_constitution import (
    BalanceSource,
    CapitalConstitution,
    CapitalConstitutionError,
)


class AccountReaderError(RuntimeError):
    """Raised when account data cannot be read or is invalid."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


@dataclass
class DemoAccountSnapshot:
    wallet_balance: float
    equity: float
    available_balance: float
    margin_balance: float
    used_margin: float
    unrealized_pnl: float
    realized_pnl: float
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    open_orders: list[dict[str, Any]] = field(default_factory=list)
    source: str = BalanceSource.BYBIT_DEMO_PRIVATE_API.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "wallet_balance": self.wallet_balance,
            "equity": self.equity,
            "available_balance": self.available_balance,
            "margin_balance": self.margin_balance,
            "used_margin": self.used_margin,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "open_positions": list(self.open_positions),
            "open_orders": list(self.open_orders),
            "source": self.source,
        }


class BybitDemoAccountReader(ABC):
    """Interface for reading real Bybit Demo account state."""

    @abstractmethod
    def read_snapshot(self) -> DemoAccountSnapshot:
        """Fetch current account snapshot from Bybit Demo private API."""

    def read_with_constitution(
        self,
        constitution: CapitalConstitution | None = None,
    ) -> DemoAccountSnapshot:
        constitution = constitution or CapitalConstitution()
        constitution.validate()
        snap = self.read_snapshot()
        if snap.source != BalanceSource.BYBIT_DEMO_PRIVATE_API.value:
            raise AccountReaderError("invalid_balance_source", snap.source)
        constitution.assert_balance_from_api(
            snap.wallet_balance,
            api_source=BalanceSource.BYBIT_DEMO_PRIVATE_API.value,
        )
        constitution.reject_virtual_balance({"wallet_balance": snap.wallet_balance})
        if constitution.violations:
            raise CapitalConstitutionError(
                "account_snapshot_rejected",
                ";".join(constitution.violations),
            )
        return snap


@dataclass
class FakeDemoAccountReader(BybitDemoAccountReader):
    """Test double — values must be explicitly injected; never invents defaults."""

    _snapshot: DemoAccountSnapshot | None = None
    _error: AccountReaderError | None = None

    def set_snapshot(self, snapshot: DemoAccountSnapshot) -> None:
        self._snapshot = snapshot
        self._error = None

    def set_error(self, error: AccountReaderError) -> None:
        self._error = error
        self._snapshot = None

    def read_snapshot(self) -> DemoAccountSnapshot:
        if self._error is not None:
            raise self._error
        if self._snapshot is None:
            raise AccountReaderError("no_snapshot_configured")
        return self._snapshot
