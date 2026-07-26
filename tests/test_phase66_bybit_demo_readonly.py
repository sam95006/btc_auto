"""Phase 6.6 — Bybit Demo READ-ONLY foundation tests (fixtures/mocks; no live writes)."""
from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.nexus_research.demo_exchange.credentials import (
    DemoCredentialPresenceValidator,
    fingerprint_secret,
)
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.errors import (
    DomainRejectedError,
    MethodNotAllowedError,
    PermissionDeniedError,
    RateLimitError,
    SignatureInvalidError,
    StaleDataError,
    TimeoutError_,
    WriteForbiddenError,
    MalformedResponseError,
    AccountIdentityMismatchError,
)
from backend.nexus_research.demo_exchange.factory import DemoPrivateClientFactory
from backend.nexus_research.demo_exchange.fixtures import (
    fixture_executions,
    fixture_open_orders,
    fixture_positions,
    fixture_wallet,
)
from backend.nexus_research.demo_exchange.identity import AccountBoundary
from backend.nexus_research.demo_exchange.readers import (
    DemoExchangeSnapshot,
    DemoExecutionReader,
    DemoOpenOrderReader,
    DemoPositionReader,
    DemoWalletReader,
)
from backend.nexus_research.demo_exchange.reconciliation import (
    DemoLedgerReconciler,
    MismatchReason,
)
from backend.nexus_research.demo_exchange.recovery import (
    DuplicateExecutionDetector,
    ExchangeSnapshotCheckpoint,
    IdempotentClientOrderIdGenerator,
    RestartRecoveryPlan,
)
from backend.nexus_research.demo_exchange.signer import DemoRequestSigner
from backend.nexus_research.demo_exchange.state_machine import (
    FORBIDDEN_STATES,
    DemoState,
    DemoStateMachine,
)
from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport


SECRET_KEY = "test-demo-key-DO-NOT-LEAK-ABC123XYZ"
SECRET_VAL = "test-demo-secret-DO-NOT-LEAK-999888"


class TestDomainPolicy(unittest.TestCase):
    def test_correct_demo_domain_accepted(self):
        p = DemoDomainPolicy("https://api-demo.bybit.com")
        self.assertEqual(p.base_url, "https://api-demo.bybit.com")

    def test_mainnet_rejected(self):
        with self.assertRaises(DomainRejectedError):
            DemoDomainPolicy("https://api.bybit.com")

    def test_testnet_rejected(self):
        with self.assertRaises(DomainRejectedError):
            DemoDomainPolicy("https://api-testnet.bybit.com")

    def test_arbitrary_domain_rejected(self):
        with self.assertRaises(DomainRejectedError):
            DemoDomainPolicy("https://evil.example.com")


class TestCredentials(unittest.TestCase):
    def test_credentials_missing(self):
        v = DemoCredentialPresenceValidator(environ={})
        p = v.validate()
        self.assertFalse(p.configured)
        self.assertEqual(p.fingerprint, "")

    def test_fingerprint_length_and_irreversible(self):
        fp = fingerprint_secret(SECRET_KEY)
        self.assertGreaterEqual(len(fp), 6)
        self.assertLessEqual(len(fp), 8)
        self.assertNotIn(SECRET_KEY, fp)
        self.assertEqual(fp, fingerprint_secret(SECRET_KEY))

    def test_configured_true(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": SECRET_KEY, "BYBIT_DEMO_API_SECRET": SECRET_VAL}
        )
        p = v.validate()
        self.assertTrue(p.configured)
        self.assertEqual(len(p.fingerprint), 8)


class TestTransportWritesImpossible(unittest.TestCase):
    def setUp(self):
        self.t = DemoReadOnlyTransport(use_fixtures=True)

    def test_post_impossible(self):
        with self.assertRaises(MethodNotAllowedError):
            self.t.post("/v5/order/create", {})

    def test_put_impossible(self):
        with self.assertRaises(MethodNotAllowedError):
            self.t.put("/x", {})

    def test_delete_impossible(self):
        with self.assertRaises(MethodNotAllowedError):
            self.t.delete("/x")

    def test_order_create_impossible(self):
        with self.assertRaises(WriteForbiddenError):
            self.t.create_order()

    def test_cancel_impossible(self):
        with self.assertRaises(WriteForbiddenError):
            self.t.cancel_order()

    def test_leverage_write_impossible(self):
        with self.assertRaises(WriteForbiddenError):
            self.t.set_leverage()

    def test_withdrawal_impossible(self):
        with self.assertRaises(WriteForbiddenError):
            self.t.withdraw()

    def test_method_post_via_request(self):
        with self.assertRaises(MethodNotAllowedError):
            self.t.request("POST", "/v5/account/wallet-balance")


