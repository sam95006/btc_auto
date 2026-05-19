import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.audit.audit_logger import AuditLogger
from backend.security.request_validator import RequestValidationError, RequestValidator
from backend.security.secret_manager import SecretManager


class Phase0SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.temp_dir.name) / "security_audit.log"
        self.audit_logger = AuditLogger(log_path=str(self.log_path))
        self.env_patch = patch.dict(
            os.environ,
            {
                "NEXUS_READ_BINANCE_API_KEY": "read1234567890ABCD",
                "NEXUS_READ_BINANCE_SECRET_KEY": "readsecret1234567890WXYZ",
                "NEXUS_TRADE_BINANCE_API_KEY": "trade1234567890ABCD",
                "NEXUS_TRADE_BINANCE_SECRET_KEY": "tradesecret1234567890WXYZ",
                "NEXUS_EMERGENCY_BINANCE_KEY_ID": "emergency-key-001",
                "NEXUS_EMERGENCY_CONTACT": "security@nexus.local",
                "NEXUS_EMERGENCY_RUNBOOK": "vault://runbooks/emergency",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_mask_secret_masks_middle(self):
        manager = SecretManager(audit_logger=self.audit_logger)
        self.assertEqual(manager.mask_secret("abcd1234wxyz5678"), "abcd****5678")

    def test_secret_manager_logs_masked_values_only(self):
        manager = SecretManager(audit_logger=self.audit_logger)
        manager.get_read_credentials()
        contents = self.log_path.read_text(encoding="utf-8")
        self.assertNotIn("readsecret1234567890WXYZ", contents)
        self.assertNotIn("read1234567890ABCD", contents)
        self.assertIn("read****ABCD", contents)

    def test_scope_separation(self):
        manager = SecretManager(audit_logger=self.audit_logger)
        read_creds = manager.get_read_credentials()
        trade_creds = manager.get_trade_credentials()
        emergency = manager.get_emergency_metadata()
        self.assertEqual(read_creds.scope, "READ")
        self.assertEqual(trade_creds.scope, "TRADE")
        self.assertEqual(emergency["scope"], "EMERGENCY")
        self.assertNotEqual(read_creds.api_key, trade_creds.api_key)
        self.assertNotIn("api_secret", emergency)

    def test_legacy_fallback_still_works(self):
        with patch.dict(
            os.environ,
            {
                "NEXUS_READ_BINANCE_API_KEY": "",
                "NEXUS_READ_BINANCE_SECRET_KEY": "",
                "BINANCE_SPOT_TESTNET_API_KEY": "legacyread1234567890",
                "BINANCE_SPOT_TESTNET_SECRET_KEY": "legacyreadsecret1234567890",
            },
            clear=False,
        ):
            manager = SecretManager(audit_logger=self.audit_logger)
            creds = manager.get_read_credentials()
            self.assertEqual(creds.source_env_key, "BINANCE_SPOT_TESTNET_API_KEY")
            self.assertEqual(creds.scope, "READ")

    def test_nexus_env_bridges_legacy_runtime_names(self):
        with patch.dict(
            os.environ,
            {
                "BINANCE_SPOT_TESTNET_API_KEY": "",
                "BINANCE_SPOT_TESTNET_SECRET_KEY": "",
            },
            clear=False,
        ):
            manager = SecretManager(audit_logger=self.audit_logger)
            bridge_report = manager.apply_runtime_env_bridge()
            self.assertEqual(os.getenv("BINANCE_SPOT_TESTNET_API_KEY"), "read1234567890ABCD")
            self.assertEqual(bridge_report["NEXUS_READ_BINANCE_API_KEY"]["status"], "bridged_to_legacy")

    def test_request_validator_blocks_secret_payload(self):
        validator = RequestValidator(audit_logger=self.audit_logger)
        with self.assertRaises(RequestValidationError):
            validator.validate_read_request(
                {
                    "actor": "tester",
                    "resource": "balances",
                    "api_key": "read1234567890ABCD",
                }
            )

    def test_request_validator_blocks_dangerous_string(self):
        validator = RequestValidator(audit_logger=self.audit_logger)
        with self.assertRaises(RequestValidationError):
            validator.validate_admin_request(
                {
                    "actor": "tester",
                    "action": "rotate_key",
                    "justification": "run os.system('rm -rf /') now",
                }
            )

    def test_audit_logger_scrubs_sensitive_metadata(self):
        self.audit_logger.log_security_event(
            actor="tester",
            action="secret_check",
            result="ALLOW",
            metadata={"api_secret": "supersecret1234567890", "nested": {"token": "abc1234567890xyz"}},
        )
        record = json.loads(self.log_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["metadata"]["api_secret"], "supe****7890")
        self.assertEqual(record["metadata"]["nested"]["token"], "abc1****0xyz")

    def test_audit_logger_hash_chain_integrity(self):
        self.audit_logger.log_security_event(actor="tester", action="a1", result="ALLOW", metadata={"k": "v"})
        self.audit_logger.log_security_event(actor="tester", action="a2", result="ALLOW", metadata={"k": "v2"})
        self.assertTrue(self.audit_logger.verify_integrity())

        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        tampered = json.loads(lines[1])
        tampered["result"] = "DENY"
        lines[1] = json.dumps(tampered, ensure_ascii=False)
        self.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.assertFalse(self.audit_logger.verify_integrity())


if __name__ == "__main__":
    unittest.main()
