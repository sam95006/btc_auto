"""Background autonomous Demo controller — non-blocking scan ownership."""
from __future__ import annotations

import concurrent.futures
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.nexus_research.demo_autonomous.error_sanitize import build_structured_error


@dataclass
class AutonomousDemoHealthGate:
    ambiguous: bool = False
    daily_loss_paused: bool = False
    weekly_dd_paused: bool = False
    session_expired: bool = False
    emergency_stop: bool = False
    protection_failed: bool = False
    stalled: bool = False
    stall_reason: str | None = None

    def allow_new_orders(self) -> tuple[bool, str | None]:
        if self.emergency_stop:
            return False, "emergency_stop"
        if self.stalled:
            return False, self.stall_reason or "scanner_stalled"
        if self.session_expired:
            return False, "session_expired"
        if self.ambiguous:
            return False, "ambiguous"
        if self.protection_failed:
            return False, "protection_failed"
        if self.daily_loss_paused:
            return False, "daily_loss"
        if self.weekly_dd_paused:
            return False, "weekly_drawdown"
        return True, None

    def to_dict(self) -> dict[str, Any]:
        ok, reason = self.allow_new_orders()
        return {
            "allowNewOrders": ok,
            "blockReason": reason,
            "ambiguous": self.ambiguous,
            "dailyLossPaused": self.daily_loss_paused,
            "weeklyDdPaused": self.weekly_dd_paused,
            "sessionExpired": self.session_expired,
            "emergencyStop": self.emergency_stop,
            "protectionFailed": self.protection_failed,
            "stalled": self.stalled,
            "stallReason": self.stall_reason,
        }


