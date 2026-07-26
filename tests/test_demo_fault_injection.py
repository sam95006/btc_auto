"""TRACK 9 — Fault Injection Tests.

Simulates operational failure scenarios to verify system resilience.
All tests use mocks — no live connections, no real orders.

Ambiguous states MUST block new orders until resolved.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


RESEARCH_ONLY: bool = True


# ── Mock Exchange Client ──────────────────────────────────────────────────────

class MockExchangeClient:
    """Simulates exchange API for fault injection."""

    def __init__(self) -> None:
        self.credentials_valid = True
        self.orders_sent: list[dict] = []
        self.fills_received: list[dict] = []
        self.position_open = False
        self.order_blocked = False
        self._timeout_next = False
        self._reject_next = False
        self._partial_fill_next = False
        self._duplicate_ack = False

    def set_credentials_invalid(self) -> None:
        self.credentials_valid = False

    def set_timeout_next(self) -> None:
        self._timeout_next = True

    def set_reject_next(self, reason: str = "INSUFFICIENT_MARGIN") -> None:
        self._reject_next = True
        self._reject_reason = reason

    def set_partial_fill_next(self, fill_pct: float = 0.5) -> None:
        self._partial_fill_next = True
        self._fill_pct = fill_pct

    def set_duplicate_ack(self) -> None:
        self._duplicate_ack = True

    def place_order(self, symbol: str, side: str, qty: float, **kwargs) -> dict:
        if self.order_blocked:
            raise OrderBlockedError("Orders blocked due to ambiguous state")

        if not self.credentials_valid:
            raise CredentialError("API credentials invalid or expired")

        if self._timeout_next:
            self._timeout_next = False
            raise TimeoutError("Exchange API timeout — order status UNKNOWN")

        if self._reject_next:
            self._reject_next = False
            raise OrderRejectedError(f"Order rejected: {self._reject_reason}")

        order = {
            "orderId": f"ORD-{len(self.orders_sent)+1}",
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "status": "NEW",
            "timestamp": int(time.time() * 1000),
        }

        if self._partial_fill_next:
            self._partial_fill_next = False
            order["status"] = "PARTIALLY_FILLED"
            order["filledQty"] = qty * self._fill_pct
            order["remainingQty"] = qty * (1 - self._fill_pct)

        if self._duplicate_ack:
            self._duplicate_ack = False
            order["duplicate_warning"] = True

        self.orders_sent.append(order)
        return order

    def get_position(self, symbol: str) -> dict | None:
        if self.position_open:
            return {"symbol": symbol, "qty": 0.001, "side": "Buy"}
        return None

    def cancel_order(self, order_id: str) -> dict:
        return {"orderId": order_id, "status": "CANCELLED"}


class CredentialError(Exception):
    pass


class OrderBlockedError(Exception):
    pass


class OrderRejectedError(Exception):
    pass


# ── Order Guard (ambiguous state blocker) ─────────────────────────────────────

class OrderGuard:
    """Blocks new orders when system is in ambiguous state."""

    def __init__(self) -> None:
        self.blocked = False
        self.block_reason: str | None = None
        self.block_since_ms: int | None = None

    def block(self, reason: str) -> None:
        self.blocked = True
        self.block_reason = reason
        self.block_since_ms = int(time.time() * 1000)

    def unblock(self) -> None:
        self.blocked = False
        self.block_reason = None
        self.block_since_ms = None

    def check(self) -> None:
        if self.blocked:
            raise OrderBlockedError(
                f"Orders blocked: {self.block_reason} (since {self.block_since_ms})"
            )


# ══════════════════════════════════════════════════════════════════════════════
# FAULT INJECTION TEST SCENARIOS
# ══════════════════════════════════════════════════════════════════════════════


class TestCredentialDisappear:
    """Credentials vanish mid-session."""

    def test_credential_disappear_blocks_orders(self):
        client = MockExchangeClient()
        client.place_order("BTCUSDT", "Buy", 0.001)
        assert len(client.orders_sent) == 1

        client.set_credentials_invalid()
        with pytest.raises(CredentialError):
            client.place_order("BTCUSDT", "Buy", 0.001)

    def test_credential_disappear_triggers_guard(self):
        client = MockExchangeClient()
        guard = OrderGuard()

        client.set_credentials_invalid()
        try:
            client.place_order("BTCUSDT", "Buy", 0.001)
        except CredentialError:
            guard.block("Credential failure detected")

        with pytest.raises(OrderBlockedError):
            guard.check()

    def test_credential_recovery_unblocks(self):
        guard = OrderGuard()
        guard.block("Credential failure")
        with pytest.raises(OrderBlockedError):
            guard.check()

        guard.unblock()
        guard.check()  # should not raise


class TestTimeoutAmbiguous:
    """Timeout leaves order status unknown — MUST block new orders."""

    def test_timeout_blocks_new_orders(self):
        client = MockExchangeClient()
        guard = OrderGuard()

        client.set_timeout_next()
        try:
            client.place_order("BTCUSDT", "Buy", 0.001)
        except TimeoutError:
            guard.block("Timeout — order status UNKNOWN")

        assert guard.blocked
        with pytest.raises(OrderBlockedError):
            guard.check()

    def test_timeout_does_not_send_duplicate(self):
        client = MockExchangeClient()
        guard = OrderGuard()

        client.set_timeout_next()
        try:
            client.place_order("BTCUSDT", "Buy", 0.001)
        except TimeoutError:
            guard.block("Timeout — order status UNKNOWN")

        assert len(client.orders_sent) == 0
        client.order_blocked = True
        with pytest.raises(OrderBlockedError):
            client.place_order("BTCUSDT", "Buy", 0.001)

    def test_timeout_resolution_after_confirmation(self):
        guard = OrderGuard()
        guard.block("Timeout — order status UNKNOWN")

        confirmed_status = "FILLED"
        if confirmed_status in ("FILLED", "CANCELLED", "REJECTED"):
            guard.unblock()

        guard.check()  # should not raise


class TestDuplicateAck:
    """Exchange sends duplicate acknowledgment."""

    def test_duplicate_ack_detected(self):
        client = MockExchangeClient()
        client.set_duplicate_ack()
        result = client.place_order("BTCUSDT", "Buy", 0.001)
        assert result.get("duplicate_warning") is True

    def test_duplicate_ack_blocks_until_reconciled(self):
        client = MockExchangeClient()
        guard = OrderGuard()

        client.set_duplicate_ack()
        result = client.place_order("BTCUSDT", "Buy", 0.001)
        if result.get("duplicate_warning"):
            guard.block("Duplicate ACK — reconciliation needed")

        with pytest.raises(OrderBlockedError):
            guard.check()

    def test_duplicate_ack_single_position_after_reconciliation(self):
        client = MockExchangeClient()
        guard = OrderGuard()
        guard.block("Duplicate ACK")

        actual_positions = [{"symbol": "BTCUSDT", "qty": 0.001}]
        expected_qty = 0.001
        if len(actual_positions) == 1 and actual_positions[0]["qty"] == expected_qty:
            guard.unblock()

        guard.check()


class TestPartialFill:
    """Order partially filled — must track remainder."""

    def test_partial_fill_tracked(self):
        client = MockExchangeClient()
        client.set_partial_fill_next(fill_pct=0.6)
        result = client.place_order("BTCUSDT", "Buy", 0.01)

        assert result["status"] == "PARTIALLY_FILLED"
        assert result["filledQty"] == pytest.approx(0.006, abs=1e-9)
        assert result["remainingQty"] == pytest.approx(0.004, abs=1e-9)

    def test_partial_fill_does_not_block_if_known(self):
        client = MockExchangeClient()
        guard = OrderGuard()

        client.set_partial_fill_next(fill_pct=0.5)
        result = client.place_order("BTCUSDT", "Buy", 0.01)

        if result["status"] == "PARTIALLY_FILLED" and "filledQty" in result:
            pass  # known state — no block
        else:
            guard.block("Unknown partial state")

        assert not guard.blocked

    def test_partial_fill_blocks_if_qty_unknown(self):
        guard = OrderGuard()
        result = {"status": "PARTIALLY_FILLED"}  # missing filledQty

        if "filledQty" not in result:
            guard.block("Partial fill — filled qty unknown")

        assert guard.blocked


class TestRestartAfterSend:
    """System restarts after order sent but before fill confirmation."""

    def test_restart_after_send_blocks_orders(self):
        guard = OrderGuard()
        pending_orders = [{"orderId": "ORD-1", "status": "NEW", "sent_at": 1000}]

        if pending_orders:
            guard.block("Restart recovery — unconfirmed orders exist")

        assert guard.blocked
        with pytest.raises(OrderBlockedError):
            guard.check()

    def test_restart_after_send_reconciles(self):
        guard = OrderGuard()
        guard.block("Restart recovery")

        exchange_status = {"orderId": "ORD-1", "status": "FILLED"}
        if exchange_status["status"] in ("FILLED", "CANCELLED"):
            guard.unblock()

        guard.check()


class TestRestartAfterFill:
    """System restarts after fill — must sync position state."""

    def test_restart_after_fill_detects_position(self):
        client = MockExchangeClient()
        client.position_open = True

        pos = client.get_position("BTCUSDT")
        assert pos is not None
        assert pos["qty"] == 0.001

    def test_restart_after_fill_no_duplicate_open(self):
        client = MockExchangeClient()
        guard = OrderGuard()
        client.position_open = True

        pos = client.get_position("BTCUSDT")
        if pos is not None:
            guard.block("Position exists — no new entries until reconciled")

        with pytest.raises(OrderBlockedError):
            guard.check()


class TestMismatchRecords:
    """Local records don't match exchange records."""

    def test_mismatch_detected_blocks_orders(self):
        guard = OrderGuard()
        local_position = {"symbol": "BTCUSDT", "qty": 0.001, "side": "Buy"}
        exchange_position = {"symbol": "BTCUSDT", "qty": 0.002, "side": "Buy"}

        if local_position["qty"] != exchange_position["qty"]:
            guard.block(
                f"Position mismatch: local={local_position['qty']} vs exchange={exchange_position['qty']}"
            )

        assert guard.blocked

    def test_mismatch_no_position_local_but_exists_exchange(self):
        guard = OrderGuard()
        local_position = None
        exchange_position = {"symbol": "BTCUSDT", "qty": 0.001}

        if local_position is None and exchange_position is not None:
            guard.block("Ghost position on exchange — not in local records")

        assert guard.blocked

    def test_mismatch_resolved_after_sync(self):
        guard = OrderGuard()
        guard.block("Position mismatch")

        local_position = {"qty": 0.001}
        exchange_position = {"qty": 0.001}
        if local_position["qty"] == exchange_position["qty"]:
            guard.unblock()

        guard.check()


