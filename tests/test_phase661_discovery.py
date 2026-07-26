"""Tests for Phase 6.6.1 credential discovery — safe integration.

Covers all 7 required categories:
1. Credential present + probe disabled → CREDENTIAL_DETECTED_PROBE_DISABLED, network_calls=0
2. Credential missing → BLOCKED_CREDENTIALS_MISSING
3. Name mismatch (alt names only) → BLOCKED_CREDENTIAL_NAME_MISMATCH
4. Probe disabled → zero wallet/position/order/execution calls
5. POST/PUT/DELETE impossible
6. Secret never in stdout/logs/exception/JSON/readiness
7. PAPER/Ledger unaffected
"""
from __future__ import annotations

import io
import json
import sys
from unittest.mock import patch

import pytest


class TestCredentialDiscoveryPresent:
    """Category 1: Credential present + probe disabled."""

    def test_detected_probe_disabled(self):
        from backend.nexus_research.demo_exchange.discovery import (
            DiscoveryStatus,
            discover_credentials,
        )

        env = {"BYBIT_DEMO_API_KEY": "k_test_abc", "BYBIT_DEMO_API_SECRET": "s_test_xyz"}
        result = discover_credentials(environ=env)
        assert result.status == DiscoveryStatus.CREDENTIAL_DETECTED_PROBE_DISABLED
        assert result.key_present is True
        assert result.secret_present is True
        assert result.network_calls == 0
        assert result.private_api_call_count == 0

    def test_probe_flag_false_by_default(self):
        from backend.nexus_research.demo_exchange.discovery import discover_credentials

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {}, clear=True):
            result = discover_credentials(environ=env)
        assert result.probe_enabled is False

    def test_write_impossible(self):
        from backend.nexus_research.demo_exchange.discovery import discover_credentials

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        result = discover_credentials(environ=env)
        assert result.write_impossible is True
        assert result.execution_write_allowed is False


class TestCredentialMissing:
    """Category 2: Credential missing → BLOCKED_CREDENTIALS_MISSING."""

    def test_both_missing(self):
        from backend.nexus_research.demo_exchange.discovery import (
            DiscoveryStatus,
            discover_credentials,
        )

        result = discover_credentials(environ={})
        assert result.status == DiscoveryStatus.BLOCKED_CREDENTIALS_MISSING
        assert result.key_present is False
        assert result.secret_present is False
        assert result.network_calls == 0

    def test_key_only(self):
        from backend.nexus_research.demo_exchange.discovery import (
            DiscoveryStatus,
            discover_credentials,
        )

        env = {"BYBIT_DEMO_API_KEY": "k"}
        result = discover_credentials(environ=env)
        assert result.status == DiscoveryStatus.BLOCKED_CREDENTIALS_MISSING

    def test_secret_only(self):
        from backend.nexus_research.demo_exchange.discovery import (
            DiscoveryStatus,
            discover_credentials,
        )

        env = {"BYBIT_DEMO_API_SECRET": "s"}
        result = discover_credentials(environ=env)
        assert result.status == DiscoveryStatus.BLOCKED_CREDENTIALS_MISSING

    def test_empty_values_treated_as_missing(self):
        from backend.nexus_research.demo_exchange.discovery import (
            DiscoveryStatus,
            discover_credentials,
        )

        env = {"BYBIT_DEMO_API_KEY": "", "BYBIT_DEMO_API_SECRET": "   "}
        result = discover_credentials(environ=env)
        assert result.status == DiscoveryStatus.BLOCKED_CREDENTIALS_MISSING


