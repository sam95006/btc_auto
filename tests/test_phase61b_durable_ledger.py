"""Phase 6.1B — durable ledger + hydration tests (research-only)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class TestPhase61BDurableLedger(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="nexus_p61b_")
        os.environ["NEXUS_DATA_DIR"] = self._tmpdir
        import backend.nexus_research.storage as st
        import backend.nexus_research.durable_ledger as dl
        import backend.nexus_research.sim_ledger as sl

        st._STORE = None
        dl.reset_durable_ledger_cache()
        sl._LEDGERS.clear()
        sl._LEDGER = None

    def test_initial_deposit_once_and_hash_stable(self) -> None:
        from backend.nexus_research.durable_ledger import (
            ACCOUNT_VALIDATION_V2,
            SOURCE_VALIDATION,
            get_durable_ledger,
            reset_durable_ledger_cache,
            validate_hash_chain,
        )

        a = get_durable_ledger(ACCOUNT_VALIDATION_V2, source=SOURCE_VALIDATION)
        e1 = a.recent_events()
        self.assertEqual(len(e1), 1)
        self.assertEqual(e1[0]["eventType"], "INITIAL_DEPOSIT")
        hid = e1[0]["eventHash"]
        eid = e1[0]["eventId"]
        seq = e1[0]["sequence"]

        # Second ensure must not reseed
        r = a.ensure_initial_deposit()
        self.assertFalse(r.get("seeded"))
        self.assertEqual(len(a.recent_events()), 1)

        # Restart simulation: clear memory, reload from SQLite
        reset_durable_ledger_cache()
        b = get_durable_ledger(ACCOUNT_VALIDATION_V2, source=SOURCE_VALIDATION)
        e2 = b.recent_events()
        self.assertEqual(len(e2), 1)
        self.assertEqual(e2[0]["eventId"], eid)
        self.assertEqual(e2[0]["sequence"], seq)
        self.assertEqual(e2[0]["eventHash"], hid)
        chain = validate_hash_chain(e2)
        self.assertTrue(chain["chainValid"])
        self.assertAlmostEqual(b.cash, 10000.0)

    def test_idempotency_returns_existing(self) -> None:
        from backend.nexus_research.durable_ledger import (
            ACCOUNT_VALIDATION_V2,
            EVT_FEE_CHARGED,
            SOURCE_VALIDATION,
            get_durable_ledger,
        )

        a = get_durable_ledger(ACCOUNT_VALIDATION_V2, source=SOURCE_VALIDATION)
        r1 = a.append_event(
            event_type=EVT_FEE_CHARGED,
            amount=1.5,
            idempotency_key="fee:test:1",
            payload={"note": "t"},
        )
        r2 = a.append_event(
            event_type=EVT_FEE_CHARGED,
            amount=1.5,
            idempotency_key="fee:test:1",
            payload={"note": "t"},
        )
        self.assertTrue(r1.get("ok"))
        self.assertTrue(r2.get("deduped"))
        self.assertEqual(r1.get("eventId"), r2.get("eventId"))
        self.assertEqual(len(a.recent_events()), 2)  # deposit + one fee

    def test_validation_event_registered(self) -> None:
        from backend.nexus_research.domain_events import (
            PERSISTENCE_VALIDATION_PACK_CREATED,
            _KNOWN_TYPES,
            get_event_bus,
        )

        self.assertIn(PERSISTENCE_VALIDATION_PACK_CREATED, _KNOWN_TYPES)
        bus = get_event_bus()
        before = bus.status()["totalDlq"]
        eid = bus.publish(
            PERSISTENCE_VALIDATION_PACK_CREATED,
            {"researchOnly": True},
            idempotency_key="test-pval-reg",
        )
        self.assertIsNotNone(eid)
        self.assertEqual(bus.status()["totalDlq"], before)

    def test_review_case_hydrate(self) -> None:
        from backend.nexus_research.storage import get_research_store
        from backend.nexus_research.review_cases import ReviewCaseManager
        import time

        store = get_research_store()
        now = int(time.time() * 1000)
        store.append(
            "review_cases",
            {
                "caseId": "case-hydrate-1",
                "case_id": "case-hydrate-1",
                "symbol": "ETHUSDT",
                "direction": "LONG",
                "side": "LONG",
                "trigger": "TOP5_ENTRY",
                "status": "PENDING",
                "window": "5m",
                "createdAt": now,
                "updatedAt": now,
                "expiresAt": now + 3_600_000,
                "candidateSnapshot": {
                    "symbol": "ETHUSDT",
                    "score": 42,
                    "stage": "WATCHING",
                    "candidateId": "eth-h1",
                },
            },
        )
        store.append(
            "review_cases",
            {
                "caseId": "case-completed-1",
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "status": "COMPLETED",
                "trigger": "MANUAL_RESEARCH",
                "createdAt": now,
                "updatedAt": now,
                "expiresAt": now + 3_600_000,
                "validationType": "PERSISTENCE_VALIDATION",
                "candidateSnapshot": {
                    "validationType": "PERSISTENCE_VALIDATION",
                    "excludeFromNaturalPaperPnl": True,
                },
            },
        )
        mgr = ReviewCaseManager()
        stats = mgr.hydrate_from_store()
        self.assertGreaterEqual(stats.get("review_cases_loaded"), 1)
        listed = mgr.list_cases(limit=10)
        self.assertTrue(any(c.get("caseId") == "case-hydrate-1" for c in listed))
        # Validation/completed remain in repository, not natural working set
        self.assertIsNotNone(mgr.get_case("case-completed-1"))
        hist = mgr.list_cases(view="historical", limit=20)
        self.assertTrue(any(c.get("caseId") == "case-completed-1" for c in hist))


if __name__ == "__main__":
    unittest.main()
