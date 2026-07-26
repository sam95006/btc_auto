"""Phase 6.6.1 — Demo Read-Only Probe Readiness tests (fixtures/mocks; no live API calls)."""
from __future__ import annotations

import json
import unittest

from backend.nexus_research.demo_exchange.credentials import (
    DemoCredentialPresenceValidator,
    fingerprint_secret,
)
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import (
    MalformedResponseError,
    MethodNotAllowedError,
    PermissionDeniedError,
    RateLimitError,
    SignatureInvalidError,
    TimeoutError_,
    WriteForbiddenError,
)
from backend.nexus_research.demo_exchange.probe_readiness import (
    CredentialConfiguredState,
    DemoConnectivityResult,
    DemoReadinessStatus,
    DemoReadOnlyProbeCommand,
    ProbeAuditRecord,
    ProbeFailClosedPolicy,
    ReadOnlyEndpointAllowlist,
    ReadOnlySnapshotReport,
)
from backend.nexus_research.demo_exchange.signer import DemoRequestSigner
from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport

SECRET_KEY = "test-probe-key-DO-NOT-LEAK-661ABC"
SECRET_VAL = "test-probe-secret-DO-NOT-LEAK-661XYZ"


class TestCredentialMissing(unittest.TestCase):
    """Probe returns BLOCKED_CREDENTIALS_MISSING when credentials absent."""

    def test_probe_blocked_no_credentials(self):
        validator = DemoCredentialPresenceValidator(environ={})
        cmd = DemoReadOnlyProbeCommand(credential_validator=validator)
        audit = cmd.execute()
        self.assertEqual(
            audit.readiness_status,
            DemoReadinessStatus.BLOCKED_CREDENTIALS_MISSING,
        )
        self.assertFalse(audit.credential_state.configured)
        self.assertGreater(audit.started_at_ms, 0)
        self.assertGreater(audit.finished_at_ms, 0)

    def test_probe_blocked_key_only(self):
        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": SECRET_KEY}
        )
        cmd = DemoReadOnlyProbeCommand(credential_validator=validator)
        audit = cmd.execute()
        self.assertEqual(
            audit.readiness_status,
            DemoReadinessStatus.BLOCKED_CREDENTIALS_MISSING,
        )

    def test_probe_blocked_secret_only(self):
        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_SECRET": SECRET_VAL}
        )
        cmd = DemoReadOnlyProbeCommand(credential_validator=validator)
        audit = cmd.execute()
        self.assertEqual(
            audit.readiness_status,
            DemoReadinessStatus.BLOCKED_CREDENTIALS_MISSING,
        )


class TestCredentialConfiguredState(unittest.TestCase):
    def test_configured_state_present(self):
        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": SECRET_KEY, "BYBIT_DEMO_API_SECRET": SECRET_VAL}
        )
        state = CredentialConfiguredState.check(validator)
        self.assertTrue(state.configured)
        self.assertEqual(state.phase, "6.6.1")
        d = state.to_dict()
        self.assertTrue(d["configured"])
        self.assertNotIn(SECRET_KEY, json.dumps(d))
        self.assertNotIn(SECRET_VAL, json.dumps(d))

    def test_configured_state_absent(self):
        state = CredentialConfiguredState.check(
            DemoCredentialPresenceValidator(environ={})
        )
        self.assertFalse(state.configured)


class TestInvalidCredential(unittest.TestCase):
    """Probe with credentials present but exchange returns signature error."""

    def test_invalid_credential_connectivity_fails(self):
        def sig_error(url, headers=None, timeout=None):
            return {"retCode": 10004, "retMsg": "invalid_sign", "result": {}}

        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": "bad", "BYBIT_DEMO_API_SECRET": "bad"}
        )
        transport = DemoReadOnlyTransport(
            signer=DemoRequestSigner("bad", "bad"),
            use_fixtures=False,
            http_get=sig_error,
        )
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        self.assertFalse(audit.connectivity.reachable)
        self.assertIn("SignatureInvalidError", audit.connectivity.error_code)


class TestInvalidSignature(unittest.TestCase):
    """Exchange rejects signature (retCode 10003)."""

    def test_signature_rejected(self):
        def sig_error(url, headers=None, timeout=None):
            return {"retCode": 10003, "retMsg": "sign_error", "result": {}}

        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        )
        transport = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=sig_error,
        )
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        self.assertFalse(audit.connectivity.reachable)
        self.assertEqual(audit.connectivity.error_code, "SignatureInvalidError")


class TestPermissionDenied(unittest.TestCase):
    """Exchange returns permission denied (retCode 10005)."""

    def test_permission_denied_probe(self):
        def perm_denied(url, headers=None, timeout=None):
            return {"retCode": 10005, "retMsg": "perm_denied", "result": {}}

        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        )
        transport = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=perm_denied,
        )
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        self.assertFalse(audit.connectivity.reachable)
        self.assertEqual(audit.connectivity.error_code, "PermissionDeniedError")