class TestCredentialNameMismatch:
    """Category 3: Alt names present but expected missing → BLOCKED_CREDENTIAL_NAME_MISMATCH."""

    @pytest.mark.parametrize(
        "alt_key,alt_secret",
        [
            ("BYBIT_M0_API_KEY", "BYBIT_M0_API_SECRET"),
            ("BYBIT_API_KEY", "BYBIT_API_SECRET"),
            ("NEXUS_BYBIT_API_KEY", "NEXUS_BYBIT_API_SECRET"),
        ],
    )
    def test_alt_names_trigger_mismatch(self, alt_key, alt_secret):
        from backend.nexus_research.demo_exchange.discovery import (
            DiscoveryStatus,
            discover_credentials,
        )

        env = {alt_key: "alt_k", alt_secret: "alt_s"}
        result = discover_credentials(environ=env)
        assert result.status == DiscoveryStatus.BLOCKED_CREDENTIAL_NAME_MISMATCH
        assert result.alternate_key_detected is True or result.alternate_secret_detected is True

    def test_alt_key_only(self):
        from backend.nexus_research.demo_exchange.discovery import (
            DiscoveryStatus,
            discover_credentials,
        )

        env = {"BYBIT_API_KEY": "val"}
        result = discover_credentials(environ=env)
        assert result.status == DiscoveryStatus.BLOCKED_CREDENTIAL_NAME_MISMATCH

    def test_expected_present_overrides_alt(self):
        from backend.nexus_research.demo_exchange.discovery import (
            DiscoveryStatus,
            discover_credentials,
        )

        env = {
            "BYBIT_DEMO_API_KEY": "correct_k",
            "BYBIT_DEMO_API_SECRET": "correct_s",
            "BYBIT_API_KEY": "old_k",
        }
        result = discover_credentials(environ=env)
        assert result.status == DiscoveryStatus.CREDENTIAL_DETECTED_PROBE_DISABLED


class TestProbeDisabledZeroCalls:
    """Category 4: Probe disabled → zero wallet/position/order/execution calls."""

    def test_no_network_calls_ever(self):
        from backend.nexus_research.demo_exchange.discovery import discover_credentials

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {"DEMO_READONLY_PROBE_ENABLED": "false"}, clear=False):
            result = discover_credentials(environ=env)
        assert result.network_calls == 0
        assert result.private_api_call_count == 0

    def test_unset_means_disabled(self):
        from backend.nexus_research.demo_exchange.discovery import discover_credentials

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {}, clear=True):
            result = discover_credentials(environ=env)
        assert result.probe_enabled is False
        assert result.network_calls == 0

    def test_readiness_report_zero_calls(self):
        from backend.nexus_research.demo_exchange.discovery import DemoReadinessReport

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {}, clear=True):
            report = DemoReadinessReport.build(environ=env)
        d = report.to_dict()
        assert d["private_api_call_count"] == 0
        assert d["probe_enabled"] is False


class TestWriteImpossible:
    """Category 5: POST/PUT/DELETE impossible."""

    def test_write_allowed_constant_false(self):
        from backend.nexus_research.demo_exchange.constants import WRITE_ALLOWED

        assert WRITE_ALLOWED is False

    def test_discovery_write_impossible(self):
        from backend.nexus_research.demo_exchange.discovery import discover_credentials

        result = discover_credentials(environ={})
        assert result.write_impossible is True
        assert result.execution_write_allowed is False

    def test_transport_rejects_post(self):
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport
        from backend.nexus_research.demo_exchange.errors import MethodNotAllowedError

        transport = DemoReadOnlyTransport(use_fixtures=True)
        with pytest.raises(MethodNotAllowedError):
            transport.request("POST", "/v5/order/create", {})

    def test_transport_rejects_put(self):
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport
        from backend.nexus_research.demo_exchange.errors import MethodNotAllowedError

        transport = DemoReadOnlyTransport(use_fixtures=True)
        with pytest.raises(MethodNotAllowedError):
            transport.request("PUT", "/v5/order/amend", {})

    def test_transport_rejects_delete(self):
        from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport
        from backend.nexus_research.demo_exchange.errors import MethodNotAllowedError

        transport = DemoReadOnlyTransport(use_fixtures=True)
        with pytest.raises(MethodNotAllowedError):
            transport.request("DELETE", "/v5/order/cancel", {})


