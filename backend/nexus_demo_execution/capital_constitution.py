"""Capital constitution — real Bybit Demo balance only; no virtual ledger."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_demo_execution import BYBIT_DEMO, MAINNET, REAL_MONEY


class CapitalSource(str, Enum):
    BYBIT_DEMO_ACCOUNT = "BYBIT_DEMO_ACCOUNT"


class BalanceSource(str, Enum):
    BYBIT_DEMO_PRIVATE_API = "BYBIT_DEMO_PRIVATE_API"


class AllocationSource(str, Enum):
    AVAILABLE_BALANCE = "AVAILABLE_BALANCE"


class CapitalConstitutionError(RuntimeError):
    """Raised when capital policy is violated."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


FORBIDDEN_VIRTUAL_BALANCE_MARKERS = frozenset(
    {
        "virtual_balance",
        "fake_balance",
        "paper_balance",
        "hardcoded_5000",
        "5000U",
        "5000.0",
    }
)

HARDCODED_5000U = 5000.0


@dataclass
class CapitalConstitution:
    """Enforces DEMO-only capital sourcing without internal fake balances."""

    capital_source: CapitalSource = CapitalSource.BYBIT_DEMO_ACCOUNT
    balance_source: BalanceSource = BalanceSource.BYBIT_DEMO_PRIVATE_API
    allocation_source: AllocationSource = AllocationSource.AVAILABLE_BALANCE
    internal_fake_balance: bool = False
    automatic_fund_reset: bool = False
    founder_manual_reset_only: bool = True

    violations: list[str] = field(default_factory=list)

    def validate(self) -> None:
        self.violations.clear()
        if not BYBIT_DEMO:
            self._reject("bybit_demo_required")
        if MAINNET or REAL_MONEY:
            self._reject("mainnet_or_real_money_forbidden")
        if self.capital_source != CapitalSource.BYBIT_DEMO_ACCOUNT:
            self._reject("invalid_capital_source", self.capital_source.value)
        if self.balance_source != BalanceSource.BYBIT_DEMO_PRIVATE_API:
            self._reject("invalid_balance_source", self.balance_source.value)
        if self.allocation_source != AllocationSource.AVAILABLE_BALANCE:
            self._reject("invalid_allocation_source", self.allocation_source.value)
        if self.internal_fake_balance:
            self._reject("internal_fake_balance_forbidden")
        if self.automatic_fund_reset:
            self._reject("automatic_fund_reset_forbidden")
        if not self.founder_manual_reset_only:
            self._reject("founder_manual_reset_only_required")
        if self.violations:
            raise CapitalConstitutionError(
                "capital_constitution_failed",
                ";".join(self.violations),
            )

    def reject_virtual_balance(self, payload: dict[str, Any] | None) -> None:
        if payload is None:
            return
        for key, value in payload.items():
            key_l = str(key).lower()
            if key_l in FORBIDDEN_VIRTUAL_BALANCE_MARKERS:
                self._reject("virtual_balance_key", key_l)
            if key_l == "virtual_balance" and value:
                self._reject("virtual_balance_true")
            val_s = str(value).lower()
            for marker in FORBIDDEN_VIRTUAL_BALANCE_MARKERS:
                if marker in val_s:
                    self._reject("virtual_balance_marker", marker)

    def reject_hardcoded_balance(self, balance: float | None, *, source: str = "") -> None:
        if balance is None:
            return
        if abs(balance - HARDCODED_5000U) < 0.01 and source != "bybit_demo_private_api":
            self._reject("hardcoded_5000u_rejected", source or "unknown")
        if self.violations:
            raise CapitalConstitutionError(
                "hardcoded_balance_rejected",
                ";".join(self.violations),
            )

    def assert_balance_from_api(self, balance: float, *, api_source: str) -> None:
        self.reject_hardcoded_balance(balance, source=api_source)
        if api_source != BalanceSource.BYBIT_DEMO_PRIVATE_API.value:
            self._reject("balance_not_from_demo_api", api_source)
        if self.violations:
            raise CapitalConstitutionError(
                "balance_source_rejected",
                ";".join(self.violations),
            )

    def _reject(self, code: str, detail: str = "") -> None:
        msg = f"{code}:{detail}" if detail else code
        self.violations.append(msg)

    def snapshot(self) -> dict[str, Any]:
        return {
            "capital_source": self.capital_source.value,
            "balance_source": self.balance_source.value,
            "allocation_source": self.allocation_source.value,
            "internal_fake_balance": self.internal_fake_balance,
            "automatic_fund_reset": self.automatic_fund_reset,
            "founder_manual_reset_only": self.founder_manual_reset_only,
            "bybit_demo": BYBIT_DEMO,
            "mainnet": MAINNET,
            "real_money": REAL_MONEY,
            "valid": len(self.violations) == 0,
        }
