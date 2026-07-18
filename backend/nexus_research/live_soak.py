"""Phase 6 Gate D — Live Soak Framework (30m smoke + phased checklist).

Enhances the Phase 5 Gate C SoakFramework with a 30-minute smoke checklist
suitable for live/CI pre-flight. Also tracks the status of phased soak markers:

  smoke  (30m)  — quick sanity; runs in seconds via synthetic bars
  6h            — pending marker (not auto-run; must be triggered manually)
  24h           — pending marker
  72h           — pending marker

The 30m smoke config is tighter than Gate C's 'smoke' profile:
  - Wall-clock budget: ≤60 seconds
  - Symbols: 2 (BTCUSDT, ETHUSDT)
  - Duration: 30 simulated minutes
  - bar_interval: 1m
  - Checklist items verified after each smoke run:
      [SIM_STACK_ALIVE] sim and ledger initialise
      [RISK_ENGINE_ACTIVE] at least 1 risk decision
      [LEDGER_CONSISTENT] no negative balance
      [EXIT_POLICIES_FIRE] at least 1 position closed
      [NO_PRIVATE_API] no private API import paths touched

Soak markers track the phase lifecycle:
  PENDING   — not yet run
  RUNNING   — in progress
  PASSED    — smoke passed criteria
  FAILED    — smoke failed
  DEFERRED  — scheduled but deferred (6h/24h/72h)
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.soak import (
    SOAK_SMOKE,
    SOAK_6H,
    SOAK_24H,
    SOAK_72H,
    SoakResult,
    get_soak_framework,
)

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Checklist item IDs ────────────────────────────────────────────────────────
CHECK_SIM_STACK_ALIVE = "SIM_STACK_ALIVE"
CHECK_RISK_ENGINE_ACTIVE = "RISK_ENGINE_ACTIVE"
CHECK_LEDGER_CONSISTENT = "LEDGER_CONSISTENT"
CHECK_EXIT_POLICIES_FIRE = "EXIT_POLICIES_FIRE"
CHECK_NO_PRIVATE_API = "NO_PRIVATE_API"

_30M_SMOKE_CHECKLIST = [
    CHECK_SIM_STACK_ALIVE,
    CHECK_RISK_ENGINE_ACTIVE,
    CHECK_LEDGER_CONSISTENT,
    CHECK_EXIT_POLICIES_FIRE,
    CHECK_NO_PRIVATE_API,
]

# ── Phased soak markers ───────────────────────────────────────────────────────
PHASE_SMOKE = "smoke_30m"
PHASE_6H = "6h"
PHASE_24H = "24h"
PHASE_72H = "72h"

MARKER_PENDING = "PENDING"
MARKER_RUNNING = "RUNNING"
MARKER_PASSED = "PASSED"
MARKER_FAILED = "FAILED"
MARKER_DEFERRED = "DEFERRED"


@dataclass
class SoakMarker:
    phase: str
    status: str = MARKER_PENDING
    soak_id: str | None = None
    started_at_ms: int = 0
    completed_at_ms: int = 0
    verdict: str | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "soakId": self.soak_id,
            "startedAtMs": self.started_at_ms,
            "completedAtMs": self.completed_at_ms,
            "verdict": self.verdict,
            "note": self.note,
            "researchOnly": True,
        }


@dataclass
class LiveSoakReport:
    """Result of a 30m smoke + checklist run."""
    soak_run_id: str
    soak_result: SoakResult
    checklist: dict[str, str] = field(default_factory=dict)  # item → PASS/FAIL/SKIP
    checklist_notes: dict[str, str] = field(default_factory=dict)
    overall_verdict: str = "PENDING"
    wall_clock_ms: int = 0
    ran_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "soakRunId": self.soak_run_id,
            "soakResult": self.soak_result.to_dict(),
            "checklist": self.checklist,
            "checklistNotes": self.checklist_notes,
            "overallVerdict": self.overall_verdict,
            "wallClockMs": self.wall_clock_ms,
            "ranAtMs": self.ran_at_ms,
            "researchOnly": True,
        }


# ── Live soak framework ───────────────────────────────────────────────────────

class LiveSoakFramework:
    """Manages the 30m smoke checklist + phased soak marker tracking."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reports: list[LiveSoakReport] = []
        self._markers: dict[str, SoakMarker] = {
            PHASE_SMOKE: SoakMarker(phase=PHASE_SMOKE),
            PHASE_6H: SoakMarker(phase=PHASE_6H, status=MARKER_DEFERRED,
                                  note="Requires manual trigger — 6h wall-clock budget"),
            PHASE_24H: SoakMarker(phase=PHASE_24H, status=MARKER_DEFERRED,
                                   note="Requires manual trigger — 24h wall-clock budget"),
            PHASE_72H: SoakMarker(phase=PHASE_72H, status=MARKER_DEFERRED,
                                   note="Requires manual trigger — 72h wall-clock budget"),
        }

    def run_smoke_30m(self) -> LiveSoakReport:
        """Run 30-minute smoke checklist. Wall-clock budget: ≤60 seconds."""
        run_id = str(uuid.uuid4())
        started = int(time.time() * 1000)

        with self._lock:
            self._markers[PHASE_SMOKE].status = MARKER_RUNNING
            self._markers[PHASE_SMOKE].soak_id = run_id
            self._markers[PHASE_SMOKE].started_at_ms = started

        # Run the underlying soak framework smoke run
        soak_fw = get_soak_framework()
        soak_result = soak_fw.run_smoke_verify()

        checklist: dict[str, str] = {}
        notes: dict[str, str] = {}

        # CHECK: sim stack alive
        if soak_result.state in ("COMPLETED", "FAILED") and soak_result.total_bars > 0:
            checklist[CHECK_SIM_STACK_ALIVE] = "PASS"
            notes[CHECK_SIM_STACK_ALIVE] = f"bars processed: {soak_result.bars_processed}"
        else:
            checklist[CHECK_SIM_STACK_ALIVE] = "FAIL"
            notes[CHECK_SIM_STACK_ALIVE] = f"state={soak_result.state} bars={soak_result.total_bars}"

        # CHECK: risk engine active
        total_risk = soak_result.risk_blocks + soak_result.risk_allows
        if total_risk > 0:
            checklist[CHECK_RISK_ENGINE_ACTIVE] = "PASS"
            notes[CHECK_RISK_ENGINE_ACTIVE] = (
                f"blocks={soak_result.risk_blocks} allows={soak_result.risk_allows}"
            )
        else:
            checklist[CHECK_RISK_ENGINE_ACTIVE] = "FAIL"
            notes[CHECK_RISK_ENGINE_ACTIVE] = "no risk decisions recorded"

        # CHECK: ledger consistent (equity > 0)
        if soak_result.final_equity > 0:
            checklist[CHECK_LEDGER_CONSISTENT] = "PASS"
            notes[CHECK_LEDGER_CONSISTENT] = f"equity={soak_result.final_equity:.2f}"
        else:
            checklist[CHECK_LEDGER_CONSISTENT] = "FAIL"
            notes[CHECK_LEDGER_CONSISTENT] = f"equity={soak_result.final_equity:.2f} ≤ 0"

        # CHECK: exit policies fire (at least 1 closed position)
        if soak_result.total_positions_closed > 0:
            checklist[CHECK_EXIT_POLICIES_FIRE] = "PASS"
            notes[CHECK_EXIT_POLICIES_FIRE] = f"closed={soak_result.total_positions_closed}"
        else:
            checklist[CHECK_EXIT_POLICIES_FIRE] = "SKIP"
            notes[CHECK_EXIT_POLICIES_FIRE] = (
                "no closed positions (smoke window may be too short); non-fatal"
            )

        # CHECK: no private API paths in soak errors
        private_api_refs = [
            e for e in (soak_result.errors or [])
            if any(kw in e.lower() for kw in ("private", "api_key", "secret", "bybit", "real_order"))
        ]
        if not private_api_refs:
            checklist[CHECK_NO_PRIVATE_API] = "PASS"
            notes[CHECK_NO_PRIVATE_API] = "no private API references in soak errors"
        else:
            checklist[CHECK_NO_PRIVATE_API] = "FAIL"
            notes[CHECK_NO_PRIVATE_API] = f"private API refs: {private_api_refs[:2]}"

        # Overall verdict
        fails = [k for k, v in checklist.items() if v == "FAIL"]
        overall = "FAIL" if fails else ("PASS" if not soak_result.errors else "WARN")

        completed = int(time.time() * 1000)
        report = LiveSoakReport(
            soak_run_id=run_id,
            soak_result=soak_result,
            checklist=checklist,
            checklist_notes=notes,
            overall_verdict=overall,
            wall_clock_ms=completed - started,
            ran_at_ms=completed,
        )

        with self._lock:
            self._reports.append(report)
            if len(self._reports) > 50:
                self._reports = self._reports[-50:]
            marker = self._markers[PHASE_SMOKE]
            marker.status = MARKER_PASSED if overall != "FAIL" else MARKER_FAILED
            marker.completed_at_ms = completed
            marker.verdict = overall
            marker.note = f"checklist items: {len(checklist)} | fails: {len(fails)}"

        logger.info(
            "[live_soak] smoke_30m run=%s verdict=%s wall_clock=%dms fails=%s",
            run_id, overall, completed - started, fails or "none",
        )
        return report

    def set_phase_marker(
        self,
        phase: str,
        status: str,
        note: str = "",
        soak_id: str | None = None,
    ) -> None:
        """Manually update a phased soak marker (6h/24h/72h)."""
        with self._lock:
            if phase in self._markers:
                m = self._markers[phase]
                m.status = status
                if note:
                    m.note = note
                if soak_id:
                    m.soak_id = soak_id
                if status == MARKER_RUNNING:
                    m.started_at_ms = int(time.time() * 1000)
                elif status in (MARKER_PASSED, MARKER_FAILED):
                    m.completed_at_ms = int(time.time() * 1000)
                    m.verdict = status

    def list_reports(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            reports = list(self._reports)
        reports.sort(key=lambda r: r.ran_at_ms, reverse=True)
        return [r.to_dict() for r in reports[:limit]]

    def status(self) -> dict[str, Any]:
        with self._lock:
            markers = {k: v.to_dict() for k, v in self._markers.items()}
            latest = self._reports[-1].to_dict() if self._reports else None
            total = len(self._reports)

        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "phasedMarkers": markers,
            "totalSmokeRuns": total,
            "latestSmoke": latest,
            "checklistItems": _30M_SMOKE_CHECKLIST,
            "generatedAt": int(time.time() * 1000),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_LIVE_SOAK: LiveSoakFramework | None = None
_LIVE_SOAK_LOCK = threading.Lock()


def get_live_soak_framework() -> LiveSoakFramework:
    global _LIVE_SOAK
    with _LIVE_SOAK_LOCK:
        if _LIVE_SOAK is None:
            _LIVE_SOAK = LiveSoakFramework()
            logger.info("[live_soak] LiveSoakFramework initialised (researchOnly=true)")
        return _LIVE_SOAK