class TestLeverageRejection:
    """25x leverage rejected by exchange."""

    def test_25x_rejected_blocks_trade(self):
        client = MockExchangeClient()
        client.set_reject_next("LEVERAGE_NOT_SUPPORTED")

        with pytest.raises(OrderRejectedError, match="LEVERAGE_NOT_SUPPORTED"):
            client.place_order("BTCUSDT", "Buy", 0.001, leverage=25)

    def test_25x_rejected_triggers_downgrade_flag(self):
        client = MockExchangeClient()
        guard = OrderGuard()
        downgrade_needed = False

        client.set_reject_next("MAX_LEVERAGE_EXCEEDED")
        try:
            client.place_order("BTCUSDT", "Buy", 0.001, leverage=25)
        except OrderRejectedError as e:
            if "LEVERAGE" in str(e):
                downgrade_needed = True

        assert downgrade_needed
        assert not guard.blocked  # rejection is not ambiguous

    def test_25x_rejected_does_not_block_if_deterministic(self):
        guard = OrderGuard()
        rejection_reason = "MAX_LEVERAGE_EXCEEDED"

        deterministic_rejections = {
            "MAX_LEVERAGE_EXCEEDED",
            "INSUFFICIENT_MARGIN",
            "MIN_ORDER_SIZE",
        }
        if rejection_reason in deterministic_rejections:
            pass  # no guard block
        else:
            guard.block(f"Unknown rejection: {rejection_reason}")

        assert not guard.blocked


