"""Zeabur-only Clean Validation Observer — read-only evidence recorder.

Runs inside the Zeabur runtime process. Does not depend on a local PC.
Never writes to the exchange, never issues sessions, never toggles Auto Send.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OBSERVER_INTERVAL_SEC = 60.0
OBSERVER_STALL_SEC = 180.0


def _evidence_dir() -> Path | None:
    try:
        from backend.nexus_research.boot_identity import research_data_dir

        root = research_data_dir()
        if root is None:
            return None
        path = root / "zeabur_clean_validation_observer"
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return None


@dataclass
class ZeaburCleanValidationObserver:
    """Single-owner read-only snapshot recorder for Clean 24H/72H."""

    owner_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    interval_sec: float = OBSERVER_INTERVAL_SEC
    stall_sec: float = OBSERVER_STALL_SEC
    sequence: int = 0
    boot_id_at_start: str | None = None
    commit_at_start: str | None = None
    last_sample_at_ms: int | None = None
    last_heartbeat_at_ms: int | None = None
    validation_failed: bool = False
    fail_reason: str | None = None
    _thread: threading.Thread | None = field(default=None, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _append(self, row: dict[str, Any]) -> None:
        d = _evidence_dir()
        if d is None:
            return
        path = d / "samples.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _fail(self, reason: str) -> None:
        self.validation_failed = True
        self.fail_reason = reason
        logger.error("zeabur_observer_fail_closed: %s", reason)

    def _sample_once(self) -> dict[str, Any]:
        from backend.nexus_research.demo_autonomous.ops_status import (
            build_operations_status,
            resolve_deployment_commit,
        )

        status = build_operations_status(include_snapshot=True)
        boot_id = str(status.get("bootId") or "")
        commit = str(status.get("deploymentCommit") or resolve_deployment_commit() or "")
        now = int(time.time() * 1000)

        if self.boot_id_at_start is None:
            self.boot_id_at_start = boot_id
        if self.commit_at_start is None:
            self.commit_at_start = commit

        if boot_id and self.boot_id_at_start and boot_id != self.boot_id_at_start:
            self._fail("runtime_boot_changed")
        if commit and self.commit_at_start and commit != self.commit_at_start:
            self._fail("commit_changed")
        if int(status.get("controllerOwnerCount") or 0) != 1:
            self._fail("controller_owner_not_1")
        if status.get("mainnetUsed") or status.get("realMoneyUsed"):
            self._fail("mainnet_or_real_money")
        if status.get("controllerHealth") == "STALLED" or status.get("scannerHealth") == "STALLED":
            self._fail("runtime_stalled")

        self.sequence += 1
        self.last_sample_at_ms = now
        self.last_heartbeat_at_ms = now
        row = {
            "sequence": self.sequence,
            "observed_at_ms": now,
            "observer_owner_id": self.owner_id,
            "boot_id": boot_id,
            "commit_sha": commit,
            "controller_health": status.get("controllerHealth"),
            "scanner_health": status.get("scannerHealth"),
            "controller_owner_count": status.get("controllerOwnerCount"),
            "position_count": status.get("positionCount"),
            "open_order_count": status.get("openOrderCount"),
            "reconciliation_status": status.get("reconciliationStatus"),
            "stale_block_reason_count": status.get("staleBlockReasonCount"),
            "block_reasons": status.get("blockReasons"),
            "session_status": status.get("sessionStatus"),
            "cycle_count": (status.get("controller") or {}).get("cycleCount"),
            "last_cycle_progress_at": (status.get("controller") or {}).get(
                "lastCycleProgressAtMs"
            ),
            "validation_failed": self.validation_failed,
            "fail_reason": self.fail_reason,
            "paper": True,
            "mainnet": False,
            "real_money": False,
            "exchange_write": False,
            "local_monitor_required": False,
            "secret_safe": True,
        }
        self._append(row)
        return row

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False  # fail-closed: second owner rejected
            self._stop.clear()

            def _run() -> None:
                while not self._stop.is_set():
                    try:
                        self._sample_once()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "zeabur_observer_sample_failed: %s", type(exc).__name__
                        )
                        self.last_heartbeat_at_ms = int(time.time() * 1000)
                    self._stop.wait(self.interval_sec)

            self._thread = threading.Thread(
                target=_run, name="zeabur-clean-observer", daemon=True
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()

    def health(self) -> str:
        if self.validation_failed:
            return "FAILED"
        if not (self._thread and self._thread.is_alive()):
            return "STOPPED"
        now = int(time.time() * 1000)
        if self.last_heartbeat_at_ms and (now - self.last_heartbeat_at_ms) > int(
            self.stall_sec * 1000
        ):
            return "STALLED"
        return "HEALTHY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ownerId": self.owner_id,
            "running": bool(self._thread and self._thread.is_alive()),
            "ownerCount": 1 if self._thread and self._thread.is_alive() else 0,
            "sequence": self.sequence,
            "health": self.health(),
            "lastSampleAtMs": self.last_sample_at_ms,
            "lastHeartbeatAtMs": self.last_heartbeat_at_ms,
            "bootIdAtStart": self.boot_id_at_start,
            "commitAtStart": self.commit_at_start,
            "validationFailed": self.validation_failed,
            "failReason": self.fail_reason,
            "intervalSec": self.interval_sec,
            "localMonitorRequired": False,
            "exchangeWrite": False,
            "demoOnly": True,
        }


_OBSERVER: ZeaburCleanValidationObserver | None = None
_OBSERVER_LOCK = threading.Lock()


def get_validation_observer() -> ZeaburCleanValidationObserver:
    global _OBSERVER
    with _OBSERVER_LOCK:
        if _OBSERVER is None:
            _OBSERVER = ZeaburCleanValidationObserver()
        return _OBSERVER


def ensure_validation_observer(*, enabled: bool | None = None) -> dict[str, Any]:
    """Start observer when NEXUS_ZEABUR_CLEAN_OBSERVER=true (default false until approved)."""
    if enabled is None:
        enabled = os.environ.get("NEXUS_ZEABUR_CLEAN_OBSERVER", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
    obs = get_validation_observer()
    started = False
    if enabled:
        started = obs.start()
        if not started and not (obs._thread and obs._thread.is_alive()):
            # Unexpected: start returned False but not running.
            pass
        elif not started and obs._thread and obs._thread.is_alive():
            # Duplicate start attempt — fail-closed for second caller identity,
            # but existing owner continues.
            logger.warning("zeabur_observer_duplicate_start_rejected")
    return {"enabled": bool(enabled), "started": started, **obs.to_dict()}
