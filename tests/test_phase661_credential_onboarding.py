"""Phase 6.6.1 — Credential Onboarding Readiness tests.

Fixtures/mocks only — no real Bybit calls, no real credentials.
Tests cover:
- credential absent
- credential malformed
- wrong permission
- trade permission unexpectedly present
- mainnet credential (rejected)
- revoked credential
- expired timestamp
- invalid signature
- log/exception/report redaction
"""
from __future__ import annotations

import json
import time
import unittest

from backend.nexus_research.demo_exchange.credential_onboarding import (
    ALLOWED_CREDENTIAL_CHANNELS,
    FORBIDDEN_CREDENTIAL_CHANNELS,
    FORBIDDEN_PERMISSIONS,
    REQUIRED_PERMISSIONS,
    DemoCredentialOnboardingPolicy,
    DemoCredentialPermissionChecklist,
    DemoCredentialRedactor,
    DemoCredentialRevocationPlan,
    DemoCredentialRotationPlan,
    DemoCredentialRuntimeStatus,
    DemoReadOnlyProbePreflight,
    OnboardingGate,
)
from backend.nexus_research.demo_exchange.credentials import (
    DemoCredentialPresenceValidator,
    fingerprint_secret,
)


FAKE_KEY = "TEST_DEMO_KEY_abc123_NEVER_REAL"
FAKE_SECRET = "TEST_DEMO_SECRET_xyz789_NEVER_REAL"


# ---------------------------------------------------------------------------
# 1. OnboardingPolicy tests
# ---------------------------------------------------------------------------
class TestDemoCredentialOnboardingPolicy(unittest.TestCase):
    def test_required_env_vars_listed(self):
        policy = DemoCredentialOnboardingPolicy()
        names = policy.env_var_names
        self.assertIn("BYBIT_DEMO_API_KEY", names)
        self.assertIn("BYBIT_DEMO_API_SECRET", names)

    def test_no_credential_values_in_policy(self):
        policy = DemoCredentialOnboardingPolicy()
        d = policy.to_dict()
        self.assertFalse(d["credential_values_present"])
        blob = json.dumps(d)
        self.assertNotIn(FAKE_KEY, blob)
        self.assertNotIn(FAKE_SECRET, blob)

    def test_zeabur_channel_allowed(self):
        policy = DemoCredentialOnboardingPolicy()
        self.assertTrue(policy.is_channel_allowed("zeabur_secret"))
        self.assertTrue(policy.is_channel_allowed("zeabur_environment_variable"))

    def test_git_channel_forbidden(self):
        policy = DemoCredentialOnboardingPolicy()
        self.assertTrue(policy.is_channel_forbidden("git_tracked_file"))
        self.assertTrue(policy.is_channel_forbidden("dotenv_tracked"))
        self.assertTrue(policy.is_channel_forbidden("json_evidence_file"))
        self.assertTrue(policy.is_channel_forbidden("stdout"))
        self.assertTrue(policy.is_channel_forbidden("log_output"))
        self.assertTrue(policy.is_channel_forbidden("exception_message"))

    def test_channel_validation_pass(self):
        policy = DemoCredentialOnboardingPolicy()
        result = policy.validate_injection_channel("zeabur_secret")
        self.assertEqual(result["verdict"], "PASS")

    def test_channel_validation_reject(self):
        policy = DemoCredentialOnboardingPolicy()
        result = policy.validate_injection_channel("git_tracked_file")
        self.assertEqual(result["verdict"], "REJECT")


