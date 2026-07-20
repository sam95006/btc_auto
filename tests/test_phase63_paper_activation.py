"""Phase 6.3 — PAPER activation, ledger isolation, fail-closed controller tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestPhase63PaperActivation(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        (self.data_dir / "nexus-research").mkdir(parents=True, exist_ok=True)
        import backend.nexus_research.storage as storage_mod
        import backend.nexus_research.paper_activation as act
        from backend.nexus_research.durable_ledger import reset_durable_ledger_cache
        from backend.nexus_research.sim_ledger import reset_sim_ledger

        storage_mod._STORE = None
        act.reset_paper_activation_cache()
        reset_durable_ledger_cache()
        reset_sim_ledger()
        self._env = mock.patch.dict(
            os.environ,
            {
                "NEXUS_DATA_DIR": str(self.data_dir),
                "NEXUS_RESEARCH_STORAGE_MODE": "sqlite",
                "NEXUS_AUTONOMOUS_RESEARCH_MODE": "PAPER",
                "NEXUS_REVIEW_ENGINE_MODE": "RULES_ONLY",
                "STAGE4_APPLY_RUNTIME_PATCH": "false",
                "LIVE_TRADING": "false",
                "REAL_MONEY": "false",
                "ARM_ALLOWED": "false",
                "PRODUCTION_PROMOTION_ALLOWED": "false",
                "PRIVATE_ORDER_ENDPOINT_BLOCKED": "true",
                "MAX_LEVERAGE": "3",
                "MAX_MARGIN_USD": "20",
                "MAX_OPEN_POSITIONS": "1",
                "PAPER_ONLY": "true",
            },
            clear=False,
        )
        self._env.start()

    def tearDown(self):
        self._env.stop()
        import backend.nexus_research.storage as storage_mod
        import backend.nexus_research.paper_activation as act
        from backend.nexus_research.durable_ledger import reset_durable_ledger_cache
        from backend.nexus_research.sim_ledger import reset_sim_ledger

        try:
            storage_mod.get_research_store().close()
        except Exception:
            pass
        storage_mod._STORE = None
        act.reset_paper_activation_cache()
        reset_durable_ledger_cache()
        reset_sim_ledger()
        self._tmpdir.cleanup()

    def test_initial_deposit_once(self):
        from backend.nexus_research.paper_activation import ensure_paper_main_ledger

        a = ensure_paper_main_ledger()
        b = ensure_paper_main_ledger()
        self.assertTrue(a["ok"])
        self.assertTrue(b["ok"])
        self.assertEqual(a["initialDepositEventId"], b["initialDepositEventId"])
        self.assertTrue(a["duplicateInitialDepositAbsent"])
        self.assertTrue(b["ledgerChainValid"])
        self.assertFalse(b["seededThisCall"])

    def test_activation_idempotent_same_boot(self):
        from backend.nexus_research.paper_activation import activate_or_resume_paper_session

        with mock.patch(
            "backend.nexus_research.paper_activation.paper_preflight",
            return_value={
                "ok": True,
                "researchOnly": True,
                "privateApi": False,
                "realExecutionAllowed": False,
                "privateApiAllowed": False,
                "autonomousMode": "PAPER",
                "autonomousModeSource": "NEXUS_AUTONOMOUS_RESEARCH_MODE",
                "reviewEngineMode": "RULES_ONLY",
                "stage4RuntimePatchEffective": False,
                "startupSafetyVerdict": "SAFE_PAPER_PRECHECK",
                "reasons": [],
                "limits": {
                    "maxLeverage": {"effective": 3},
                    "maxMarginUsd": {"effective": 20},
                    "maxOpenPositions": {"effective": 1},
                },
                "preflightHash": "abc123",
                "generatedAt": 1,
            },
        ):
            first = activate_or_resume_paper_session(deployment_commit="test")
            second = activate_or_resume_paper_session(deployment_commit="test")
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["resumed"])
        self.assertEqual(
            first["session"]["activationSessionId"],
            second["session"]["activationSessionId"],
        )
        self.assertEqual(first["session"]["accountId"], "NEXUS_PAPER_MAIN_V1")

    def test_preflight_fail_pauses(self):
        from backend.nexus_research.paper_activation import activate_or_resume_paper_session

        with mock.patch(
            "backend.nexus_research.paper_activation.paper_preflight",
            return_value={
                "ok": False,
                "researchOnly": True,
                "autonomousMode": "SHADOW",
                "autonomousModeSource": "fail_closed",
                "reviewEngineMode": "RULES_ONLY",
                "stage4RuntimePatchEffective": False,
                "startupSafetyVerdict": "SAFE_SHADOW",
                "reasons": ["autonomous_mode=SHADOW"],
                "limits": {
                    "maxLeverage": {"effective": 3},
                    "maxMarginUsd": {"effective": 20},
                    "maxOpenPositions": {"effective": 1},
                },
                "preflightHash": "bad",
                "generatedAt": 1,
            },
        ):
            result = activate_or_resume_paper_session()
        self.assertFalse(result["ok"])
        self.assertEqual(result["controllerHint"], "PAPER_PAUSED")
        self.assertEqual(result["session"]["state"], "PAUSED")

    def test_v2_validation_account_isolated(self):
        from backend.nexus_research.durable_ledger import (
            ACCOUNT_VALIDATION_V2,
            ACCOUNT_PAPER_MAIN_V1,
            get_durable_ledger,
            SOURCE_VALIDATION,
            SOURCE_PAPER,
        )

        v2 = get_durable_ledger(ACCOUNT_VALIDATION_V2, source=SOURCE_VALIDATION)
        paper = get_durable_ledger(ACCOUNT_PAPER_MAIN_V1, source=SOURCE_PAPER)
        v2.ensure_initial_deposit(amount=10000)
        paper.ensure_initial_deposit(amount=10000)
        self.assertNotEqual(
            v2.snapshot().get("accountId"),
            paper.snapshot().get("accountId"),
        )


if __name__ == "__main__":
    unittest.main()
