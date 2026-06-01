"""Tests for Pure AI verifiable status."""

import os
import unittest
from unittest.mock import MagicMock

os.environ["NEXUS_PURE_AI_MODE"] = "1"
os.environ["NEXUS_TESTNET_SANDBOX"] = "1"
os.environ["NEXUS_RULE_SIGNAL_BRIDGE"] = "0"

from backend.autonomy.pure_ai_status import build_pure_ai_status


class PureAiStatusTests(unittest.TestCase):
    def test_build_status_includes_verification_checks(self):
        runtime = MagicMock()
        runtime.llm_status = {"enabled": True, "models": {"flex_trade_eval": "test-model"}}
        runtime._last_pure_ai_cycle = {"mode": "pure_ai", "entry_count": 1, "entry_proposals": []}
        runtime._last_entry_pipeline = {"mode": "pure_ai", "executed": 0}
        runtime._last_ai_flex_exit_eval = {"mode": "pure_ai", "action_count": 0}
        status = build_pure_ai_status(runtime)
        self.assertTrue(status["active"])
        self.assertEqual(status["pipeline"]["mode"], "pure_ai")
        self.assertGreaterEqual(len(status["verification_checks"]), 5)
        self.assertIn("explanation", status)


if __name__ == "__main__":
    unittest.main()