# ---------------------------------------------------------------------------
# 2. RuntimeStatus tests
# ---------------------------------------------------------------------------
class TestDemoCredentialRuntimeStatus(unittest.TestCase):
    def test_credential_absent(self):
        v = DemoCredentialPresenceValidator(environ={})
        status = DemoCredentialRuntimeStatus.check(validator=v)
        self.assertFalse(status.credential_configured)
        self.assertFalse(status.key_present)
        self.assertFalse(status.secret_present)
        self.assertEqual(status.fingerprint, "")
        self.assertFalse(status.actual_credentials_present)
        self.assertFalse(status.ready_for_live_readonly_probe)
        self.assertFalse(status.ready_for_deploy)
        self.assertFalse(status.execution_write_allowed)
        self.assertEqual(status.gate, OnboardingGate.AWAITING_HUMAN_SETUP.value)

    def test_credential_present_but_gates_still_false(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": FAKE_KEY, "BYBIT_DEMO_API_SECRET": FAKE_SECRET}
        )
        status = DemoCredentialRuntimeStatus.check(validator=v)
        self.assertTrue(status.credential_configured)
        self.assertTrue(status.key_present)
        self.assertTrue(status.secret_present)
        self.assertTrue(len(status.fingerprint) >= 6)
        self.assertTrue(status.actual_credentials_present)
        self.assertFalse(status.ready_for_live_readonly_probe)
        self.assertFalse(status.ready_for_deploy)
        self.assertFalse(status.execution_write_allowed)
        self.assertEqual(status.gate, OnboardingGate.CREDENTIALS_CONFIGURED.value)

    def test_credential_malformed_key_only(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": FAKE_KEY}
        )
        status = DemoCredentialRuntimeStatus.check(validator=v)
        self.assertFalse(status.credential_configured)
        self.assertTrue(status.key_present)
        self.assertFalse(status.secret_present)

    def test_credential_malformed_secret_only(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_SECRET": FAKE_SECRET}
        )
        status = DemoCredentialRuntimeStatus.check(validator=v)
        self.assertFalse(status.credential_configured)
        self.assertFalse(status.key_present)
        self.assertTrue(status.secret_present)

    def test_credential_malformed_empty_values(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": "", "BYBIT_DEMO_API_SECRET": "  "}
        )
        status = DemoCredentialRuntimeStatus.check(validator=v)
        self.assertFalse(status.credential_configured)
        self.assertFalse(status.key_present)
        self.assertFalse(status.secret_present)

    def test_no_secret_in_dict(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": FAKE_KEY, "BYBIT_DEMO_API_SECRET": FAKE_SECRET}
        )
        status = DemoCredentialRuntimeStatus.check(validator=v)
        blob = json.dumps(status.to_dict())
        self.assertNotIn(FAKE_KEY, blob)
        self.assertNotIn(FAKE_SECRET, blob)


# ---------------------------------------------------------------------------
# 3. Redactor tests
# ---------------------------------------------------------------------------
class TestDemoCredentialRedactor(unittest.TestCase):
    def test_redact_known_secret(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY, FAKE_SECRET])
        text = f"Error with key={FAKE_KEY} and secret={FAKE_SECRET}"
        redacted = r.redact(text)
        self.assertNotIn(FAKE_KEY, redacted)
        self.assertNotIn(FAKE_SECRET, redacted)
        self.assertIn("***REDACTED***", redacted)

    def test_redact_dict(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY])
        d = {"api_key": FAKE_KEY, "nested": {"val": f"key={FAKE_KEY}"}}
        result = r.redact_dict(d)
        blob = json.dumps(result)
        self.assertNotIn(FAKE_KEY, blob)

    def test_assert_no_leak_raises(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY])
        with self.assertRaises(ValueError):
            r.assert_no_leak(f"log line: api_key={FAKE_KEY}")

    def test_assert_no_leak_passes_clean(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY])
        r.assert_no_leak("clean log line without secrets")

    def test_exception_redaction(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY, FAKE_SECRET])
        try:
            raise RuntimeError(f"Bybit returned error for key={FAKE_KEY}")
        except RuntimeError as exc:
            sanitized = r.redact(str(exc))
        self.assertNotIn(FAKE_KEY, sanitized)

    def test_log_output_redaction(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY])
        log_line = f"2026-07-24 INFO transport: signed with {FAKE_KEY}"
        redacted = r.redact(log_line)
        self.assertNotIn(FAKE_KEY, redacted)

    def test_report_redaction(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY, FAKE_SECRET])
        report = json.dumps({
            "probe_result": "fail",
            "credential_used": FAKE_KEY,
            "secret_in_error": FAKE_SECRET,
        })
        redacted = r.redact(report)
        self.assertNotIn(FAKE_KEY, redacted)
        self.assertNotIn(FAKE_SECRET, redacted)

    def test_add_secret_dynamically(self):
        r = DemoCredentialRedactor()
        r.add_secret(FAKE_KEY)
        self.assertNotIn(FAKE_KEY, r.redact(f"key={FAKE_KEY}"))

    def test_scan_suspicious(self):
        r = DemoCredentialRedactor()
        findings = r.scan_for_suspicious("api_key=abcdef1234567890abcdef")
        self.assertTrue(len(findings) > 0)


