"""Tests for Phase 6.6.1 Demo Account Snapshot.

Covers:
1. Probe disabled → network_calls=0
2. Credential missing → blocked
3. Fixtures for successful snapshot
4. Write paths still impossible
5. Secret redaction
6. Unexpected positions flag
7. PAPER balance sentinel detection
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


class TestSnapshotProbeDisabled:
    """Probe disabled → network_calls=0, no network activity."""

    def test_disabled_returns_zero_calls(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {}, clear=True):
            result = capture_account_snapshot(environ=env)
        assert result.status == "PROBE_DISABLED"
        assert result.network_calls == 0
        assert result.probe_enabled is False

    def test_disabled_explicit_false(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "false"}, clear=True):
            result = capture_account_snapshot(environ=env)
        assert result.network_calls == 0
        assert result.status == "PROBE_DISABLED"

    def test_disabled_dict_write_impossible(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        with patch.dict("os.environ", {}, clear=True):
            result = capture_account_snapshot(environ={})
        d = result.to_dict()
        assert d["write_impossible"] is True
        assert d["secret_safe"] is True
        assert d["network_calls"] == 0


class TestSnapshotCredentialMissing:
    """Credential missing → blocked."""

    def test_no_creds_blocked(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = capture_account_snapshot(environ={})
        assert result.status == "BLOCKED_CREDENTIALS_MISSING"
        assert result.credential_present is False
        assert result.network_calls == 0

    def test_partial_creds_blocked(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        env = {"BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = capture_account_snapshot(environ=env)
        assert result.status == "BLOCKED_CREDENTIALS_MISSING"
        assert result.network_calls == 0


class TestSnapshotWithFixtures:
    """Fixtures for successful snapshot (no live network)."""

    def test_snapshot_succeeds_with_fixtures(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": "k_snap", "BYBIT_DEMO_API_SECRET": "s_snap"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = capture_account_snapshot(environ=env, transport=transport)
        assert result.network_calls >= 4
        assert result.wallet_balance > 0
        assert result.account_type == "UNIFIED"
        assert result.currency == "USDT"
        assert result.captured_at_ms > 0

    def test_snapshot_dict_has_all_fields(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = capture_account_snapshot(environ=env, transport=transport)
        d = result.to_dict()
        required = {
            "status", "account_identity", "account_type", "total_equity",
            "wallet_balance", "available_balance", "unrealised_pnl",
            "margins", "currency", "updated_at_ms", "freshness_ms",
            "positions", "open_orders", "recent_orders", "executions",
            "review_flags", "network_calls", "write_impossible", "secret_safe",
        }
        assert required.issubset(set(d.keys()))

    def test_snapshot_positions_present(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = capture_account_snapshot(environ=env, transport=transport)
        assert isinstance(result.positions, list)
        assert isinstance(result.open_orders, list)
        assert isinstance(result.recent_orders, list)
        assert isinstance(result.executions, list)


class TestSnapshotWriteImpossible:
    """Write paths still impossible in snapshot context."""

    def test_snapshot_write_impossible_flag(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        with patch.dict("os.environ", {}, clear=True):
            result = capture_account_snapshot(environ={})
        assert result.to_dict()["write_impossible"] is True

    def test_transport_rejects_all_writes(self):
        from backend.nexus_research.demo_exchange.errors import (
            MethodNotAllowedError,
            WriteForbiddenError,
        )
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        for method in [transport.post, transport.put, transport.delete]:
            with pytest.raises(MethodNotAllowedError):
                method()
        for method in [transport.create_order, transport.cancel_order, transport.withdraw, transport.transfer]:
            with pytest.raises(WriteForbiddenError):
                method()


class TestSnapshotSecretRedaction:
    """Secret never appears in snapshot output."""

    SECRET_KEY = "SNAP_SECRET_KEY_QWERTY_54321"
    SECRET_VAL = "SNAP_SECRET_VAL_UIOP_09876"

    def test_snapshot_disabled_no_secrets(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        with patch.dict("os.environ", {}, clear=True):
            result = capture_account_snapshot(environ=env)
        serialized = json.dumps(result.to_dict())
        assert self.SECRET_KEY not in serialized
        assert self.SECRET_VAL not in serialized

    def test_snapshot_enabled_no_secrets(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = capture_account_snapshot(environ=env, transport=transport)
        serialized = json.dumps(result.to_dict())
        assert self.SECRET_KEY not in serialized
        assert self.SECRET_VAL not in serialized

    def test_no_secrets_in_stdout(self, capsys):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            capture_account_snapshot(environ=env, transport=transport)
        captured = capsys.readouterr()
        assert self.SECRET_KEY not in captured.out
        assert self.SECRET_VAL not in captured.out


class TestSnapshotUnexpectedPositions:
    """Flag EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW if unexpected open positions/orders."""

    def test_fixture_positions_flag_review(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = capture_account_snapshot(environ=env, transport=transport)
        assert "EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW" in result.review_flags
        assert result.status == "EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW"


class TestSnapshotPaperBalanceSentinel:
    """NEVER use PAPER 10000 as demo balance — detect if suspicious."""

    def test_paper_sentinel_flagged(self):
        from backend.nexus_research.demo_exchange.account_snapshot import _check_paper_balance

        assert _check_paper_balance(10000.0) is True
        assert _check_paper_balance(10000.005) is True

    def test_non_paper_balance_ok(self):
        from backend.nexus_research.demo_exchange.account_snapshot import _check_paper_balance

        assert _check_paper_balance(5000.0) is False
        assert _check_paper_balance(15000.0) is False
        assert _check_paper_balance(0.0) is False

    def test_fixture_wallet_10000_gets_flagged(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = capture_account_snapshot(environ=env, transport=transport)
        assert "BALANCE_MATCHES_PAPER_SENTINEL_10000" in result.review_flags


class TestSnapshotAccountIdentity:
    """Account identity must be BYBIT_DEMO_ACCOUNT, not PAPER."""

    def test_identity_is_bybit_demo(self):
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        with patch.dict("os.environ", {}, clear=True):
            result = capture_account_snapshot(environ={})
        assert result.account_identity == "BYBIT_DEMO_ACCOUNT"
        assert result.account_identity != "NEXUS_PAPER_MAIN_V1"