class TestTimeout(unittest.TestCase):
    """Exchange times out."""

    def test_timeout_probe(self):
        def timeout_boom(url, headers=None, timeout=None):
            raise TimeoutError_("http_timeout")

        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        )
        transport = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=timeout_boom,
        )
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        self.assertFalse(audit.connectivity.reachable)
        self.assertEqual(audit.connectivity.error_code, "TimeoutError_")


class TestRateLimit(unittest.TestCase):
    """Exchange returns rate limit (retCode 10006)."""

    def test_rate_limit_probe(self):
        def rate_boom(url, headers=None, timeout=None):
            return {"retCode": 10006, "retMsg": "rate", "result": {}}

        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        )
        transport = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=rate_boom,
        )
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        self.assertFalse(audit.connectivity.reachable)
        self.assertEqual(audit.connectivity.error_code, "RateLimitError")


class TestStaleResponse(unittest.TestCase):
    """Connectivity succeeds but response might be stale (probe doesn't check staleness itself)."""

    def test_connectivity_still_reachable_with_old_time(self):
        def stale_resp(url, headers=None, timeout=None):
            return {"retCode": 0, "retMsg": "OK", "time": 100, "result": {"list": []}}

        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        )
        transport = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=stale_resp,
        )
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        self.assertTrue(audit.connectivity.reachable)
        self.assertEqual(audit.connectivity.ret_code, 0)


class TestMalformedResponse(unittest.TestCase):
    """Exchange returns unparseable response."""

    def test_malformed_json_probe(self):
        def bad_json(url, headers=None, timeout=None):
            return "<<<not json>>>"

        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        )
        transport = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=bad_json,
        )
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        self.assertFalse(audit.connectivity.reachable)
        self.assertEqual(audit.connectivity.error_code, "MalformedResponseError")


class TestWrongAccountIdentity(unittest.TestCase):
    """Account identity is wrong — boundary check catches it."""

    def test_wrong_identity_in_fail_closed(self):
        audit = ProbeAuditRecord(started_at_ms=1)
        audit.credential_state = CredentialConfiguredState.check(
            DemoCredentialPresenceValidator(
                environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
            )
        )
        audit.connectivity = DemoConnectivityResult(reachable=True)
        audit.account_identity_ok = False
        policy = ProbeFailClosedPolicy()
        status = policy.evaluate(audit)
        self.assertEqual(status, DemoReadinessStatus.BLOCKED_IDENTITY_MISMATCH)


class TestDuplicateExecution(unittest.TestCase):
    """Duplicate execution guard in probe context."""

    def test_duplicate_probe_id_stability(self):
        a = ProbeAuditRecord(started_at_ms=12345)
        b = ProbeAuditRecord(started_at_ms=12345)
        self.assertIsInstance(a.probe_id, str)
        self.assertEqual(len(a.probe_id), 16)
        self.assertNotEqual(a.probe_id, b.probe_id)


class TestPagination(unittest.TestCase):
    """Probe with fixture transport exercises pagination via snapshot."""

    def test_fixture_probe_passes_with_pagination(self):
        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": SECRET_KEY, "BYBIT_DEMO_API_SECRET": SECRET_VAL}
        )
        transport = DemoReadOnlyTransport(use_fixtures=True)
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        self.assertEqual(audit.readiness_status, DemoReadinessStatus.PROBE_PASSED)
        self.assertTrue(audit.connectivity.reachable)
        self.assertTrue(audit.connectivity.used_fixtures)


class TestSecretRedaction(unittest.TestCase):
    """Audit record and serialization never contain raw secrets."""

    def test_no_secrets_in_audit_json(self):
        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": SECRET_KEY, "BYBIT_DEMO_API_SECRET": SECRET_VAL}
        )
        transport = DemoReadOnlyTransport(use_fixtures=True)
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        blob = json.dumps(audit.to_dict())
        self.assertNotIn(SECRET_KEY, blob)
        self.assertNotIn(SECRET_VAL, blob)

    def test_credential_state_never_leaks(self):
        state = CredentialConfiguredState.check(
            DemoCredentialPresenceValidator(
                environ={"BYBIT_DEMO_API_KEY": SECRET_KEY, "BYBIT_DEMO_API_SECRET": SECRET_VAL}
            )
        )
        blob = json.dumps(state.to_dict())
        self.assertNotIn(SECRET_KEY, blob)
        self.assertNotIn(SECRET_VAL, blob)


