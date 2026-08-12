"""Persistent exchange-clock watermark for Collector Cutover V2 (R2-D-003)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.constants import (
    CLOCK_WATERMARK_FILENAME,
    SCHEMA,
)


class ClockRollbackRejected(Exception):
    """Raised when exchange timestamp regresses past the persisted watermark."""

    def __init__(self, *, wall_ms: int, last_ms: int, hour: str, last_hour: str) -> None:
        self.wall_ms = wall_ms
        self.last_ms = last_ms
        self.hour = hour
        self.last_hour = last_hour
        super().__init__(
            f"BLOCKED_CLOCK_ROLLBACK: wall_ms={wall_ms} last_ms={last_ms} "
            f"hour={hour} last_hour={last_hour}"
        )


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_hour_key(exchange_ts_ms: int) -> str:
    dt = datetime.fromtimestamp(exchange_ts_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y%m%d_%H")


class PersistentClockGuard:
    """Persist last accepted exchange timestamp across process reopen.

    Reopen loads the watermark from disk and refuses regressions unless an
    explicit resume boundary has been armed.
    """

    def __init__(self, session_dir: Path, *, capture_session_id: str) -> None:
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.capture_session_id = capture_session_id
        self.path = self.session_dir / CLOCK_WATERMARK_FILENAME
        self._last_exchange_ms: int | None = None
        self._last_hour: str | None = None
        self._resume_boundary = False
        self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self.snapshot()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("capture_session_id") != self.capture_session_id:
            return self.snapshot()
        last = data.get("last_accepted_exchange_ms")
        self._last_exchange_ms = int(last) if last is not None else None
        self._last_hour = data.get("last_accepted_utc_hour")
        self._resume_boundary = bool(data.get("resume_boundary_armed", False))
        return self.snapshot()

    def arm_resume_boundary(self) -> None:
        """Allow one discontinuity after unclean stop / open-tail resume."""
        self._resume_boundary = True
        self._persist()

    def accept(self, exchange_ts_ms: int) -> str:
        """Validate and record exchange timestamp; return UTC hour key."""
        hour = utc_hour_key(exchange_ts_ms)
        ts_regress = (
            self._last_exchange_ms is not None and exchange_ts_ms < self._last_exchange_ms
        )
        hour_regress = self._last_hour is not None and hour < self._last_hour
        if ts_regress or hour_regress:
            if not self._resume_boundary:
                raise ClockRollbackRejected(
                    wall_ms=exchange_ts_ms,
                    last_ms=int(self._last_exchange_ms or 0),
                    hour=hour,
                    last_hour=str(self._last_hour),
                )
            # Consume resume fence once.
            self._resume_boundary = False
        self._last_exchange_ms = exchange_ts_ms
        self._last_hour = hour
        self._persist()
        return hour

    def _persist(self) -> None:
        body = self.snapshot()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": f"{SCHEMA}_clock_watermark",
            "capture_session_id": self.capture_session_id,
            "last_accepted_exchange_ms": self._last_exchange_ms,
            "last_accepted_utc_hour": self._last_hour,
            "resume_boundary_armed": self._resume_boundary,
            "updated_at": _utc(),
            "persistent": True,
            "process_local_only": False,
        }
