"""In-process, read-only event emission for the alpha WebSocket endpoint."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from backend.nexus_event_contract import event_envelope


class RuntimeEventEmitter:
    """Sequenced runtime-health events with reconnect cursor and ID dedupe."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._sequence = 0
        self._seen: set[str] = set()

    def emit_runtime_health(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            event_id = str(uuid.uuid4())
            self._seen.add(event_id)
            return event_envelope(
                event_id=event_id,
                event_type="runtime.health",
                occurred_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                sequence=self._sequence,
                payload=payload,
            )

    def is_duplicate(self, event_id: str) -> bool:
        with self._lock:
            return event_id in self._seen
