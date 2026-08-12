"""Runtime federation counters — prove write attempts stay at zero."""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_counters = {
    "federation_get_count": 0,
    "federation_write_attempt_count": 0,
    "ssrf_block_count": 0,
    "schema_mismatch_count": 0,
    "service_timeout_count": 0,
    "circuit_open_count": 0,
    "secret_redaction_count": 0,
}


def reset_counters() -> None:
    with _lock:
        for k in _counters:
            _counters[k] = 0


def incr(name: str, amount: int = 1) -> None:
    with _lock:
        if name in _counters:
            _counters[name] += amount


def snapshot() -> dict[str, Any]:
    with _lock:
        out = dict(_counters)
    out["federation_write_attempt_count_ok"] = out["federation_write_attempt_count"] == 0
    return out