class TestTransportErrors(unittest.TestCase):
    def test_invalid_signature(self):
        def boom(url, headers=None, timeout=None):
            return {"retCode": 10004, "retMsg": "error", "result": {}}

        t = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=boom,
        )
        with self.assertRaises(SignatureInvalidError):
            t.request("GET", "/v5/account/wallet-balance", {})

    def test_permission_denied(self):
        def boom(url, headers=None, timeout=None):
            return {"retCode": 10005, "retMsg": "perm", "result": {}}

        t = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=boom,
        )
        with self.assertRaises(PermissionDeniedError):
            t.request("GET", "/v5/account/wallet-balance", {})

    def test_rate_limit(self):
        def boom(url, headers=None, timeout=None):
            return {"retCode": 10006, "retMsg": "rate", "result": {}}

        t = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=boom,
        )
        with self.assertRaises(RateLimitError):
            t.request("GET", "/v5/account/wallet-balance", {})

    def test_malformed_response(self):
        def boom(url, headers=None, timeout=None):
            return "not-json{{"

        t = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=boom,
        )
        with self.assertRaises(MalformedResponseError):
            t.request("GET", "/v5/account/wallet-balance", {})

    def test_http_timeout(self):
        def boom(url, headers=None, timeout=None):
            raise TimeoutError_("http_timeout")

        t = DemoReadOnlyTransport(
            signer=DemoRequestSigner("k", "s"),
            use_fixtures=False,
            http_get=boom,
        )
        with self.assertRaises(TimeoutError_):
            t.request("GET", "/v5/account/wallet-balance", {})


class TestReaders(unittest.TestCase):
    def setUp(self):
        self.t = DemoReadOnlyTransport(use_fixtures=True)

    def test_wallet_reader(self):
        w = DemoWalletReader(self.t).read()
        self.assertGreater(w.wallet_balance, 0)
        self.assertGreater(w.available_balance, 0)

    def test_stale_wallet(self):
        t = DemoReadOnlyTransport(use_fixtures=True)

        def stale_get(method, path, params=None, fixture_kwargs=None):
            return fixture_wallet(stale=True)

        t.request = stale_get  # type: ignore[method-assign]
        with self.assertRaises(StaleDataError):
            DemoWalletReader(t, stale_ms=60_000).read(check_stale=True)

    def test_stale_position(self):
        t = DemoReadOnlyTransport(use_fixtures=True)

        def stale_get(method, path, params=None, fixture_kwargs=None):
            return fixture_positions(stale=True)

        t.request = stale_get  # type: ignore[method-assign]
        with self.assertRaises(StaleDataError):
            DemoPositionReader(t, stale_ms=60_000).read(check_stale=True)

    def test_pagination(self):
        orders = DemoOpenOrderReader(self.t).read(max_pages=2)
        self.assertGreaterEqual(len(orders), 2)

    def test_snapshot_created(self):
        snap = DemoExchangeSnapshot.capture(self.t, check_stale=True)
        self.assertEqual(snap.identity.account_id, "BYBIT_DEMO_ACCOUNT")
        self.assertIsNotNone(snap.wallet)
        self.assertTrue(snap.positions)
        self.assertTrue(snap.open_orders)
        self.assertTrue(snap.executions)


class TestDuplicatesAndIdentity(unittest.TestCase):
    def test_duplicate_execution(self):
        t = DemoReadOnlyTransport(use_fixtures=True)

        def dup_get(method, path, params=None, fixture_kwargs=None):
            if path == "/v5/execution/list":
                return fixture_executions(duplicate=True)
            return DemoReadOnlyTransport(use_fixtures=True).request(
                method, path, params, fixture_kwargs=fixture_kwargs
            )

        t.request = dup_get  # type: ignore[method-assign]
        ex = DemoExecutionReader(t).read()
        dups = DuplicateExecutionDetector().detect(ex)
        self.assertTrue(dups)

    def test_duplicated_order_record(self):
        t = DemoReadOnlyTransport(use_fixtures=True)
        snap = DemoExchangeSnapshot.capture(t)
        # inject duplicate
        if snap.open_orders:
            snap.open_orders.append(snap.open_orders[0])
        result = DemoLedgerReconciler().reconcile_demo_internal(snap)
        self.assertFalse(result.ok)
        self.assertIn(MismatchReason.ORDER_STATE, result.reasons)

    def test_symbol_mismatch(self):
        t = DemoReadOnlyTransport(use_fixtures=True)
        snap = DemoExchangeSnapshot.capture(t)
        result = DemoLedgerReconciler().reconcile_demo_internal(
            snap, expected_symbols={"ETHUSDT"}
        )
        self.assertFalse(result.ok)
        self.assertIn(MismatchReason.SYMBOL, result.reasons)

    def test_account_identity_mismatch(self):
        t = DemoReadOnlyTransport(use_fixtures=True)
        snap = DemoExchangeSnapshot.capture(t, account_id="WRONG_ACCOUNT")
        result = DemoLedgerReconciler().reconcile_demo_internal(snap)
        self.assertFalse(result.ok)
        self.assertEqual(result.reconciliation_status, "FAIL_CLOSED")
        self.assertFalse(result.execution_write_allowed)

    def test_paper_demo_boundary(self):
        b = AccountBoundary()
        self.assertNotEqual(b.PAPER.account_id, b.DEMO.account_id)
        with self.assertRaises(AccountIdentityMismatchError):
            b.assert_no_cross_write("write_demo_execution_into_paper_ledger")
        r = DemoLedgerReconciler().compare_paper_vs_demo_balances(
            paper_balance=10000.0, demo_balance=5000.0
        )
        self.assertTrue(r.ok)
        self.assertFalse(r.balances_forced_equal)
        self.assertEqual(r.status, "SKIPPED_CROSS_ACCOUNT")


