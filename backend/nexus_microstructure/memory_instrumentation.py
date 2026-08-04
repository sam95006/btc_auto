"""Process memory instrumentation for microstructure capture."""
from __future__ import annotations

import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any


def _rss_bytes() -> int:
    try:
        import psutil  # type: ignore

        return int(psutil.Process().memory_info().rss)
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            GetCurrentProcess = ctypes.windll.kernel32.GetCurrentProcess
            GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            if GetProcessMemoryInfo(GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize)
        except Exception:
            pass
    try:
        import resource  # type: ignore

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(usage) if sys.platform.startswith("win") else int(usage) * 1024
    except Exception:
        return 0


@dataclass
class MemorySampler:
    interval_s: float = 5.0
    samples: list[dict[str, Any]] = field(default_factory=list)
    _started: bool = False
    start_rss: int = 0
    start_heap: int = 0
    peak_rss: int = 0
    peak_heap: int = 0
    last_sample_at: float = 0.0

    def start(self) -> None:
        tracemalloc.start()
        self.start_rss = _rss_bytes()
        current, peak = tracemalloc.get_traced_memory()
        self.start_heap = current
        self.peak_rss = self.start_rss
        self.peak_heap = peak
        self._started = True
        self.last_sample_at = time.time()
        self.samples.append({"t": time.time(), "rss": self.start_rss, "heap": current})

    def maybe_sample(self) -> None:
        if not self._started:
            return
        now = time.time()
        if now - self.last_sample_at < self.interval_s:
            return
        rss = _rss_bytes()
        current, peak = tracemalloc.get_traced_memory()
        self.peak_rss = max(self.peak_rss, rss)
        self.peak_heap = max(self.peak_heap, peak, current)
        self.samples.append({"t": now, "rss": rss, "heap": current})
        self.last_sample_at = now

    def stop(self, *, event_count: int) -> dict[str, Any]:
        if not self._started:
            return {"memory_growth_status": "INSTRUMENTATION_FAILED"}
        self.maybe_sample()
        end_rss = _rss_bytes()
        current, peak = tracemalloc.get_traced_memory()
        end_heap = current
        self.peak_rss = max(self.peak_rss, end_rss)
        self.peak_heap = max(self.peak_heap, peak, end_heap)
        try:
            tracemalloc.stop()
        except Exception:
            pass
        if self.start_rss <= 0 and end_rss <= 0:
            return {
                "memory_growth_status": "INSTRUMENTATION_FAILED",
                "process_RSS_start_bytes": self.start_rss,
                "process_RSS_end_bytes": end_rss,
                "process_RSS_peak_bytes": self.peak_rss,
                "Python_heap_start_bytes": self.start_heap,
                "Python_heap_end_bytes": end_heap,
                "Python_heap_peak_bytes": self.peak_heap,
            }
        rss_growth = end_rss - self.start_rss
        heap_growth = end_heap - self.start_heap
        per_m = (rss_growth / (event_count / 1_000_000.0)) if event_count > 0 else None
        status = "BOUNDED"
        if per_m is None:
            status = "INSTRUMENTATION_FAILED"
        elif per_m > 200 * 1024 * 1024:
            status = "LINEAR_GROWTH_DETECTED"
        elif per_m > 50 * 1024 * 1024:
            status = "LIKELY_BOUNDED_NEEDS_LONGER_RUN"
        return {
            "process_RSS_start_bytes": self.start_rss,
            "process_RSS_end_bytes": end_rss,
            "process_RSS_peak_bytes": self.peak_rss,
            "Python_heap_start_bytes": self.start_heap,
            "Python_heap_end_bytes": end_heap,
            "Python_heap_peak_bytes": self.peak_heap,
            "RSS_growth_bytes": rss_growth,
            "RSS_growth_per_million_events": per_m,
            "heap_growth_bytes": heap_growth,
            "heap_growth_per_million_events": (heap_growth / (event_count / 1_000_000.0))
            if event_count
            else None,
            "memory_growth_status": status,
            "sample_count": len(self.samples),
        }
