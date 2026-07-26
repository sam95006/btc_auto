"""Phase 6.6 — Demo ledger reconciliation foundation (fail-closed, no forced equality)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_research.demo_exchange.constants import (
    ACCOUNT_BYBIT_DEMO,
    ACCOUNT_PAPER_MAIN_V1,
)
from backend.nexus_research.demo_exchange.identity import AccountBoundary
from backend.nexus_research.demo_exchange.readers import DemoExchangeSnapshot


class MismatchReason(str, Enum):
    NONE = "NONE"
    ACCOUNT_IDENTITY = "ACCOUNT_IDENTITY"
    SYMBOL = "SYMBOL"
    SIDE = "SIDE"
    QUANTITY = "QUANTITY"
    AVERAGE_PRICE = "AVERAGE_PRICE"
    REALIZED_PNL = "REALIZED_PNL"
    ORDER_STATE = "ORDER_STATE"
    WALLET = "WALLET"
    AVAILABLE_BALANCE = "AVAILABLE_BALANCE"
    POSITION = "POSITION"
    OPEN_ORDER = "OPEN_ORDER"
    EXECUTION = "EXECUTION"
    TIMESTAMP = "TIMESTAMP"
    CROSS_ACCOUNT_COMPARE_FORBIDDEN = "CROSS_ACCOUNT_COMPARE_FORBIDDEN"


@dataclass
class ReconciliationResult:
    ok: bool
    status: str  # MATCH | MISMATCH | SKIPPED_CROSS_ACCOUNT | FAIL_CLOSED
    reasons: list[MismatchReason] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    execution_write_allowed: bool = False
    reconciliation_status: str = "OK"
    paper_account_id: str = ACCOUNT_PAPER_MAIN_V1
    demo_account_id: str = ACCOUNT_BYBIT_DEMO
    balances_forced_equal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "reasons": [r.value for r in self.reasons],
            "details": list(self.details),
            "execution_write_allowed": self.execution_write_allowed,
            "reconciliation_status": self.reconciliation_status,
            "paperAccountId": self.paper_account_id,
            "demoAccountId": self.demo_account_id,
            "balancesForcedEqual": self.balances_forced_equal,
        }


class FailClosedMismatchPolicy:
    """On mismatch: lock writes and mark FAIL_CLOSED."""

    def apply(self, result: ReconciliationResult) -> ReconciliationResult:
        if result.ok and result.status in {"MATCH", "SKIPPED_CROSS_ACCOUNT"}:
            result.execution_write_allowed = False  # Phase 6.6 remains read-only always
            result.reconciliation_status = "OK" if result.ok else "FAIL_CLOSED"
            return result
        result.ok = False
        result.execution_write_allowed = False
        result.reconciliation_status = "FAIL_CLOSED"
        if result.status != "FAIL_CLOSED":
            result.status = "MISMATCH"
        return result


class DemoLedgerReconciler:
    """Compare demo snapshot fields for internal consistency.

    Does NOT force paper balance == demo balance. Cross-account numeric
    equality is explicitly forbidden / skipped.
    """

    def __init__(
        self,
        boundary: AccountBoundary | None = None,
        policy: FailClosedMismatchPolicy | None = None,
    ) -> None:
        self.boundary = boundary or AccountBoundary()
        self.policy = policy or FailClosedMismatchPolicy()

    def reconcile_demo_internal(
        self,
        snapshot: DemoExchangeSnapshot,
        *,
        expected_symbols: set[str] | None = None,
    ) -> ReconciliationResult:
        reasons: list[MismatchReason] = []
        details: list[str] = []

        try:
            self.boundary.assert_demo_identity(snapshot.identity.account_id)
        except Exception as exc:  # noqa: BLE001
            reasons.append(MismatchReason.ACCOUNT_IDENTITY)
            details.append(str(exc))

        if snapshot.wallet is None:
            reasons.append(MismatchReason.WALLET)
            details.append("wallet_missing")

        for pos in snapshot.positions:
            if expected_symbols and pos.symbol and pos.symbol not in expected_symbols:
                reasons.append(MismatchReason.SYMBOL)
                details.append(f"unexpected_symbol:{pos.symbol}")
            if pos.size < 0:
                reasons.append(MismatchReason.QUANTITY)
                details.append(f"negative_size:{pos.symbol}")

        # Duplicate order ids within open orders
        seen_orders: set[str] = set()
        for o in snapshot.open_orders:
            if o.order_id and o.order_id in seen_orders:
                reasons.append(MismatchReason.ORDER_STATE)
                details.append(f"duplicated_order_record:{o.order_id}")
            seen_orders.add(o.order_id)

        seen_exec: set[str] = set()
        for e in snapshot.executions:
            if e.exec_id and e.exec_id in seen_exec:
                reasons.append(MismatchReason.EXECUTION)
                details.append(f"duplicate_execution:{e.exec_id}")
            seen_exec.add(e.exec_id)

        ok = not reasons
        result = ReconciliationResult(
            ok=ok,
            status="MATCH" if ok else "MISMATCH",
            reasons=reasons,
            details=details,
            execution_write_allowed=False,
        )
        return self.policy.apply(result)

    def compare_paper_vs_demo_balances(
        self,
        *,
        paper_balance: float,
        demo_balance: float,
    ) -> ReconciliationResult:
        """Explicitly refuse to force equality across independent accounts."""
        _ = (paper_balance, demo_balance)  # intentionally unused for equality
        result = ReconciliationResult(
            ok=True,
            status="SKIPPED_CROSS_ACCOUNT",
            reasons=[MismatchReason.CROSS_ACCOUNT_COMPARE_FORBIDDEN],
            details=[
                "paper_and_demo_are_independent_accounts",
                "balances_not_forced_equal",
            ],
            execution_write_allowed=False,
            balances_forced_equal=False,
        )
        # Not a mismatch — skip is OK; still write-locked for Phase 6.6
        result.reconciliation_status = "OK"
        return result

    def on_mismatch_lock(self, result: ReconciliationResult) -> ReconciliationResult:
        return self.policy.apply(result)