class TestRecoveryAndState(unittest.TestCase):
    def test_idempotent_id(self):
        gen = IdempotentClientOrderIdGenerator()
        a = gen.generate_idempotent("intent-1")
        b = gen.generate_idempotent("intent-1")
        c = gen.generate_idempotent("intent-2")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        # never send to exchange — generator only
        self.assertTrue(a.startswith("nxd66-"))

    def test_restart_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "checkpoint.json"
            t = DemoReadOnlyTransport(use_fixtures=True)
            snap = DemoExchangeSnapshot.capture(t)
            cp = ExchangeSnapshotCheckpoint(path=path).save(snap)
            loaded = cp.load()
            self.assertEqual(loaded["snapshotId"], snap.identity.snapshot_id)
            plan = RestartRecoveryPlan().build(cp)
            self.assertIn("never_auto_submit_orders", plan.steps)
            self.assertFalse(plan.to_dict()["writeOnRestart"])

    def test_state_machine_skeleton(self):
        sm = DemoStateMachine()
        sm.enable_read_only()
        sm.begin_reconcile()
        sm.complete_reconcile(ok=True)
        self.assertEqual(sm.state, DemoState.RECONCILED)
        sm.lock_writes()
        self.assertEqual(sm.state, DemoState.WRITE_LOCKED)
        self.assertEqual(sm.write_calls, 0)
        for bad in FORBIDDEN_STATES:
            with self.assertRaises(ValueError):
                sm.transition(bad)


class TestSecretLeakage(unittest.TestCase):
    def test_no_secret_in_stdout_logs_exception_report(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        log = logging.getLogger("backend.nexus_research.demo_exchange.transport")
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        try:
            factory = DemoPrivateClientFactory(
                credential_validator=DemoCredentialPresenceValidator(
                    environ={
                        "BYBIT_DEMO_API_KEY": SECRET_KEY,
                        "BYBIT_DEMO_API_SECRET": SECRET_VAL,
                    }
                ),
                force_fixtures=True,
            )
            transport, meta = factory.create()
            transport.request("GET", "/v5/account/wallet-balance", {})
            signer = DemoRequestSigner(SECRET_KEY, SECRET_VAL)
            text_repr = repr(signer) + str(signer)
            report = {
                "credential_fingerprint": meta["credential_fingerprint"],
                "signer": text_repr,
                "meta": meta,
            }
            report_json = json.dumps(report)
            try:
                raise SignatureInvalidError(f"failed for key={SECRET_KEY}")
            except SignatureInvalidError as exc:
                sanitized = DemoCredentialPresenceValidator.sanitize_message(
                    str(exc), [SECRET_KEY, SECRET_VAL]
                )
            blob = stream.getvalue() + report_json + sanitized + text_repr
            self.assertNotIn(SECRET_KEY, blob)
            self.assertNotIn(SECRET_VAL, blob)
            self.assertNotIn(SECRET_KEY, report_json)
            self.assertNotIn(SECRET_VAL, sanitized)
        finally:
            log.removeHandler(handler)


class TestFactoryWithoutCredentials(unittest.TestCase):
    def test_fixtures_when_missing(self):
        factory = DemoPrivateClientFactory(
            credential_validator=DemoCredentialPresenceValidator(environ={}),
        )
        transport, meta = factory.create()
        self.assertFalse(meta["credential_configured"])
        self.assertTrue(transport.use_fixtures)
        snap = DemoExchangeSnapshot.capture(transport)
        self.assertIsNotNone(snap.wallet)


if __name__ == "__main__":
    unittest.main()
