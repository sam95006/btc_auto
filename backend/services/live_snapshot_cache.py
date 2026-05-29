"""In-process live snapshot cache to decouple worker ticks from SQLite reads."""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Dict, Optional


class LiveSnapshotCache:
    def __init__(self):
        self._lock = threading.RLock()
        self._snapshot: Optional[Dict[str, Any]] = None
        self._version = 0
        self._updated_at = 0.0

    def put(self, snapshot: Dict[str, Any]) -> int:
        with self._lock:
            self._snapshot = copy.deepcopy(snapshot or {})
            self._version += 1
            self._updated_at = time.time()
            return self._version

    def get(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._snapshot is None:
                return None
            return copy.deepcopy(self._snapshot)

    def meta(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": self._version,
                "updated_at": self._updated_at,
                "has_data": self._snapshot is not None,
            }
