"""Tests for Phase 6.6.1 GET-only readonly probe + credential audit.

Covers:
1. Probe disabled → network_calls=0
2. Credential missing → blocked
3. Fixtures for successful probe
4. Write paths still impossible
5. Secret redaction
6. Credential audit: presence + fingerprint + boot continuity
7. Permission fail-closed
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


# ── Credential Audit ──────────────────────────────────────────────────────

class TestCredentialAuditPresence:
    """Credential presence audit returns PRESENT/MISSING correctly."""

    def test_both_present(self):
        from backend.nexus_research.demo_exchange.credential_audit import check_credential_presence

        env = {"BYBIT_DEMO_API_KEY": "k_test", "BYBIT_DEMO_API_SECRET": "s_test"}
        result = check_credential_presence(env)
        assert result.key_status == "PRESENT"
        assert result.secret_status == "PRESENT"
        assert result.both_present is True

    def test_both_missing(self):
        from backend.nexus_research.demo_exchange.credential_audit import check_credential_presence

        result = check_credential_presence({})
        assert result.key_status == "MISSING"
        assert result.secret_status == "MISSING"
        assert result.both_present is False

    def test_key_only(self):
        from backend.nexus_research.demo_exchange.credential_audit import check_credential_presence

        result = check_credential_presence({"BYBIT_DEMO_API_KEY": "k"})
        assert result.key_status == "PRESENT"
        assert result.secret_status == "MISSING"
        assert result.both_present is False

    def test_empty_values_are_missing(self):
        from backend.nexus_research.demo_exchange.credential_audit import check_credential_presence

        env = {"BYBIT_DEMO_API_KEY": "  ", "BYBIT_DEMO_API_SECRET": ""}
        result = check_credential_presence(env)
        assert result.both_present is False


class TestCredentialFingerprint:
    """Irreversible fingerprint via HMAC-SHA256."""

    def test_fingerprint_stable(self):
        from backend.nexus_research.demo_exchange.credential_audit import credential_fingerprint

        fp1 = credential_fingerprint("key1", "secret1")
        fp2 = credential_fingerprint("key1", "secret1")
        assert fp1 == fp2
        assert len(fp1) == 8

    def test_fingerprint_different_keys(self):
        from backend.nexus_research.demo_exchange.credential_audit import credential_fingerprint

        fp1 = credential_fingerprint("key1", "secret1")
        fp2 = credential_fingerprint("key2", "secret2")
        assert fp1 != fp2

    def test_fingerprint_empty_returns_empty(self):
        from backend.nexus_research.demo_exchange.credential_audit import credential_fingerprint

        assert credential_fingerprint("", "secret") == ""
        assert credential_fingerprint("key", "") == ""
        assert credential_fingerprint("", "") == ""

    def test_fingerprint_max_length(self):
        from backend.nexus_research.demo_exchange.credential_audit import credential_fingerprint

        fp = credential_fingerprint("long_key_value_here", "long_secret_here")
        assert 6 <= len(fp) <= 8


class TestBootContinuity:
    """Boot continuity records contain no secrets."""

    def test_boot_continuity_fields(self):
        from backend.nexus_research.demo_exchange.credential_audit import build_boot_continuity

        env = {"BYBIT_DEMO_API_KEY": "k_test", "BYBIT_DEMO_API_SECRET": "s_test"}
        with patch.dict("os.environ", {}, clear=True):
            record = build_boot_continuity(env)
        d = record.to_dict()
        assert "boot_id" in d
        assert d["boot_id"]
        assert "fingerprint" in d
        assert d["credential_present"] is True
        assert d["secret_safe"] is True
        assert d["timestamp_ms"] > 0

    def test_boot_continuity_no_secrets(self):
        from backend.nexus_research.demo_exchange.credential_audit import build_boot_continuity

        secret_key = "TOP_SECRET_KEY_VALUE_999"
        secret_val = "TOP_SECRET_SECRET_VALUE_888"
        env = {"BYBIT_DEMO_API_KEY": secret_key, "BYBIT_DEMO_API_SECRET": secret_val}
        with patch.dict("os.environ", {}, clear=True):
            record = build_boot_continuity(env)
        serialized = json.dumps(record.to_dict())
        assert secret_key not in serialized
        assert secret_val not in serialized

    def test_boot_continuity_deployment_commit(self):
        from backend.nexus_research.demo_exchange.credential_audit import build_boot_continuity

        env = {
            "BYBIT_DEMO_API_KEY": "k",
            "BYBIT_DEMO_API_SECRET": "s",
            "DEPLOYMENT_COMMIT": "abc123",
        }
        with patch.dict("os.environ", {}, clear=True):
            record = build_boot_continuity(env)
        assert record.deployment_commit == "abc123"

    def test_boot_continuity_missing_creds(self):
        from backend.nexus_research.demo_exchange.credential_audit import build_boot_continuity

        with patch.dict("os.environ", {}, clear=True):
            record = build_boot_continuity({})
        assert record.credential_present is False
        assert record.fingerprint == ""


class TestFullAudit:
    """DemoCredentialPresenceAudit combines all pieces."""

    def test_full_audit_dict(self):
        from backend.nexus_research.demo_exchange.credential_audit import DemoCredentialPresenceAudit

        env = {"BYBIT_DEMO_API_KEY": "k_audit", "BYBIT_DEMO_API_SECRET": "s_audit"}
        with patch.dict("os.environ", {}, clear=True):
            audit = DemoCredentialPresenceAudit.build(env)
        d = audit.to_dict()
        assert d["key_status"] == "PRESENT"
        assert d["secret_status"] == "PRESENT"
        assert d["credential_present"] is True
        assert d["secret_safe"] is True
        assert d["fingerprint"]
        assert "boot_continuity" in d

    def test_full_audit_no_secrets(self):
        from backend.nexus_research.demo_exchange.credential_audit import DemoCredentialPresenceAudit

        sk = "ULTRA_SECRET_KEY_XYZ"
        sv = "ULTRA_SECRET_VAL_ABC"
        env = {"BYBIT_DEMO_API_KEY": sk, "BYBIT_DEMO_API_SECRET": sv}
        with patch.dict("os.environ", {}, clear=True):
            audit = DemoCredentialPresenceAudit.build(env)
        serialized = json.dumps(audit.to_dict())
        assert sk not in serialized
        assert sv not in serialized


# ── Readonly Probe ────────────────────────────────────────────────────────

class TestProbeDisabled:
    """Probe disabled → network_calls=0."""

    def test_disabled_by_default(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {}, clear=True):
            result = run_readonly_probe(environ=env)
        assert result.status == "PROBE_DISABLED"
        assert result.network_calls == 0
        assert result.probe_enabled is False

    def test_disabled_explicit_false(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "false"}, clear=True):
            result = run_readonly_probe(environ=env)
        assert result.network_calls == 0

    def test_disabled_returns_zero_endpoints(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe

        with patch.dict("os.environ", {}, clear=True):
            result = run_readonly_probe(environ={})
        d = result.to_dict()
        assert d["network_calls"] == 0
        assert d["endpoints_probed"] == []
        assert d["write_impossible"] is True


class TestProbeCredentialMissing:
    """Credential missing → blocked."""

    def test_no_creds_blocked(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe

        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = run_readonly_probe(environ={})
        assert result.status == "BLOCKED_CREDENTIALS_MISSING"
        assert result.credential_present is False
        assert result.network_calls == 0

    def test_partial_creds_blocked(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe

        env = {"BYBIT_DEMO_API_KEY": "k"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = run_readonly_probe(environ=env)
        assert result.status == "BLOCKED_CREDENTIALS_MISSING"
        assert result.network_calls == 0


class TestProbeWithFixtures:
    """Fixtures for successful probe (no live network)."""

    def test_probe_passes_with_fixture_transport(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": "k_fix", "BYBIT_DEMO_API_SECRET": "s_fix"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = run_readonly_probe(environ=env, transport=transport)
        assert result.status == "PROBE_PASSED"
        assert result.server_time_ok is True
        assert result.wallet_readable is True
        assert result.position_readable is True
        assert result.order_readable is True
        assert result.execution_readable is True
        assert result.network_calls == 6
        assert len(result.endpoints_probed) == 6
        assert result.write_attempted is False
        assert result.to_dict()["execution_write_allowed"] is False

    def test_probe_result_dict_has_all_fields(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = run_readonly_probe(environ=env, transport=transport)
        d = result.to_dict()
        required_fields = {
            "status", "probe_enabled", "credential_present", "fingerprint",
            "domain", "network_calls", "wallet_readable", "position_readable",
            "order_readable", "execution_readable", "write_impossible",
            "secret_safe", "fail_closed", "write_attempted",
        }
        assert required_fields.issubset(set(d.keys()))


class TestProbeWriteImpossible:
    """Write paths still impossible during probe."""

    def test_transport_post_raises(self):
        from backend.nexus_research.demo_exchange.errors import MethodNotAllowedError
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        with pytest.raises(MethodNotAllowedError):
            transport.post()

    def test_transport_create_order_raises(self):
        from backend.nexus_research.demo_exchange.errors import WriteForbiddenError
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        with pytest.raises(WriteForbiddenError):
            transport.create_order()

    def test_transport_withdraw_raises(self):
        from backend.nexus_research.demo_exchange.errors import WriteForbiddenError
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        with pytest.raises(WriteForbiddenError):
            transport.withdraw()

    def test_probe_result_write_impossible(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe

        with patch.dict("os.environ", {}, clear=True):
            result = run_readonly_probe(environ={})
        assert result.to_dict()["write_impossible"] is True
        assert result.write_attempted is False


class TestProbeSecretRedaction:
    """Secret never appears in probe output."""

    SECRET_KEY = "PROBE_SECRET_KEY_ABCDEF_12345"
    SECRET_VAL = "PROBE_SECRET_VAL_GHIJKL_67890"

    def test_probe_dict_no_secrets(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe

        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        with patch.dict("os.environ", {}, clear=True):
            result = run_readonly_probe(environ=env)
        serialized = json.dumps(result.to_dict())
        assert self.SECRET_KEY not in serialized
        assert self.SECRET_VAL not in serialized

    def test_probe_enabled_dict_no_secrets(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            result = run_readonly_probe(environ=env, transport=transport)
        serialized = json.dumps(result.to_dict())
        assert self.SECRET_KEY not in serialized
        assert self.SECRET_VAL not in serialized

    def test_no_secrets_in_stdout(self, capsys):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
            run_readonly_probe(environ=env, transport=transport)
        captured = capsys.readouterr()
        assert self.SECRET_KEY not in captured.out
        assert self.SECRET_VAL not in captured.out
        assert self.SECRET_KEY not in captured.err
        assert self.SECRET_VAL not in captured.err


class TestProbePermissionCheck:
    """Permission check — fail-closed if forbidden permissions appear."""

    def test_check_permissions_clean(self):
        from backend.nexus_research.demo_exchange.readonly_probe import _check_permissions

        data = {"permissions": {"ReadOnly": ["ReadOnly"]}}
        result = _check_permissions(data)
        assert result["read_only"] is True
        assert result["fail_closed"] is False

    def test_check_permissions_trade_present(self):
        from backend.nexus_research.demo_exchange.readonly_probe import _check_permissions

        data = {"permissions": {"ContractTrade": ["Trade"], "ReadOnly": ["ReadOnly"]}}
        result = _check_permissions(data)
        # Trade-capable Demo keys are expected; hard-fail only Withdraw/Transfer.
        assert result["fail_closed"] is False
        assert result["trade_capable"] is True
        assert "Trade" in result["trade_permissions"]
        assert result["writes_still_impossible"] is True
        assert result["execution_write_allowed"] is False

    def test_check_permissions_withdraw_hard_fail(self):
        from backend.nexus_research.demo_exchange.readonly_probe import _check_permissions

        data = {"permissions": {"Wallet": ["Withdraw"]}}
        result = _check_permissions(data)
        assert result["fail_closed"] is True
        assert "Withdraw" in result["hard_violations"]

    def test_check_permissions_empty(self):
        from backend.nexus_research.demo_exchange.readonly_probe import _check_permissions

        result = _check_permissions({})
        assert result["read_only"] is True
        assert result["fail_closed"] is False

    def test_probe_stops_on_withdraw_permission(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

        transport = DemoReadOnlyTransport(use_fixtures=True)
        # Force withdraw fixture via monkeypatch of FIXTURE path
        from backend.nexus_research.demo_exchange import fixtures as fx

        original = fx.FIXTURE_BY_PATH["/v5/user/query-api"]
        fx.FIXTURE_BY_PATH["/v5/user/query-api"] = lambda **_: fx.fixture_query_api(withdraw=True)
        try:
            env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
            with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
                result = run_readonly_probe(environ=env, transport=transport)
            assert result.status == "FAIL_CLOSED_PERMISSION"
            assert result.fail_closed is True
            assert result.wallet_readable is False
            assert result.network_calls == 2  # time + query-api only
        finally:
            fx.FIXTURE_BY_PATH["/v5/user/query-api"] = original

    def test_probe_continues_on_trade_capable_key(self):
        from backend.nexus_research.demo_exchange.readonly_probe import run_readonly_probe
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport
        from backend.nexus_research.demo_exchange import fixtures as fx

        transport = DemoReadOnlyTransport(use_fixtures=True)
        original = fx.FIXTURE_BY_PATH["/v5/user/query-api"]
        fx.FIXTURE_BY_PATH["/v5/user/query-api"] = lambda **_: fx.fixture_query_api(trade=True)
        try:
            env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
            with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "true"}, clear=True):
                result = run_readonly_probe(environ=env, transport=transport)
            assert result.status == "PROBE_PASSED"
            assert result.fail_closed is False
            assert result.permission_check.get("trade_capable") is True
            assert result.wallet_readable is True
            assert result.to_dict()["write_impossible"] is True
        finally:
            fx.FIXTURE_BY_PATH["/v5/user/query-api"] = original


class TestFingerprintBootContinuityCompare:
    """Fingerprint can be used for boot continuity comparison."""

    def test_same_creds_same_fingerprint(self):
        from backend.nexus_research.demo_exchange.credential_audit import build_credential_fingerprint

        env = {"BYBIT_DEMO_API_KEY": "key_x", "BYBIT_DEMO_API_SECRET": "secret_x"}
        fp1 = build_credential_fingerprint(env)
        fp2 = build_credential_fingerprint(env)
        assert fp1 == fp2
        assert fp1 != ""

    def test_different_creds_different_fingerprint(self):
        from backend.nexus_research.demo_exchange.credential_audit import build_credential_fingerprint

        env_a = {"BYBIT_DEMO_API_KEY": "key_a", "BYBIT_DEMO_API_SECRET": "secret_a"}
        env_b = {"BYBIT_DEMO_API_KEY": "key_b", "BYBIT_DEMO_API_SECRET": "secret_b"}
        fp_a = build_credential_fingerprint(env_a)
        fp_b = build_credential_fingerprint(env_b)
        assert fp_a != fp_b