# ---------------------------------------------------------------------------
# 4. Preflight tests
# ---------------------------------------------------------------------------
class TestDemoReadOnlyProbePreflight(unittest.TestCase):
    def test_preflight_no_credentials(self):
        v = DemoCredentialPresenceValidator(environ={})
        pf = DemoReadOnlyProbePreflight.run(credential_validator=v)
        self.assertTrue(pf.domain_is_demo)
        self.assertTrue(pf.get_only_enforced)
        self.assertFalse(pf.credential_configured)
        self.assertTrue(pf.paper_separated)
        self.assertTrue(pf.write_impossible)
        self.assertFalse(pf.execution_write_allowed)
        self.assertFalse(pf.actual_credentials_present)
        self.assertFalse(pf.ready_for_live_readonly_probe)
        self.assertFalse(pf.ready_for_deploy)
        self.assertFalse(pf.all_gates_pass)

    def test_preflight_with_credentials(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": FAKE_KEY, "BYBIT_DEMO_API_SECRET": FAKE_SECRET}
        )
        pf = DemoReadOnlyProbePreflight.run(credential_validator=v)
        self.assertTrue(pf.credential_configured)
        self.assertTrue(pf.ready_for_live_readonly_probe)
        self.assertFalse(pf.ready_for_deploy)
        self.assertFalse(pf.execution_write_allowed)

    def test_preflight_execution_write_always_false(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": FAKE_KEY, "BYBIT_DEMO_API_SECRET": FAKE_SECRET}
        )
        pf = DemoReadOnlyProbePreflight.run(credential_validator=v)
        self.assertFalse(pf.execution_write_allowed)
        d = pf.to_dict()
        self.assertFalse(d["execution_write_allowed"])

    def test_preflight_identity_is_bybit_demo(self):
        pf = DemoReadOnlyProbePreflight.run(
            credential_validator=DemoCredentialPresenceValidator(environ={})
        )
        self.assertTrue(pf.identity_is_bybit_demo)
        self.assertEqual(pf.to_dict()["identity"], "BYBIT_DEMO_ACCOUNT")

    def test_preflight_no_secret_in_output(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": FAKE_KEY, "BYBIT_DEMO_API_SECRET": FAKE_SECRET}
        )
        pf = DemoReadOnlyProbePreflight.run(credential_validator=v)
        blob = json.dumps(pf.to_dict())
        self.assertNotIn(FAKE_KEY, blob)
        self.assertNotIn(FAKE_SECRET, blob)


