"""Phase 6.6 — Account boundary: PAPER vs BYBIT_DEMO never mixed."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_exchange.constants import (
    ACCOUNT_BYBIT_DEMO,
    ACCOUNT_PAPER_MAIN_V1,
)
from backend.nexus_research.demo_exchange.errors import AccountIdentityMismatchError


@dataclass(frozen=True)
class ExchangeAccountIdentity:
    account_id: str
    venue: str
    kind: str  # paper | bybit_demo

    def assert_not_mixed_with(self, other: "ExchangeAccountIdentity") -> None:
        if self.account_id == other.account_id and self.kind != other.kind:
            raise AccountIdentityMismatchError("identity_kind_conflict")
        if self.account_id != other.account_id and self.kind == other.kind == "bybit_demo":
            # same kind different ids ok for multi-demo future; paper/demo must differ
            pass
        if {self.kind, other.kind} == {"paper", "bybit_demo"}:
            if self.account_id == other.account_id:
                raise AccountIdentityMismatchError("paper_demo_id_collision")


@dataclass
class DemoSnapshotIdentity:
    account_id: str = ACCOUNT_BYBIT_DEMO
    venue: str = "bybit_demo"
    snapshot_id: str = ""
    captured_at_ms: int = 0
    source: str = "demo_readonly"

    def __post_init__(self) -> None:
        if not self.captured_at_ms:
            self.captured_at_ms = int(time.time() * 1000)
        if not self.snapshot_id:
            raw = f"{self.account_id}:{self.captured_at_ms}:{self.source}"
            self.snapshot_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accountId": self.account_id,
            "venue": self.venue,
            "snapshotId": self.snapshot_id,
            "capturedAtMs": self.captured_at_ms,
            "source": self.source,
        }


class AccountBoundary:
    """Hard separation: NEXUS_PAPER_MAIN_V1 ≠ BYBIT_DEMO_ACCOUNT."""

    PAPER = ExchangeAccountIdentity(
        account_id=ACCOUNT_PAPER_MAIN_V1,
        venue="nexus_internal",
        kind="paper",
    )
    DEMO = ExchangeAccountIdentity(
        account_id=ACCOUNT_BYBIT_DEMO,
        venue="bybit_demo",
        kind="bybit_demo",
    )

    FORBIDDEN_ACTIONS = frozenset(
        {
            "treat_paper_10000_as_demo_balance",
            "write_demo_execution_into_paper_ledger",
            "treat_paper_position_as_demo_position",
            "auto_sync_assets",
            "auto_create_hedge",
        }
    )

    def __init__(self) -> None:
        self.PAPER.assert_not_mixed_with(self.DEMO)
        if self.PAPER.account_id == self.DEMO.account_id:
            raise AccountIdentityMismatchError("account_ids_must_differ")

    def assert_demo_identity(self, account_id: str) -> None:
        if account_id != ACCOUNT_BYBIT_DEMO:
            raise AccountIdentityMismatchError(f"expected_demo_account:{account_id}")

    def assert_paper_identity(self, account_id: str) -> None:
        if account_id != ACCOUNT_PAPER_MAIN_V1:
            raise AccountIdentityMismatchError(f"expected_paper_account:{account_id}")

    def assert_no_cross_write(self, action: str) -> None:
        if action in self.FORBIDDEN_ACTIONS:
            raise AccountIdentityMismatchError(f"cross_account_forbidden:{action}")

    def summary(self) -> dict[str, Any]:
        return {
            "paperAccountId": self.PAPER.account_id,
            "demoAccountId": self.DEMO.account_id,
            "mixed": False,
            "balancesForcedEqual": False,
            "forbiddenActions": sorted(self.FORBIDDEN_ACTIONS),
        }
