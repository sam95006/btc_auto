"""Background autonomous Demo controller — non-blocking scan ownership."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AutonomousDemoHealthGate:
    ambiguous: bool = False
    daily_loss_paused: bool = False
    weekly_dd_paused: bool = False
    session_expired: bool = False
    emergency_stop: bool = False
    protection_failed: bool = False

    def allow_new_orders(self) -> tuple[bool, str | None]:
        if self.emergency_stop:
            return False, "emergency_stop"
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
        }


@dataclass
class AutonomousDemoController:
    """Single-owner scanner loop. Does not block the web runtime when started as daemon."""

    owner_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    interval_sec: float = 60.0
    health: AutonomousDemoHealthGate = field(default_factory=AutonomousDemoHealthGate)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    last_cycle: dict[str, Any] | None = None
    cycle_count: int = 0

    def start(self, cycle_fn: Callable[[], dict[str, Any]]) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()

            def _run() -> None:
                while not self._stop.is_set():
                    try:
                        ok, reason = self.health.allow_new_orders()
                        if ok:
                            self.last_cycle = cycle_fn()
                        else:
                            self.last_cycle = {"skipped": True, "reason": reason}
                        self.cycle_count += 1
                    except Exception as exc:  # noqa: BLE001
                        self.last_cycle = {"error": type(exc).__name__}
                    self._stop.wait(self.interval_sec)

            self._thread = threading.Thread(target=_run, name="autonomous-demo", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop.set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ownerId": self.owner_id,
            "intervalSec": self.interval_sec,
            "running": bool(self._thread and self._thread.is_alive()),
            "cycleCount": self.cycle_count,
            "lastCycle": self.last_cycle,
            "health": self.health.to_dict(),
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