class TestRateLimitExhausted:
    """API rate limit prevents order management."""

    def test_rate_limit_blocks_temporarily(self):
        guard = OrderGuard()
        rate_limited = True
        retry_after_ms = 30_000

        if rate_limited:
            guard.block(f"Rate limited — retry after {retry_after_ms}ms")

        assert guard.blocked

    def test_rate_limit_with_open_position_escalates(self):
        guard = OrderGuard()
        has_open_position = True
        rate_limited = True

        severity = "CRITICAL" if (rate_limited and has_open_position) else "WARNING"
        if rate_limited:
            guard.block(f"Rate limited [{severity}]")

        assert "CRITICAL" in guard.block_reason


class TestNetworkPartition:
    """Network connectivity lost."""

    def test_network_loss_blocks_all_orders(self):
        guard = OrderGuard()
        network_ok = False

        if not network_ok:
            guard.block("Network partition — no exchange connectivity")

        assert guard.blocked

    def test_network_recovery_requires_position_check(self):
        guard = OrderGuard()
        guard.block("Network partition")

        network_restored = True
        position_synced = False

        if network_restored and not position_synced:
            pass  # stay blocked until positions reconciled
        elif network_restored and position_synced:
            guard.unblock()

        assert guard.blocked  # still blocked — positions not synced

        position_synced = True
        if network_restored and position_synced:
            guard.unblock()

        guard.check()


