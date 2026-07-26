"""Phase 6.6.1 — Demo Account Snapshot (GET-only, no secret values).

Hard rules:
- NEVER use PAPER 10000 as demo balance
- Flag EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW if unexpected open positions/orders
- Only works when probe enabled; else returns probe_disabled status with zero network calls
- No secrets in any output
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_exchange.constants import (
    ACCOUNT_BYBIT_DEMO,
    DEMO_REST_BASE_URL,
)
from backend.nexus_research.demo_exchange.credential_audit import (
    build_credential_fingerprint,
    check_credential_presence,
)
from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import DemoExchangeError
from backend.nexus_research.demo_exchange.factory import DemoPrivateClientFactory
from backend.nexus_research.demo_exchange.readers import (
    DemoExecutionReader,
    DemoOpenOrderReader,
    DemoOrderHistoryReader,
    DemoPositionReader,
    DemoWalletReader,
)
from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

_PAPER_BALANCE_SENTINEL = 10_000.0


class SnapshotStatus:
    PROBE_DISABLED = "PROBE_DISABLED"
    BLOCKED_CREDENTIALS_MISSING = "BLOCKED_CREDENTIALS_MISSING"
    SNAPSHOT_OK = "SNAPSHOT_OK"
    EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW = "EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW"
    SNAPSHOT_PARTIAL = "SNAPSHOT_PARTIAL"
    SNAPSHOT_FAILED = "SNAPSHOT_FAILED"


@dataclass
class AccountSnapshotResult:
    """Full demo account snapshot — no secret values."""
    status: str
    account_identity: str = ACCOUNT_BYBIT_DEMO
    account_type: str = ""
    total_equity: float = 0.0
    wallet_balance: float = 0.0
    available_balance: float = 0.0
    unrealised_pnl: float = 0.0
    margins: float = 0.0
    currency: str = "USDT"
    updated_at_ms: int = 0
    freshness_ms: int = 0
    positions: list[dict[str, Any]] = field(default_factory=list)
    open_orders: list[dict[str, Any]] = field(default_factory=list)
    recent_orders: list[dict[str, Any]] = field(default_factory=list)
    executions: list[dict[str, Any]] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)
    network_calls: int = 0
    probe_enabled: bool = False
    credential_present: bool = False
    fingerprint: str = ""
    errors: list[str] = field(default_factory=list)
    captured_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "account_identity": self.account_identity,
            "account_type": self.account_type,
            "total_equity": self.total_equity,
            "wallet_balance": self.wallet_balance,
            "available_balance": self.available_balance,
            "unrealised_pnl": self.unrealised_pnl,
            "margins": self.margins,
            "currency": self.currency,
            "updated_at_ms": self.updated_at_ms,
            "freshness_ms": self.freshness_ms,
            "positions": list(self.positions),
            "open_orders": list(self.open_orders),
            "recent_orders": list(self.recent_orders),
            "executions": list(self.executions),
            "review_flags": list(self.review_flags),
            "network_calls": self.network_calls,
            "probe_enabled": self.probe_enabled,
            "credential_present": self.credential_present,
            "fingerprint": self.fingerprint,
            "errors": list(self.errors),
            "write_impossible": True,
            "secret_safe": True,
            "captured_at_ms": self.captured_at_ms,
        }


def _probe_enabled() -> bool:
    raw = os.environ.get("DEMO_READONLY_PROBE_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes")


def _check_paper_balance(equity: float) -> bool:
    """Return True if balance looks like PAPER sentinel value."""
    return abs(equity - _PAPER_BALANCE_SENTINEL) < 0.01


def capture_account_snapshot(
    *,
    environ: dict[str, str] | None = None,
    transport: DemoReadOnlyTransport | None = None,
) -> AccountSnapshotResult:
    """Capture a GET-only demo account snapshot.

    Returns probe_disabled with zero network calls when probe is off.
    """
    now = int(time.time() * 1000)
    probe_on = _probe_enabled()
    presence = check_credential_presence(environ)
    fp = build_credential_fingerprint(environ)

    if not probe_on:
        return AccountSnapshotResult(
            status=SnapshotStatus.PROBE_DISABLED,
            probe_enabled=False,
            credential_present=presence.both_present,
            fingerprint=fp,
            network_calls=0,
            captured_at_ms=now,
        )

    if not presence.both_present:
        return AccountSnapshotResult(
            status=SnapshotStatus.BLOCKED_CREDENTIALS_MISSING,
            probe_enabled=True,
            credential_present=False,
            fingerprint="",
            network_calls=0,
            captured_at_ms=now,
        )

    if transport is None:
        try:
            policy = DemoDomainPolicy(DEMO_REST_BASE_URL)
            factory = DemoPrivateClientFactory(policy=policy)
            transport, _meta = factory.create()
        except Exception as exc:
            return AccountSnapshotResult(
                status=SnapshotStatus.SNAPSHOT_FAILED,
                probe_enabled=True,
                credential_present=True,
                fingerprint=fp,
                errors=[f"factory:{type(exc).__name__}"],
                network_calls=0,
                captured_at_ms=now,
            )

    result = AccountSnapshotResult(
        status=SnapshotStatus.SNAPSHOT_OK,
        probe_enabled=True,
        credential_present=True,
        fingerprint=fp,
        captured_at_ms=now,
    )

    # Wallet
    try:
        wallet = DemoWalletReader(transport).read(check_stale=False)
        result.account_type = wallet.account_type
        result.total_equity = wallet.total_equity
        result.wallet_balance = wallet.wallet_balance
        result.available_balance = wallet.available_balance
        result.currency = wallet.coin
        result.updated_at_ms = wallet.raw_time_ms
        result.freshness_ms = abs(now - wallet.raw_time_ms) if wallet.raw_time_ms else 0
        result.unrealised_pnl = result.total_equity - result.wallet_balance
        result.margins = result.wallet_balance - result.available_balance
        result.network_calls += 1

        if _check_paper_balance(wallet.total_equity):
            result.review_flags.append("BALANCE_MATCHES_PAPER_SENTINEL_10000")
    except DemoExchangeError as exc:
        result.errors.append(f"wallet:{type(exc).__name__}")
    except Exception as exc:
        result.errors.append(f"wallet:{type(exc).__name__}")

    # Positions
    try:
        positions = DemoPositionReader(transport).read(check_stale=False)
        result.positions = [p.to_dict() for p in positions if p.size > 0]
        result.network_calls += 1
        if result.positions:
            result.review_flags.append("EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW")
    except DemoExchangeError as exc:
        result.errors.append(f"positions:{type(exc).__name__}")
    except Exception as exc:
        result.errors.append(f"positions:{type(exc).__name__}")

    # Open orders
    try:
        open_orders = DemoOpenOrderReader(transport).read()
        result.open_orders = [o.to_dict() for o in open_orders]
        result.network_calls += 1
        if result.open_orders:
            result.review_flags.append("EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW")
    except DemoExchangeError as exc:
        result.errors.append(f"open_orders:{type(exc).__name__}")
    except Exception as exc:
        result.errors.append(f"open_orders:{type(exc).__name__}")

    # Recent orders (history)
    try:
        history = DemoOrderHistoryReader(transport).read()
        result.recent_orders = [o.to_dict() for o in history]
        result.network_calls += 1
    except DemoExchangeError as exc:
        result.errors.append(f"order_history:{type(exc).__name__}")
    except Exception as exc:
        result.errors.append(f"order_history:{type(exc).__name__}")

    # Executions
    try:
        executions = DemoExecutionReader(transport).read()
        result.executions = [e.to_dict() for e in executions]
        result.network_calls += 1
    except DemoExchangeError as exc:
        result.errors.append(f"executions:{type(exc).__name__}")
    except Exception as exc:
        result.errors.append(f"executions:{type(exc).__name__}")

    # Deduplicate review flags
    result.review_flags = sorted(set(result.review_flags))

    if SnapshotStatus.EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW.replace("_", "") in "".join(
        f.replace("_", "") for f in result.review_flags
    ):
        result.status = SnapshotStatus.EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW

    if result.errors and not result.wallet_balance:
        result.status = SnapshotStatus.SNAPSHOT_PARTIAL if result.network_calls > 0 else SnapshotStatus.SNAPSHOT_FAILED

    return result
