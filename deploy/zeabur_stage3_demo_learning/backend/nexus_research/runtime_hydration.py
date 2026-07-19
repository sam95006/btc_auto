"""Phase 6.1B — Runtime hydration orchestration (research-only).

Order: ledger replay → review cases → sessions/decisions counts → report.
Does not publish CREATED events. Does not enable PAPER.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_PROFILE: dict[str, Any] | None = None


def hydrate_research_runtime() -> dict[str, Any]:
    """Run startup hydration. Safe to call multiple times."""
    global _PROFILE
    with _LOCK:
        if _PROFILE is not None:
            return dict(_PROFILE)

        profile: dict[str, Any] = {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "review_cases_loaded": 0,
            "decisions_loaded": 0,
            "review_sessions_loaded": 0,
            "sim_orders_loaded": 0,
            "sim_positions_loaded": 0,
            "ledger_events_loaded": 0,
            "expired_records_skipped": 0,
            "hydrate_duplicate_events": 0,
            "hydrate_duplicate_cases": 0,
            "hydrate_duplicate_sessions": 0,
            "ledger_chain_valid": False,
            "hydrationFailed": False,
            "steps": [],
        }

        # 1) Durable ledger (blocks paper orders if failed)
        try:
            from backend.nexus_research.durable_ledger import (
                ACCOUNT_PAPER_DEFAULT,
                get_durable_ledger,
                hydration_status,
            )
            from backend.nexus_research.sim_ledger import get_sim_ledger

            ledger = get_durable_ledger(ACCOUNT_PAPER_DEFAULT)
            snap = ledger.snapshot()
            get_sim_ledger()  # facade cache
            profile["ledger_events_loaded"] = int(snap.get("totalEvents") or 0)
            profile["ledger_chain_valid"] = bool(snap.get("ledgerChainValid"))
            hyd = hydration_status()
            profile["hydrationFailed"] = bool(hyd.get("hydrationFailed"))
            profile["steps"].append("durable_ledger: OK" if not profile["hydrationFailed"] else "durable_ledger: FAILED")
        except Exception as exc:  # noqa: BLE001
            profile["ok"] = False
            profile["hydrationFailed"] = True
            profile["steps"].append(f"durable_ledger: FAILED ({exc})")
            logger.warning("[runtime_hydration] ledger: %s", exc)

        # 2) Review cases
        try:
            from backend.nexus_research.review_cases import get_review_case_manager

            stats = get_review_case_manager().hydrate_from_store()
            profile["review_cases_loaded"] = int(stats.get("review_cases_loaded") or 0)
            profile["expired_records_skipped"] = int(stats.get("expired_records_skipped") or 0)
            profile["steps"].append("review_cases: OK")
        except Exception as exc:  # noqa: BLE001
            profile["steps"].append(f"review_cases: FAILED ({exc})")
            logger.warning("[runtime_hydration] cases: %s", exc)

        # 3) Repository counts (decisions / sessions / sim)
        try:
            from backend.nexus_research.storage import get_research_store

            store = get_research_store()
            profile["decisions_loaded"] = store.count("research_decisions")
            profile["review_sessions_loaded"] = store.count("review_sessions")
            profile["sim_orders_loaded"] = store.count("sim_orders")
            profile["sim_positions_loaded"] = store.count("sim_positions")
            profile["steps"].append("repository_counts: OK")
        except Exception as exc:  # noqa: BLE001
            profile["steps"].append(f"repository_counts: FAILED ({exc})")

        if profile["hydrationFailed"]:
            profile["ok"] = False
            # Force paper controller degraded via env-safe signal on status only.
            try:
                from backend.nexus_research.paper_controller import get_paper_controller

                ctrl = get_paper_controller()
                if hasattr(ctrl, "_state"):
                    from backend.nexus_research.paper_controller import STATE_DEGRADED

                    ctrl._state = STATE_DEGRADED
            except Exception:  # noqa: BLE001
                pass

        _PROFILE = profile
        return dict(profile)


def runtime_hydration_profile() -> dict[str, Any]:
    if _PROFILE is None:
        return hydrate_research_runtime()
    return dict(_PROFILE)