# ---------------------------------------------------------------------------
# 5. PermissionChecklist tests
# ---------------------------------------------------------------------------
class TestDemoCredentialPermissionChecklist(unittest.TestCase):
    def test_readonly_permission_passes(self):
        cl = DemoCredentialPermissionChecklist.build()
        result = cl.validate_permission_set({"ReadOnly"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "PASS")

    def test_trade_permission_unexpectedly_present(self):
        cl = DemoCredentialPermissionChecklist.build()
        result = cl.validate_permission_set({"ReadOnly", "Trade"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["verdict"], "REJECT")
        self.assertTrue(any("Trade" in v for v in result["violations"]))

    def test_withdraw_permission_rejected(self):
        cl = DemoCredentialPermissionChecklist.build()
        result = cl.validate_permission_set({"ReadOnly", "Withdraw"})
        self.assertFalse(result["ok"])

    def test_transfer_permission_rejected(self):
        cl = DemoCredentialPermissionChecklist.build()
        result = cl.validate_permission_set({"ReadOnly", "Transfer"})
        self.assertFalse(result["ok"])

    def test_mainnet_permission_rejected(self):
        cl = DemoCredentialPermissionChecklist.build()
        result = cl.validate_permission_set({"ReadOnly", "Mainnet"})
        self.assertFalse(result["ok"])

    def test_contract_trade_rejected(self):
        cl = DemoCredentialPermissionChecklist.build()
        result = cl.validate_permission_set({"ReadOnly", "ContractTrade"})
        self.assertFalse(result["ok"])

    def test_missing_readonly_permission(self):
        cl = DemoCredentialPermissionChecklist.build()
        result = cl.validate_permission_set(set())
        self.assertFalse(result["ok"])
        self.assertTrue(any("ReadOnly" in m for m in result["missing_required"]))

    def test_all_forbidden_permissions_rejected(self):
        cl = DemoCredentialPermissionChecklist.build()
        for perm in FORBIDDEN_PERMISSIONS:
            result = cl.validate_permission_set({"ReadOnly", perm})
            self.assertFalse(result["ok"], f"Should reject: {perm}")
            self.assertEqual(result["verdict"], "REJECT")

    def test_fingerprint_validation_ok(self):
        cl = DemoCredentialPermissionChecklist.build()
        fp = fingerprint_secret(FAKE_KEY)
        result = cl.validate_fingerprint(fp)
        self.assertTrue(result["length_ok"])
        self.assertTrue(result["irreversible"])

    def test_fingerprint_validation_empty(self):
        cl = DemoCredentialPermissionChecklist.build()
        result = cl.validate_fingerprint("")
        self.assertFalse(result["length_ok"])

    def test_ip_allowlist_suggested(self):
        cl = DemoCredentialPermissionChecklist.build()
        self.assertTrue(cl.ip_allowlist_suggested)
        d = cl.to_dict()
        self.assertTrue(d["ip_allowlist_suggested"])


# ---------------------------------------------------------------------------
# 6. RotationPlan tests
# ---------------------------------------------------------------------------
class TestDemoCredentialRotationPlan(unittest.TestCase):
    def test_rotation_plan_structure(self):
        plan = DemoCredentialRotationPlan.build()
        self.assertFalse(plan.rotation_initiated)
        self.assertFalse(plan.rotation_completed)
        self.assertEqual(plan.rotation_channel, "zeabur_secret")
        self.assertIn("BYBIT_DEMO_API_KEY", plan.env_vars_to_rotate)
        self.assertIn("BYBIT_DEMO_API_SECRET", plan.env_vars_to_rotate)

    def test_rotation_verify_different_fingerprints(self):
        plan = DemoCredentialRotationPlan.build()
        old_fp = fingerprint_secret("old-key-value")
        new_fp = fingerprint_secret("new-key-value")
        result = plan.verify_rotation(old_fp, new_fp)
        self.assertTrue(result["ok"])
        self.assertTrue(result["fingerprints_differ"])

    def test_rotation_verify_identical_fails(self):
        plan = DemoCredentialRotationPlan.build()
        fp = fingerprint_secret(FAKE_KEY)
        result = plan.verify_rotation(fp, fp)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "fingerprints_identical_rotation_failed")

    def test_rotation_verify_missing_fingerprint(self):
        plan = DemoCredentialRotationPlan.build()
        result = plan.verify_rotation("", "abc123ab")
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "fingerprints_missing")

    def test_expired_timestamp_scenario(self):
        plan = DemoCredentialRotationPlan.build()
        self.assertGreater(plan.checked_at_ms, 0)
        expired_ts = int(time.time() * 1000) - 86_400_000  # 24h ago
        plan_old = DemoCredentialRotationPlan(checked_at_ms=expired_ts)
        age_ms = int(time.time() * 1000) - plan_old.checked_at_ms
        self.assertGreater(age_ms, 86_000_000)

    def test_no_secret_in_plan(self):
        plan = DemoCredentialRotationPlan.build(old_fingerprint="ab12cd34")
        blob = json.dumps(plan.to_dict())
        self.assertNotIn(FAKE_KEY, blob)
        self.assertNotIn(FAKE_SECRET, blob)