class TestSecretNeverExposed:
    """Category 6: Secret never in stdout/logs/exception/JSON/readiness."""

    SECRET_KEY = "SUPER_SECRET_KEY_VALUE_12345"
    SECRET_VAL = "ULTRA_SECRET_SECRET_VALUE_67890"

    def test_discovery_dict_no_secret_values(self):
        from backend.nexus_research.demo_exchange.discovery import discover_credentials

        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        result = discover_credentials(environ=env)
        d = result.to_dict()
        serialized = json.dumps(d)
        assert self.SECRET_KEY not in serialized
        assert self.SECRET_VAL not in serialized

    def test_readiness_report_no_secret_values(self):
        from backend.nexus_research.demo_exchange.discovery import DemoReadinessReport

        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        with patch.dict("os.environ", {}, clear=True):
            report = DemoReadinessReport.build(environ=env)
        serialized = json.dumps(report.to_dict())
        assert self.SECRET_KEY not in serialized
        assert self.SECRET_VAL not in serialized

    def test_credential_presence_no_secret_values(self):
        from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator

        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        v = DemoCredentialPresenceValidator(environ=env)
        presence = v.validate()
        d = presence.to_public_dict()
        serialized = json.dumps(d)
        assert self.SECRET_KEY not in serialized
        assert self.SECRET_VAL not in serialized

    def test_no_secrets_in_stdout(self, capsys):
        from backend.nexus_research.demo_exchange.discovery import discover_credentials

        env = {"BYBIT_DEMO_API_KEY": self.SECRET_KEY, "BYBIT_DEMO_API_SECRET": self.SECRET_VAL}
        discover_credentials(environ=env)
        captured = capsys.readouterr()
        assert self.SECRET_KEY not in captured.out
        assert self.SECRET_VAL not in captured.out
        assert self.SECRET_KEY not in captured.err
        assert self.SECRET_VAL not in captured.err

    def test_exception_messages_redacted(self):
        from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator

        env = {"BYBIT_DEMO_API_KEY": "", "BYBIT_DEMO_API_SECRET": ""}
        v = DemoCredentialPresenceValidator(environ=env)
        from backend.nexus_research.demo_exchange.errors import CredentialMissingError

        with pytest.raises(CredentialMissingError) as exc_info:
            v.validate(require=True)
        assert self.SECRET_KEY not in str(exc_info.value)
        assert self.SECRET_VAL not in str(exc_info.value)


class TestPaperLedgerUnaffected:
    """Category 7: PAPER/Ledger unaffected."""

    def test_account_separation(self):
        from backend.nexus_research.demo_exchange.constants import (
            ACCOUNT_BYBIT_DEMO,
            ACCOUNT_PAPER_MAIN_V1,
        )

        assert ACCOUNT_BYBIT_DEMO != ACCOUNT_PAPER_MAIN_V1
        assert ACCOUNT_PAPER_MAIN_V1 == "NEXUS_PAPER_MAIN_V1"
        assert ACCOUNT_BYBIT_DEMO == "BYBIT_DEMO_ACCOUNT"

    def test_identity_boundary_rejects_cross(self):
        from backend.nexus_research.demo_exchange.identity import AccountBoundary
        from backend.nexus_research.demo_exchange.constants import (
            ACCOUNT_BYBIT_DEMO,
            ACCOUNT_PAPER_MAIN_V1,
        )

        boundary = AccountBoundary()
        boundary.assert_demo_identity(ACCOUNT_BYBIT_DEMO)
        with pytest.raises(Exception):
            boundary.assert_demo_identity(ACCOUNT_PAPER_MAIN_V1)

    def test_discovery_does_not_import_ledger(self):
        import importlib
        import backend.nexus_research.demo_exchange.discovery as disc_mod

        importlib.reload(disc_mod)
        source = disc_mod.__file__
        with open(source, "r", encoding="utf-8") as f:
            content = f.read()
        assert "ledger" not in content.lower()
        assert "paper_balance" not in content.lower()


class TestReadinessEndpointContract:
    """Verify the readiness report JSON contract matches spec."""

    def test_readiness_report_fields(self):
        from backend.nexus_research.demo_exchange.discovery import DemoReadinessReport

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        with patch.dict("os.environ", {}, clear=True):
            report = DemoReadinessReport.build(environ=env)
        d = report.to_dict()
        assert "status" in d
        assert "probe_enabled" in d
        assert d["probe_enabled"] is False
        assert "private_api_call_count" in d
        assert d["private_api_call_count"] == 0
        assert "write_impossible" in d
        assert d["write_impossible"] is True
        assert "execution_write_allowed" in d
        assert d["execution_write_allowed"] is False

    def test_discovery_result_fields(self):
        from backend.nexus_research.demo_exchange.discovery import discover_credentials

        env = {"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        result = discover_credentials(environ=env)
        d = result.to_dict()
        required = {
            "status", "probe_enabled", "key_present", "secret_present",
            "alternate_key_detected", "alternate_secret_detected",
            "private_api_call_count", "write_impossible",
            "execution_write_allowed", "network_calls", "checked_at_ms",
        }
        assert required.issubset(set(d.keys()))
