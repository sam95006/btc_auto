"""Tests for Stage 4.18-P2-R1 BTC provider override (default off, BTC-only)."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from tools.research.stage4_provider_chain import resolve_provider_chain_for_symbol
from tools.research.stage4_provider_routing_config import (
    btc_provider_override_enabled,
    is_btc_provider_override_active,
    routing_config_summary,
)


class Stage418P2R1OverrideTests(unittest.TestCase):
    def tearDown(self) -> None:
        for k in (
            "STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED",
            "STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED",
            "STAGE4_BTC_PROVIDER_CHAIN",
            "STAGE4_LLM_PROVIDER_CHAIN",
            "STAGE4_PRIMARY_LLM_PROVIDER",
            "STAGE4_SECONDARY_LLM_PROVIDER",
        ):
            os.environ.pop(k, None)

    def test_override_default_off(self) -> None:
        self.assertFalse(btc_provider_override_enabled())
        self.assertFalse(is_btc_provider_override_active())
        chain = resolve_provider_chain_for_symbol("BTCUSDT")
        self.assertTrue(len(chain) >= 1)

    def test_override_requires_experiment_flag(self) -> None:
        os.environ["STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED"] = "true"
        os.environ["STAGE4_BTC_PROVIDER_CHAIN"] = "cerebras,groq"
        self.assertFalse(is_btc_provider_override_active())

    def test_btc_only_override(self) -> None:
        os.environ["STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED"] = "true"
        os.environ["STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED"] = "true"
        os.environ["STAGE4_BTC_PROVIDER_CHAIN"] = "cerebras,groq"
        os.environ["STAGE4_LLM_PROVIDER_CHAIN"] = "groq,cerebras"
        self.assertEqual(resolve_provider_chain_for_symbol("BTCUSDT"), ["cerebras", "groq"])
        self.assertEqual(resolve_provider_chain_for_symbol("ETHUSDT"), ["groq", "cerebras"])
        self.assertEqual(resolve_provider_chain_for_symbol("SOLUSDT"), ["groq", "cerebras"])
        summary = routing_config_summary()
        self.assertTrue(summary["btc_provider_override_active"])
        self.assertEqual(summary["btc_provider_chain"], "cerebras,groq")
        self.assertFalse(summary["routing_auto_change_allowed"])

    def test_no_order_paths_in_override_modules(self) -> None:
        for rel in (
            "tools/research/stage4_provider_routing_config.py",
            "tools/research/stage4_provider_chain.py",
        ):
            src = open(rel, encoding="utf-8").read()
            self.assertNotIn("place_order", src)
            self.assertNotIn("create_order", src)


if __name__ == "__main__":
    unittest.main()