class TestGETAllowlist(unittest.TestCase):
    """ReadOnlyEndpointAllowlist verifies GET paths and blocks writes."""

    def test_allowed_paths_are_get_only(self):
        al = ReadOnlyEndpointAllowlist()
        for path in al.allowed_paths:
            self.assertTrue(al.is_allowed(path))
            self.assertFalse(al.is_write_endpoint(path))

    def test_write_endpoints_rejected(self):
        al = ReadOnlyEndpointAllowlist()
        write_paths = [
            "/v5/order/create",
            "/v5/order/amend",
            "/v5/order/cancel",
            "/v5/order/cancel-all",
            "/v5/position/set-leverage",
            "/v5/asset/transfer",
            "/v5/asset/withdraw",
        ]
        for path in write_paths:
            self.assertTrue(al.is_write_endpoint(path), f"should reject: {path}")
            with self.assertRaises(WriteForbiddenError):
                al.assert_allowed(path)

    def test_unknown_path_not_in_allowlist(self):
        al = ReadOnlyEndpointAllowlist()
        self.assertFalse(al.is_allowed("/v5/unknown/endpoint"))
        with self.assertRaises(WriteForbiddenError):
            al.assert_allowed("/v5/unknown/endpoint")

    def test_allowlist_serialization(self):
        al = ReadOnlyEndpointAllowlist()
        d = al.to_dict()
        self.assertTrue(d["get_only"])
        self.assertFalse(d["write_allowed"])
        self.assertIsInstance(d["allowed_paths"], list)
        self.assertGreater(len(d["allowed_paths"]), 0)


class TestWriteEndpointDenial(unittest.TestCase):
    """Write endpoints are impossible via transport and allowlist."""

    def test_transport_post_still_impossible(self):
        t = DemoReadOnlyTransport(use_fixtures=True)
        with self.assertRaises(MethodNotAllowedError):
            t.post("/v5/order/create")

    def test_transport_create_order_still_impossible(self):
        t = DemoReadOnlyTransport(use_fixtures=True)
        with self.assertRaises(WriteForbiddenError):
            t.create_order()

    def test_transport_apply_demo_money_impossible(self):
        t = DemoReadOnlyTransport(use_fixtures=True)
        with self.assertRaises(WriteForbiddenError):
            t.apply_demo_money()

    def test_allowlist_blocks_apply_demo_money(self):
        al = ReadOnlyEndpointAllowlist()
        self.assertTrue(al.is_write_endpoint("apply_demo_money"))


class TestProbeFailClosedPolicy(unittest.TestCase):
    """ProbeFailClosedPolicy evaluates audit records."""

    def test_write_attempted_blocks(self):
        audit = ProbeAuditRecord(started_at_ms=1)
        audit.write_attempted = True
        audit.credential_state = CredentialConfiguredState.check(
            DemoCredentialPresenceValidator(
                environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
            )
        )
        audit.connectivity = DemoConnectivityResult(reachable=True)
        audit.account_identity_ok = True
        status = ProbeFailClosedPolicy().evaluate(audit)
        self.assertEqual(status, DemoReadinessStatus.BLOCKED_FAIL_CLOSED)
        self.assertTrue(audit.fail_closed_enforced)

    def test_secret_leaked_blocks(self):
        audit = ProbeAuditRecord(started_at_ms=1)
        audit.secret_leaked = True
        audit.credential_state = CredentialConfiguredState.check(
            DemoCredentialPresenceValidator(
                environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
            )
        )
        audit.connectivity = DemoConnectivityResult(reachable=True)
        audit.account_identity_ok = True
        status = ProbeFailClosedPolicy().evaluate(audit)
        self.assertEqual(status, DemoReadinessStatus.BLOCKED_FAIL_CLOSED)

    def test_errors_cause_fail_closed(self):
        audit = ProbeAuditRecord(started_at_ms=1)
        audit.errors.append("something_wrong")
        audit.credential_state = CredentialConfiguredState.check(
            DemoCredentialPresenceValidator(
                environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
            )
        )
        audit.connectivity = DemoConnectivityResult(reachable=True)
        audit.account_identity_ok = True
        status = ProbeFailClosedPolicy().evaluate(audit)
        self.assertEqual(status, DemoReadinessStatus.BLOCKED_FAIL_CLOSED)

    def test_all_ok_passes(self):
        audit = ProbeAuditRecord(started_at_ms=1)
        audit.credential_state = CredentialConfiguredState.check(
            DemoCredentialPresenceValidator(
                environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
            )
        )
        audit.connectivity = DemoConnectivityResult(reachable=True)
        audit.account_identity_ok = True
        status = ProbeFailClosedPolicy().evaluate(audit)
        self.assertEqual(status, DemoReadinessStatus.PROBE_PASSED)