@dataclass
class AutonomousDemoController:
    """Single-owner scanner loop. Does not block the web runtime when started as daemon."""

    owner_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    interval_sec: float = 60.0
    cycle_timeout_sec: float = 90.0
    stall_progress_sec: float = 180.0
    health: AutonomousDemoHealthGate = field(default_factory=AutonomousDemoHealthGate)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    last_cycle: dict[str, Any] | None = None
    cycle_count: int = 0
    failure_count: int = 0
    consecutive_failure_count: int = 0
    current_stage: str = "idle"
    last_cycle_started_at_ms: int | None = None
    last_cycle_completed_at_ms: int | None = None
    last_cycle_progress_at_ms: int | None = None
    last_successful_cycle_at_ms: int | None = None
    last_successful_stage: str | None = None
    current_cycle_id: str | None = None

    def mark_progress(self, stage: str) -> None:
        now = int(time.time() * 1000)
        self.current_stage = stage
        self.last_cycle_progress_at_ms = now
        self.last_successful_stage = stage

    def _refresh_stall(self) -> None:
        now = int(time.time() * 1000)
        progress = self.last_cycle_progress_at_ms or self.last_cycle_completed_at_ms
        if progress is None and self._thread and self._thread.is_alive():
            # Started but never progressed.
            started = self.last_cycle_started_at_ms or now
            if (now - started) > int(self.stall_progress_sec * 1000):
                self.health.stalled = True
                self.health.stall_reason = "no_cycle_progress"
                return
        if progress is not None and (now - int(progress)) > int(self.stall_progress_sec * 1000):
            self.health.stalled = True
            self.health.stall_reason = f"stale_progress:{self.current_stage}"
            return
        # Clear stall only when we have fresh progress within threshold.
        if progress is not None and (now - int(progress)) <= int(self.stall_progress_sec * 1000):
            if self.health.stall_reason in (
                None,
                "no_cycle_progress",
                "cycle_timeout",
            ) or str(self.health.stall_reason or "").startswith("stale_progress"):
                self.health.stalled = False
                self.health.stall_reason = None

    def start(self, cycle_fn: Callable[[], dict[str, Any]]) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()

            def _run() -> None:
                while not self._stop.is_set():
                    cycle_id = str(uuid.uuid4())
                    started = int(time.time() * 1000)
                    self.current_cycle_id = cycle_id
                    self.last_cycle_started_at_ms = started
                    self.mark_progress("cycle_start")
                    try:
                        ok, reason = self.health.allow_new_orders()
                        # Stall still blocks new entries, but keep cycling for recovery/observability.
                        if not ok and reason not in (
                            "scanner_stalled",
                            "no_cycle_progress",
                            "cycle_timeout",
                        ) and not str(reason or "").startswith("stale_progress"):
                            self.last_cycle = {
                                "skipped": True,
                                "reason": reason,
                                "cycle_id": cycle_id,
                            }
                            self.cycle_count += 1
                            self.last_cycle_completed_at_ms = int(time.time() * 1000)
                            self.mark_progress("skipped")
                        else:
                            pool = concurrent.futures.ThreadPoolExecutor(
                                max_workers=1, thread_name_prefix="auto-cycle"
                            )
                            fut = pool.submit(cycle_fn)
                            try:
                                self.last_cycle = fut.result(timeout=self.cycle_timeout_sec)
                                self.consecutive_failure_count = 0
                                self.last_successful_cycle_at_ms = int(time.time() * 1000)
                                self.mark_progress("cycle_complete")
                                self.health.stalled = False
                                self.health.stall_reason = None
                            except concurrent.futures.TimeoutError:
                                self.failure_count += 1
                                self.consecutive_failure_count += 1
                                self.health.stalled = True
                                self.health.stall_reason = "cycle_timeout"
                                self.last_cycle = build_structured_error(
                                    TimeoutError(
                                        f"cycle exceeded {self.cycle_timeout_sec}s"
                                    ),
                                    stage=self.current_stage or "cycle",
                                    cycle_id=cycle_id,
                                    started_at_ms=started,
                                    failed_at_ms=int(time.time() * 1000),
                                    last_successful_stage=self.last_successful_stage,
                                    consecutive_failure_count=self.consecutive_failure_count,
                                    retryable=True,
                                )
                                self.mark_progress("cycle_timeout")
                            finally:
                                pool.shutdown(wait=False, cancel_futures=True)
                            self.cycle_count += 1
                            self.last_cycle_completed_at_ms = int(time.time() * 1000)
                    except Exception as exc:  # noqa: BLE001
                        self.failure_count += 1
                        self.consecutive_failure_count += 1
                        self.last_cycle = build_structured_error(
                            exc,
                            stage=self.current_stage or "cycle",
                            cycle_id=cycle_id,
                            started_at_ms=started,
                            failed_at_ms=int(time.time() * 1000),
                            last_successful_stage=self.last_successful_stage,
                            consecutive_failure_count=self.consecutive_failure_count,
                        )
                        self.cycle_count += 1
                        self.last_cycle_completed_at_ms = int(time.time() * 1000)
                        self.mark_progress("cycle_error")
                    self._refresh_stall()
                    self._stop.wait(self.interval_sec)

            self._thread = threading.Thread(target=_run, name="autonomous-demo", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()

    def health_label(self) -> str:
        self._refresh_stall()
        if not (self._thread and self._thread.is_alive()):
            return "STOPPED"
        if self.health.stalled:
            return "STALLED"
        return "HEALTHY"

    def to_dict(self) -> dict[str, Any]:
        self._refresh_stall()
        return {
            "ownerId": self.owner_id,
            "intervalSec": self.interval_sec,
            "cycleTimeoutSec": self.cycle_timeout_sec,
            "running": bool(self._thread and self._thread.is_alive()),
            "cycleCount": self.cycle_count,
            "failureCount": self.failure_count,
            "consecutiveFailureCount": self.consecutive_failure_count,
            "lastCycle": self.last_cycle,
            "health": self.health.to_dict(),
            "controllerHealth": self.health_label(),
            "scannerHealth": self.health_label(),
            "currentStage": self.current_stage,
            "currentCycleId": self.current_cycle_id,
            "lastCycleStartedAtMs": self.last_cycle_started_at_ms,
            "lastCycleCompletedAtMs": self.last_cycle_completed_at_ms,
            "lastCycleProgressAtMs": self.last_cycle_progress_at_ms,
            "lastSuccessfulCycleAtMs": self.last_successful_cycle_at_ms,
            "lastSuccessfulStage": self.last_successful_stage,
            "stalled": self.health.stalled,
            "stallReason": self.health.stall_reason,
            "demoOnly": True,
            "mainnetAllowed": False,
        }


_CONTROLLER: AutonomousDemoController | None = None
_CONTROLLER_LOCK = threading.Lock()


def get_autonomous_controller() -> AutonomousDemoController:
    global _CONTROLLER
    with _CONTROLLER_LOCK:
        if _CONTROLLER is None:
            _CONTROLLER = AutonomousDemoController()
        return _CONTROLLER
