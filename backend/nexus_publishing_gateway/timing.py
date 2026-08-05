"""Timing-leak protection — pad publish path to a minimum floor."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from backend.nexus_publishing_gateway.constants import TIMING_PAD_MS


@contextmanager
def timing_pad(min_ms: int = TIMING_PAD_MS) -> Iterator[dict[str, Any]]:
    """Ensure the enclosed block takes at least min_ms wall time.

    Equalizes fast deny vs slow serialize paths enough to blunt simple
    timing oracles on LOCAL/STAGING harnesses. Not a cryptographic
    constant-time guarantee — a deliberate floor for side-channel tests.
    """
    meta: dict[str, Any] = {"min_ms": min_ms, "padded": False, "elapsed_ms": 0.0}
    start = time.perf_counter()
    try:
        yield meta
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        remaining = min_ms - elapsed_ms
        if remaining > 0:
            time.sleep(remaining / 1000.0)
            meta["padded"] = True
        meta["elapsed_ms"] = (time.perf_counter() - start) * 1000.0


def measure_publish_times(
    fn_ok,
    fn_deny,
    *,
    samples: int = 8,
    min_ms: int = TIMING_PAD_MS,
) -> dict[str, Any]:
    """Compare padded OK vs DENY path timings for side-channel tests."""
    ok_times: list[float] = []
    deny_times: list[float] = []
    for _ in range(samples):
        with timing_pad(min_ms) as meta_ok:
            try:
                fn_ok()
            except Exception:
                pass
        ok_times.append(float(meta_ok["elapsed_ms"]))
        with timing_pad(min_ms) as meta_deny:
            try:
                fn_deny()
            except Exception:
                pass
        deny_times.append(float(meta_deny["elapsed_ms"]))

    ok_mean = sum(ok_times) / len(ok_times)
    deny_mean = sum(deny_times) / len(deny_times)
    delta = abs(ok_mean - deny_mean)
    # Allow small jitter; flag if means diverge wildly relative to pad floor.
    leak_suspected = delta > max(min_ms * 2.5, 80.0)
    return {
        "ok_mean_ms": ok_mean,
        "deny_mean_ms": deny_mean,
        "delta_ms": delta,
        "min_ms": min_ms,
        "leak_suspected": leak_suspected,
        "samples": samples,
    }