class TestReadOnlySnapshotReport(unittest.TestCase):
    def test_report_serialization(self):
        report = ReadOnlySnapshotReport(
            probe_id="test123",
            wallet_readable=True,
            position_readable=True,
            order_readable=True,
            execution_readable=True,
        )
        self.assertTrue(report.all_readable)
        d = report.to_dict()
        self.assertTrue(d["all_readable"])
        self.assertEqual(d["probe_id"], "test123")

    def test_report_partial_failure(self):
        report = ReadOnlySnapshotReport(
            probe_id="test456",
            wallet_readable=True,
            position_readable=False,
            order_readable=True,
            execution_readable=True,
        )
        self.assertFalse(report.all_readable)


class TestDemoConnectivityResult(unittest.TestCase):
    def test_serialization(self):
        r = DemoConnectivityResult(
            reachable=True,
            latency_ms=42,
            endpoint_tested="/v5/account/wallet-balance",
        )
        d = r.to_dict()
        self.assertTrue(d["reachable"])
        self.assertEqual(d["latency_ms"], 42)

    def test_failure_serialization(self):
        r = DemoConnectivityResult(
            reachable=False,
            error_code="TimeoutError_",
            error_detail="http_timeout",
        )
        d = r.to_dict()
        self.assertFalse(d["reachable"])
        self.assertEqual(d["error_code"], "TimeoutError_")


class TestProbeAuditRecord(unittest.TestCase):
    def test_probe_id_generated(self):
        audit = ProbeAuditRecord(started_at_ms=999)
        self.assertEqual(len(audit.probe_id), 16)

    def test_audit_serialization_complete(self):
        audit = ProbeAuditRecord(started_at_ms=1000)
        audit.credential_state = CredentialConfiguredState.check(
            DemoCredentialPresenceValidator(environ={})
        )
        audit.connectivity = DemoConnectivityResult(reachable=False)
        audit.readiness_status = DemoReadinessStatus.BLOCKED_CREDENTIALS_MISSING
        d = audit.to_dict()
        self.assertIn("probe_id", d)
        self.assertIn("credential_state", d)
        self.assertIn("connectivity", d)
        self.assertEqual(d["readiness_status"], "BLOCKED_CREDENTIALS_MISSING")


class TestDemoReadinessStatusEnum(unittest.TestCase):
    def test_all_statuses_serializable(self):
        for status in DemoReadinessStatus:
            self.assertIsInstance(status.value, str)

    def test_blocked_credentials_missing_exists(self):
        self.assertEqual(
            DemoReadinessStatus.BLOCKED_CREDENTIALS_MISSING.value,
            "BLOCKED_CREDENTIALS_MISSING",
        )


class TestFullProbeWithFixtures(unittest.TestCase):
    """End-to-end probe with fixture transport and valid credentials."""

    def test_full_probe_passes(self):
        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": SECRET_KEY, "BYBIT_DEMO_API_SECRET": SECRET_VAL}
        )
        transport = DemoReadOnlyTransport(use_fixtures=True)
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=transport,
        )
        audit = cmd.execute()
        self.assertEqual(audit.readiness_status, DemoReadinessStatus.PROBE_PASSED)
        self.assertTrue(audit.connectivity.reachable)
        self.assertTrue(audit.account_identity_ok)
        self.assertTrue(audit.endpoint_allowlist_verified)
        self.assertFalse(audit.write_attempted)
        self.assertFalse(audit.secret_leaked)
        self.assertGreater(audit.started_at_ms, 0)
        self.assertGreater(audit.finished_at_ms, 0)
        blob = json.dumps(audit.to_dict())
        self.assertNotIn(SECRET_KEY, blob)
        self.assertNotIn(SECRET_VAL, blob)

    def test_probe_without_transport_no_connectivity(self):
        validator = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": "k", "BYBIT_DEMO_API_SECRET": "s"}
        )
        cmd = DemoReadOnlyProbeCommand(
            credential_validator=validator,
            transport=None,
        )
        audit = cmd.execute()
        self.assertFalse(audit.connectivity.reachable)
        self.assertEqual(audit.connectivity.error_code, "no_transport")


class TestMainnetTestnetStillRejected(unittest.TestCase):
    """Phase 6.6 domain policy still rejects mainnet/testnet in 6.6.1 context."""

    def test_mainnet_rejected_in_probe(self):
        from backend.nexus_research.demo_exchange.errors import DomainRejectedError

        with self.assertRaises(DomainRejectedError):
            DemoDomainPolicy("https://api.bybit.com")

    def test_testnet_rejected_in_probe(self):
        from backend.nexus_research.demo_exchange.errors import DomainRejectedError

        with self.assertRaises(DomainRejectedError):
            DemoDomainPolicy("https://api-testnet.bybit.com")


if __name__ == "__main__":
    unittest.main()