class TestMultipleSimultaneousFaults:
    """Multiple faults occurring at once."""

    def test_compound_fault_all_block(self):
        guard = OrderGuard()
        faults = [
            "Timeout — order status UNKNOWN",
            "Network degraded",
            "Rate limit approaching",
        ]
        guard.block("; ".join(faults))
        assert guard.blocked
        assert "Timeout" in guard.block_reason
        assert "Network" in guard.block_reason

    def test_compound_fault_requires_full_resolution(self):
        guard = OrderGuard()
        unresolved = {"timeout": True, "mismatch": True}

        guard.block("Multiple faults")

        unresolved["timeout"] = False
        if any(unresolved.values()):
            pass  # stay blocked
        else:
            guard.unblock()

        assert guard.blocked

        unresolved["mismatch"] = False
        if not any(unresolved.values()):
            guard.unblock()

        guard.check()


class TestFundingRateSpike:
    """Extreme funding rate scenario."""

    def test_extreme_funding_rate_blocks_new_entry(self):
        guard = OrderGuard()
        funding_rate = 0.01  # 1% per 8h — extreme

        FUNDING_BLOCK_THRESHOLD = 0.005
        if abs(funding_rate) > FUNDING_BLOCK_THRESHOLD:
            guard.block(f"Extreme funding rate: {funding_rate}")

        assert guard.blocked

    def test_normal_funding_rate_allows_entry(self):
        guard = OrderGuard()
        funding_rate = 0.0001

        FUNDING_BLOCK_THRESHOLD = 0.005
        if abs(funding_rate) > FUNDING_BLOCK_THRESHOLD:
            guard.block(f"Extreme funding rate: {funding_rate}")

        assert not guard.blocked


class TestOrderBookEmpty:
    """Order book has no liquidity."""

    def test_empty_book_blocks_market_order(self):
        guard = OrderGuard()
        best_ask = None  # no liquidity

        if best_ask is None:
            guard.block("No liquidity — order book empty")

        assert guard.blocked

    def test_thin_book_warns_but_allows_limit(self):
        guard = OrderGuard()
        spread_bps = 50  # 50 bps spread — thin but not empty

        SPREAD_BLOCK_THRESHOLD_BPS = 100
        if spread_bps >= SPREAD_BLOCK_THRESHOLD_BPS:
            guard.block("Spread too wide")

        assert not guard.blocked
