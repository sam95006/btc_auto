"""Buffer decision traces and flush to SQLite on an interval (decouples tick from audit I/O)."""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional


class BatchedDecisionTraceWriter:
    def __init__(self, runtime_store, flush_seconds: float = None, max_buffer: int = None):
        self.runtime_store = runtime_store
        self.flush_seconds = float(
            flush_seconds if flush_seconds is not None else os.getenv("NEXUS_DECISION_TRACE_FLUSH_SECONDS", "300")
        )
        self.max_buffer = int(max_buffer if max_buffer is not None else os.getenv("NEXUS_DECISION_TRACE_MAX_BUFFER", "200"))
        self._buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_flush_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._flush_loop, name="decision-trace-flush", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self.flush()

    def enqueue(self, record: Dict[str, Any]) -> None:
        with self._lock:
            self._buffer.append(dict(record or {}))
            if len(self._buffer) >= self.max_buffer:
                self._flush_locked()

    def flush(self) -> int:
        with self._lock:
            return self._flush_locked()

    def _flush_locked(self) -> int:
        if not self._buffer:
            return 0
        batch = list(self._buffer)
        self._buffer.clear()
        writer = getattr(self.runtime_store, "append_decision_traces_batch", None)
        if callable(writer):
            writer(batch)
        else:
            for row in batch:
                self.runtime_store.append_decision_trace(row)
        self._last_flush_at = time.time()
        return len(batch)

    def _flush_loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(max(5.0, self.flush_seconds))
            if self._stop.is_set():
                break
            self.flush()

    def pending_count(self) -> int:
        with self._lock:
            return len(self._buffer)