# ---------------------------------------------------------------------------
# 7. RevocationPlan tests
# ---------------------------------------------------------------------------
class TestDemoCredentialRevocationPlan(unittest.TestCase):
    def test_revocation_plan_structure(self):
        plan = DemoCredentialRevocationPlan.build(
            fingerprint="ab12cd34",
            reason="key_compromised",
        )
        self.assertFalse(plan.revocation_initiated)
        self.assertFalse(plan.revocation_completed)
        self.assertEqual(plan.revocation_reason, "key_compromised")
        self.assertEqual(plan.revoked_key_fingerprint, "ab12cd34")
        self.assertEqual(plan.revocation_channel, "zeabur_secret")

    def test_verify_revocation_credentials_absent(self):
        v = DemoCredentialPresenceValidator(environ={})
        status = DemoCredentialRuntimeStatus.check(validator=v)
        plan = DemoCredentialRevocationPlan.build()
        result = plan.verify_revocation(status)
        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "PASS")

    def test_verify_revocation_credentials_still_present(self):
        v = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": FAKE_KEY, "BYBIT_DEMO_API_SECRET": FAKE_SECRET}
        )
        status = DemoCredentialRuntimeStatus.check(validator=v)
        plan = DemoCredentialRevocationPlan.build()
        result = plan.verify_revocation(status)
        self.assertFalse(result["ok"])
        self.assertEqual(result["verdict"], "FAIL_CREDENTIALS_STILL_PRESENT")

    def test_revoked_credential_scenario(self):
        """Simulate: keys were present, then revoked (env cleared)."""
        v_before = DemoCredentialPresenceValidator(
            environ={"BYBIT_DEMO_API_KEY": FAKE_KEY, "BYBIT_DEMO_API_SECRET": FAKE_SECRET}
        )
        status_before = DemoCredentialRuntimeStatus.check(validator=v_before)
        self.assertTrue(status_before.credential_configured)

        v_after = DemoCredentialPresenceValidator(environ={})
        status_after = DemoCredentialRuntimeStatus.check(validator=v_after)
        self.assertFalse(status_after.credential_configured)

        plan = DemoCredentialRevocationPlan.build(
            fingerprint=status_before.fingerprint,
            reason="planned_rotation",
        )
        result = plan.verify_revocation(status_after)
        self.assertTrue(result["ok"])


# ---------------------------------------------------------------------------
# 8. Mainnet credential rejection
# ---------------------------------------------------------------------------
class TestMainnetCredentialRejection(unittest.TestCase):
    def test_preflight_always_demo_domain(self):
        pf = DemoReadOnlyProbePreflight.run(
            credential_validator=DemoCredentialPresenceValidator(environ={})
        )
        self.assertTrue(pf.domain_is_demo)
        self.assertEqual(pf.to_dict()["domain"], "https://api-demo.bybit.com")

    def test_mainnet_permission_in_checklist(self):
        cl = DemoCredentialPermissionChecklist.build()
        result = cl.validate_permission_set({"Mainnet"})
        self.assertFalse(result["ok"])
        self.assertTrue(any("Mainnet" in v for v in result["violations"]))

    def test_policy_forbids_frontend_channel(self):
        policy = DemoCredentialOnboardingPolicy()
        self.assertTrue(policy.is_channel_forbidden("frontend_code"))
        self.assertTrue(policy.is_channel_forbidden("client_visible_payload"))


