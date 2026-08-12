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

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            for dll_name, fn_name in (("kernel32", "K32GetProcessMemoryInfo"), ("psapi", "GetProcessMemoryInfo")):
                try:
                    dll = ctypes.WinDLL(dll_name, use_last_error=True)
                    fn = getattr(dll, fn_name)
                except AttributeError:
                    continue
                fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
                fn.restype = wintypes.BOOL
                if fn(handle, ctypes.byref(counters), counters.cb):
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
    # Brief heap snapshots only — continuous tracemalloc inflates RSS.
    _trace_heap: bool = False

    def start(self) -> None:
        tracemalloc.start()
        self.start_rss = _rss_bytes()
        current, peak = tracemalloc.get_traced_memory()
        self.start_heap = current
        self.peak_rss = self.start_rss
        self.peak_heap = peak
        tracemalloc.stop()
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
        self.peak_rss = max(self.peak_rss, rss)
        self.samples.append({"t": now, "rss": rss, "heap": None})
        self.last_sample_at = now

    def stop(self, *, event_count: int) -> dict[str, Any]:
        if not self._started:
            return {"memory_growth_status": "INSTRUMENTATION_FAILED"}
        self.maybe_sample()
        end_rss = _rss_bytes()
        tracemalloc.start()
        current, peak = tracemalloc.get_traced_memory()
        end_heap = current
        self.peak_heap = max(self.peak_heap, peak, end_heap)
        try:
            tracemalloc.stop()
        except Exception:
            pass
        self.peak_rss = max(self.peak_rss, end_rss)
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

        late_slope_bps = None
        late_range = None
        if len(self.samples) >= 8:
            warm = max(3, len(self.samples) // 4)
            late = self.samples[warm:]
            dt = max(late[-1]["t"] - late[0]["t"], 1e-6)
            late_slope_bps = (late[-1]["rss"] - late[0]["rss"]) / dt
            late_range = max(s["rss"] for s in late) - min(s["rss"] for s in late)

        min_events_for_linear = 50_000
        status = "BOUNDED"
        if per_m is None or self.start_rss <= 0:
            status = "INSTRUMENTATION_FAILED"
        elif event_count < min_events_for_linear:
            if rss_growth > 256 * 1024 * 1024 and (late_slope_bps or 0) > 100_000:
                status = "LINEAR_GROWTH_DETECTED"
            else:
                status = "LIKELY_BOUNDED_NEEDS_LONGER_RUN"
        elif late_slope_bps is not None and late_slope_bps > 80_000 and (late_range or 0) > 32 * 1024 * 1024:
            # Sustained >~80KB/s with >32MB late-window range.
            status = "LINEAR_GROWTH_DETECTED"
        elif per_m > 200 * 1024 * 1024 and (late_slope_bps is None or late_slope_bps > 40_000):
            status = "LINEAR_GROWTH_DETECTED"
        elif per_m > 50 * 1024 * 1024 or (late_slope_bps or 0) > 40_000:
            status = "LIKELY_BOUNDED_NEEDS_LONGER_RUN"
        elif late_range is not None and late_range < 16 * 1024 * 1024:
            status = "BOUNDED"

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
            "heap_growth_per_million_events": (heap_growth / (event_count / 1_000_000.0)) if event_count else None,
            "late_rss_slope_bytes_per_sec": late_slope_bps,
            "late_rss_range_bytes": late_range,
            "memory_growth_status": status,
            "sample_count": len(self.samples),
        }
