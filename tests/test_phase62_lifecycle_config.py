"""Phase 6.2 — Review case lifecycle + canonical config tests."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


class TestPhase62Config(unittest.TestCase):
    def test_default_autonomous_shadow(self):
        from backend.nexus_research.config import resolve_autonomous_mode

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NEXUS_AUTONOMOUS_RESEARCH_MODE", None)
            r = resolve_autonomous_mode()
            self.assertEqual(r["effective"], "SHADOW")
            self.assertTrue(r["isDefault"])

    def test_legacy_cannot_force_paper_when_live(self):
        from backend.nexus_research.config import resolve_autonomous_mode

        env = {
            "NEXUS_AUTONOMOUS_RESEARCH_MODE": "PAPER",
            "LIVE_TRADING": "true",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            r = resolve_autonomous_mode()
            self.assertEqual(r["effective"], "SHADOW")
            self.assertTrue(r["failClosed"])

    def test_paper_only_compatible_with_canonical_paper(self):
        from backend.nexus_research.config import resolve_autonomous_mode

        env = {
            "NEXUS_AUTONOMOUS_RESEARCH_MODE": "PAPER",
            "PAPER_ONLY": "true",
            "NEXUS_PAPER_ONLY": "1",
            "LIVE_TRADING": "false",
            "REAL_MONEY": "false",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            r = resolve_autonomous_mode()
            self.assertEqual(r["effective"], "PAPER")
            self.assertEqual(r["source"], "NEXUS_AUTONOMOUS_RESEARCH_MODE")
            self.assertFalse(r["failClosed"])
            self.assertIn("legacy_PAPER_ONLY_compatible_with_canonical_PAPER", r.get("notes") or [])

    def test_llm_assisted_fail_closed_to_rules_only(self):
        from backend.nexus_research.config import resolve_review_engine_mode

        with mock.patch.dict(os.environ, {"NEXUS_REVIEW_ENGINE_MODE": "LLM_ASSISTED"}, clear=False):
            r = resolve_review_engine_mode()
            self.assertEqual(r["effective"], "RULES_ONLY")
            self.assertTrue(r["failClosed"])

    def test_effective_config_redacts_secrets(self):
        from backend.nexus_research.config import get_effective_config

        with mock.patch.dict(
            os.environ,
            {"GROQ_API_KEY": "should-never-appear", "NEXUS_AUTONOMOUS_RESEARCH_MODE": "SHADOW"},
            clear=False,
        ):
            cfg = get_effective_config(refresh=True)
            blob = str(cfg)
            self.assertNotIn("should-never-appear", blob)
            self.assertTrue(cfg["credentials"]["groqCredentialPresent"])
            self.assertEqual(cfg["autonomousMode"]["effective"], "SHADOW")

    def test_stage4_patch_blocks_paper_precheck(self):
        from backend.nexus_research.config import compute_startup_safety_verdict

        v = compute_startup_safety_verdict(
            {
                "durableClaim": True,
                "restartProof": True,
                "runtimeOwnerCount": 1,
                "schedulerOwnerCount": 1,
                "scannerOwnerCount": 1,
                "ledgerOwnerCount": 1,
                "executionSafe": True,
                "storageHealthy": True,
                "stage4RuntimePatchEffective": True,
                "naturalActiveCapacityAvailable": True,
                "ledgerHealthy": True,
                "riskEngineHealthy": True,
                "capitalAllocatorHealthy": True,
                "simulatorHealthy": True,
                "conflicts": [],
            }
        )
        self.assertEqual(v["verdict"], "SAFE_SHADOW")
        self.assertTrue(v["stage4RuntimePatchBlocksPaper"])


class TestPhase62ReviewCases(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        (self.data_dir / "nexus-research").mkdir(parents=True, exist_ok=True)
        # Reset singletons
        import backend.nexus_research.storage as storage_mod
        import backend.nexus_research.review_cases as rc

        storage_mod._STORE = None
        rc.reset_review_case_manager_for_tests()
        self._env = mock.patch.dict(
            os.environ,
            {
                "NEXUS_DATA_DIR": str(self.data_dir),
                "NEXUS_RESEARCH_STORAGE_MODE": "sqlite",
                "NEXUS_AUTONOMOUS_RESEARCH_MODE": "SHADOW",
            },
            clear=False,
        )
        self._env.start()

    def tearDown(self):
        self._env.stop()
        import backend.nexus_research.storage as storage_mod
        import backend.nexus_research.review_cases as rc

        try:
            store = storage_mod.get_research_store()
            store.close()
        except Exception:
            pass
        storage_mod._STORE = None
        rc.reset_review_case_manager_for_tests()
        self._tmpdir.cleanup()

    def test_hydrate_bounded_and_validation_excluded(self):
        from backend.nexus_research.storage import get_research_store
        from backend.nexus_research.review_cases import (
            ReviewCaseManager,
            STATUS_PENDING,
            STATUS_COMPLETED,
        )

        store = get_research_store()
        now = int(time.time() * 1000)
        # Seed many historical PENDING (expired) + one validation COMPLETED
        for i in range(80):
            store.append(
                "review_cases",
                {
                    "caseId": f"hist-{i}",
                    "symbol": f"SYM{i}USDT",
                    "side": "LONG",
                    "direction": "LONG",
                    "status": STATUS_PENDING,
                    "trigger": "TOP5_ENTRY",
                    "window": "5m",
                    "createdAt": now - 10_000_000,
                    "updatedAt": now - 10_000_000,
                    "expiresAt": now - 5_000_000,
                    "candidateSnapshot": {"symbol": f"SYM{i}USDT", "score": i, "stage": "WATCHING"},
                    "researchOnly": True,
                },
            )
        store.append(
            "review_cases",
            {
                "caseId": "val-v2",
                "symbol": "BTCUSDT",
                "side": "LONG",
                "direction": "LONG",
                "status": STATUS_COMPLETED,
                "trigger": "MANUAL_RESEARCH",
                "window": "5m",
                "createdAt": now,
                "updatedAt": now,
                "expiresAt": now + 3_600_000,
                "validationType": "PERSISTENCE_VALIDATION",
                "candidateSnapshot": {
                    "symbol": "BTCUSDT",
                    "validationType": "PERSISTENCE_VALIDATION",
                    "validationRound": "PHASE61_RESTART_PROOF_V2",
                    "excludeFromNaturalPaperPnl": True,
                },
                "researchOnly": True,
            },
        )

        mgr = ReviewCaseManager()
        stats = mgr.hydrate_from_store(limit=50)
        self.assertTrue(stats["ok"])
        self.assertLessEqual(stats["review_cases_loaded"], 50)
        summary = mgr.status_summary()
        self.assertLessEqual(summary["naturalActive"], 50)
        self.assertEqual(summary["validationActiveExcluded"], 0)  # completed not active
        # Historical preserved in repo
        self.assertGreaterEqual(store.count("review_cases"), 81)

    def test_capacity_blocks_then_critical_displaces(self):
        from backend.nexus_research.review_cases import (
            ReviewCaseManager,
            TRIGGER_TOP5_ENTRY,
            TRIGGER_MAJOR_ANOMALY,
            TRIGGER_SCORE_CHANGE,
            _MAX_ACTIVE_CASES,
        )

        mgr = ReviewCaseManager()
        mgr.hydrate_from_store()
        with mock.patch.object(mgr, "run_instant_role_review", return_value=None):
            for i in range(_MAX_ACTIVE_CASES):
                mgr.create_case(
                    f"S{i}USDT",
                    "LONG",
                    TRIGGER_TOP5_ENTRY,
                    {
                        "symbol": f"S{i}USDT",
                        "score": i,
                        "stage": "WATCHING",
                        "candidateId": f"id-{i}",
                    },
                )
            self.assertEqual(mgr.status_summary()["naturalActive"], _MAX_ACTIVE_CASES)
            blocked = mgr.create_case(
                "LOWUSDT",
                "LONG",
                TRIGGER_SCORE_CHANGE,
                {"symbol": "LOWUSDT", "score": 1, "stage": "WATCHING", "candidateId": "low"},
            )
            self.assertIsNone(blocked)
            critical = mgr.create_case(
                "CRITUSDT",
                "LONG",
                TRIGGER_MAJOR_ANOMALY,
                {"symbol": "CRITUSDT", "score": 99, "stage": "CONFIRMED", "candidateId": "crit"},
            )
            self.assertIsNotNone(critical)
            self.assertLessEqual(mgr.status_summary()["naturalActive"], _MAX_ACTIVE_CASES)

    def test_duplicate_snapshot_updates_not_creates(self):
        from backend.nexus_research.review_cases import ReviewCaseManager, TRIGGER_TOP5_ENTRY

        mgr = ReviewCaseManager()
        mgr.hydrate_from_store()
        snap = {"symbol": "ETHUSDT", "score": 55, "stage": "WATCHING", "candidateId": "c-eth-1"}
        with mock.patch.object(mgr, "run_instant_role_review", return_value=None):
            c1 = mgr.create_case("ETHUSDT", "LONG", TRIGGER_TOP5_ENTRY, snap)
            self.assertIsNotNone(c1)
            c2 = mgr.create_case("ETHUSDT", "LONG", TRIGGER_TOP5_ENTRY, {**snap, "score": 56})
            self.assertIsNotNone(c2)
            self.assertEqual(c1.case_id, c2.case_id)
            self.assertEqual(mgr.status_summary()["naturalActive"], 1)

    def test_expiry_sweep_persists_terminal(self):
        from backend.nexus_research.storage import get_research_store
        from backend.nexus_research.review_cases import ReviewCaseManager, STATUS_PENDING, STATUS_EXPIRED

        store = get_research_store()
        now = int(time.time() * 1000)
        store.append(
            "review_cases",
            {
                "caseId": "stale-1",
                "symbol": "ADAUSDT",
                "side": "LONG",
                "direction": "LONG",
                "status": STATUS_PENDING,
                "trigger": "TOP5_ENTRY",
                "window": "5m",
                "createdAt": now - 10_000_000,
                "updatedAt": now - 10_000_000,
                "expiresAt": now - 1_000,
                "candidateSnapshot": {"symbol": "ADAUSDT", "score": 10, "candidateId": "ada"},
            },
        )
        mgr = ReviewCaseManager()
        sweep = mgr.lifecycle_sweep()
        self.assertGreaterEqual(sweep["expired"], 1)
        row = store.get_by_pk("review_cases", "stale-1")
        self.assertEqual(row["status"], STATUS_EXPIRED)


if __name__ == "__main__":
    unittest.main()