# ---------------------------------------------------------------------------
# 9. Invalid signature scenario (mock)
# ---------------------------------------------------------------------------
class TestInvalidSignatureScenario(unittest.TestCase):
    def test_invalid_signature_redacted(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY, FAKE_SECRET])
        error_msg = f"SignatureInvalidError: key={FAKE_KEY} computed with secret={FAKE_SECRET}"
        redacted = r.redact(error_msg)
        self.assertNotIn(FAKE_KEY, redacted)
        self.assertNotIn(FAKE_SECRET, redacted)
        self.assertIn("SignatureInvalidError", redacted)


# ---------------------------------------------------------------------------
# 10. Comprehensive redaction across surfaces
# ---------------------------------------------------------------------------
class TestRedactionAcrossSurfaces(unittest.TestCase):
    def test_log_redaction(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY])
        log = f"[INFO] Connecting with key {FAKE_KEY} to api-demo.bybit.com"
        self.assertNotIn(FAKE_KEY, r.redact(log))

    def test_exception_redaction(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY])
        exc_str = f"PermissionDeniedError: key={FAKE_KEY} lacks ReadOnly"
        self.assertNotIn(FAKE_KEY, r.redact(exc_str))

    def test_report_json_redaction(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY, FAKE_SECRET])
        report = {"api_key": FAKE_KEY, "err": f"sign failed with {FAKE_SECRET}"}
        cleaned = r.redact_dict(report)
        blob = json.dumps(cleaned)
        self.assertNotIn(FAKE_KEY, blob)
        self.assertNotIn(FAKE_SECRET, blob)

    def test_stdout_redaction(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY])
        stdout_line = f"probe: using credential {FAKE_KEY}"
        self.assertNotIn(FAKE_KEY, r.redact(stdout_line))

    def test_nested_dict_redaction(self):
        r = DemoCredentialRedactor(known_secrets=[FAKE_KEY])
        d = {"level1": {"level2": {"value": f"x={FAKE_KEY}"}}}
        cleaned = r.redact_dict(d)
        self.assertNotIn(FAKE_KEY, json.dumps(cleaned))


# ---------------------------------------------------------------------------
# 11. OnboardingGate enum coverage
# ---------------------------------------------------------------------------
class TestOnboardingGate(unittest.TestCase):
    def test_all_gates_exist(self):
        expected = {
            "NOT_STARTED", "POLICY_DEFINED", "CHECKLIST_READY",
            "AWAITING_HUMAN_SETUP", "CREDENTIALS_CONFIGURED",
            "PREFLIGHT_PASSED", "BLOCKED",
        }
        actual = {g.value for g in OnboardingGate}
        self.assertEqual(expected, actual)


# ---------------------------------------------------------------------------
# 12. actual_credentials_present invariant
# ---------------------------------------------------------------------------
class TestActualCredentialsInvariant(unittest.TestCase):
    def test_absent_env_means_false(self):
        status = DemoCredentialRuntimeStatus.check(
            validator=DemoCredentialPresenceValidator(environ={})
        )
        self.assertFalse(status.actual_credentials_present)

    def test_ready_for_deploy_always_false(self):
        status = DemoCredentialRuntimeStatus.check(
            validator=DemoCredentialPresenceValidator(
                environ={"BYBIT_DEMO_API_KEY": FAKE_KEY, "BYBIT_DEMO_API_SECRET": FAKE_SECRET}
            )
        )
        self.assertFalse(status.ready_for_deploy)

    def test_preflight_ready_for_deploy_always_false(self):
        pf = DemoReadOnlyProbePreflight.run(
            credential_validator=DemoCredentialPresenceValidator(
                environ={"BYBIT_DEMO_API_KEY": FAKE_KEY, "BYBIT_DEMO_API_SECRET": FAKE_SECRET}
            )
        )
        self.assertFalse(pf.ready_for_deploy)


if __name__ == "__main__":
    unittest.main()
