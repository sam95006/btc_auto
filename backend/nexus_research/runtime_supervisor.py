"""Single-owner 24h research supervisor.

Job registry, scheduling, timeout, retry/backoff, circuit breaker,
graceful shutdown hooks, stuck detection.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from typing import Any, Callable

from backend.nexus_research.domain_events import (
    SUPERVISOR_CIRCUIT_OPEN,
    SUPERVISOR_JOB_COMPLETED,
    SUPERVISOR_JOB_FAILED,
    SUPERVISOR_JOB_REGISTERED,
    SUPERVISOR_STARTED,
    publish_event,
)

logger = logging.getLogger(__name__)

_CIRCUIT_FAIL_THRESHOLD = 3
_CIRCUIT_RESET_SEC = 300
_STUCK_THRESHOLD_SEC = 120


class JobCircuitBreaker:
    def __init__(self, job_id: str, fail_threshold: int = _CIRCUIT_FAIL_THRESHOLD) -> None:
        self.job_id = job_id
        self.fail_threshold = fail_threshold
        self._fails = 0
        self._open_at: float = 0.0
        self._lock = threading.RLock()  # RLock allows re-entrant acquisition

    def _is_open_unlocked(self) -> bool:
        """Check circuit state; caller must hold self._lock."""
        if self._fails >= self.fail_threshold:
            if time.time() - self._open_at < _CIRCUIT_RESET_SEC:
                return True
            self._fails = 0
        return False

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._is_open_unlocked()

    def record_success(self) -> None:
        with self._lock:
            self._fails = 0

    def record_failure(self) -> None:
        with self._lock:
            self._fails += 1
            if self._fails >= self.fail_threshold:
                self._open_at = time.time()
                publish_event(
                    SUPERVISOR_CIRCUIT_OPEN,
                    {"jobId": self.job_id, "fails": self._fails},
                )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "jobId": self.job_id,
                "fails": self._fails,
                "isOpen": self._is_open_unlocked(),  # safe: RLock allows re-entrance
                "openAt": self._open_at or None,
            }


class RegisteredJob:
    def __init__(
        self,
        job_id: str,
        fn: Callable[[], None],
        interval_sec: float,
        timeout_sec: float = 60.0,
        max_retries: int = 2,
        backoff_sec: float = 5.0,
    ) -> None:
        self.job_id = job_id
        self.fn = fn
        self.interval_sec = interval_sec
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.backoff_sec = backoff_sec
        self.circuit = JobCircuitBreaker(job_id)
        self._lock = threading.RLock()  # RLock: re-entrant safe for nested property calls
        self._last_run_at: float = 0.0
        self._last_success_at: float = 0.0
        self._run_count = 0
        self._fail_count = 0
        self._running = False
        self._running_since: float = 0.0

    @property
    def is_due(self) -> bool:
        return time.time() - self._last_run_at >= self.interval_sec

    def _is_stuck_unlocked(self) -> bool:
        """Check stuck state; caller must hold self._lock."""
        if self._running and self._running_since > 0:
            return time.time() - self._running_since > _STUCK_THRESHOLD_SEC
        return False

    @property
    def is_stuck(self) -> bool:
        with self._lock:
            return self._is_stuck_unlocked()

    def run_once(self) -> None:
        if self.circuit.is_open:
            logger.info("[supervisor] circuit open for %s — skipping", self.job_id)
            return
        with self._lock:
            self._running = True
            self._running_since = time.time()
            self._last_run_at = time.time()

        attempts = 0
        while attempts <= self.max_retries:
            try:
                self.fn()
                with self._lock:
                    self._run_count += 1
                    self._last_success_at = time.time()
                    self._running = False
                self.circuit.record_success()
                publish_event(
                    SUPERVISOR_JOB_COMPLETED,
                    {"jobId": self.job_id, "attempt": attempts},
                )
                return
            except Exception as exc:  # noqa: BLE001
                attempts += 1
                logger.warning("[supervisor] job %s attempt %d failed: %s", self.job_id, attempts, exc)
                if attempts <= self.max_retries:
                    time.sleep(self.backoff_sec * attempts)

        with self._lock:
            self._fail_count += 1
            self._running = False
        self.circuit.record_failure()
        publish_event(SUPERVISOR_JOB_FAILED, {"jobId": self.job_id, "attempts": attempts})

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "jobId": self.job_id,
                "intervalSec": self.interval_sec,
                "lastRunAt": self._last_run_at or None,
                "lastSuccessAt": self._last_success_at or None,
                "runCount": self._run_count,
                "failCount": self._fail_count,
                "running": self._running,
                "isStuck": self._is_stuck_unlocked(),  # safe: RLock re-entrant
                "circuit": self.circuit.status(),
            }


class ResearchSupervisor:
    """Single-owner supervisor. Start once at app boot; runs background thread."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, RegisteredJob] = {}
        self._shutdown_hooks: list[Callable[[], None]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: float = 0.0
        self._tick_interval_sec = 5.0

    def register_job(
        self,
        job_id: str,
        fn: Callable[[], None],
        interval_sec: float,
        timeout_sec: float = 60.0,
        max_retries: int = 2,
        backoff_sec: float = 5.0,
    ) -> None:
        job = RegisteredJob(job_id, fn, interval_sec, timeout_sec, max_retries, backoff_sec)
        with self._lock:
            self._jobs[job_id] = job
        publish_event(SUPERVISOR_JOB_REGISTERED, {"jobId": job_id, "intervalSec": interval_sec})

    def add_shutdown_hook(self, fn: Callable[[], None]) -> None:
        with self._lock:
            self._shutdown_hooks.append(fn)

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._started_at = time.time()
            self._thread = threading.Thread(
                target=self._loop, name="nexus-research-supervisor", daemon=True
            )
            self._thread.start()
        publish_event(SUPERVISOR_STARTED, {"researchOnly": True})
        logger.info("[supervisor] research supervisor started")

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        with self._lock:
            hooks = list(self._shutdown_hooks)
        for hook in hooks:
            try:
                hook()
            except Exception:  # noqa: BLE001
                pass
        t = self._thread
        if t:
            t.join(timeout=timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self._tick_interval_sec)
            if self._stop.is_set():
                break
            with self._lock:
                jobs = list(self._jobs.values())
            for job in jobs:
                if job.is_stuck:
                    logger.warning("[supervisor] job %s appears stuck", job.job_id)
                if job.is_due and not job.circuit.is_open:
                    t = threading.Thread(
                        target=job.run_once,
                        name=f"nexus-job-{job.job_id}",
                        daemon=True,
                    )
                    t.start()

    def status(self) -> dict[str, Any]:
        with self._lock:
            jobs_status = {jid: j.status() for jid, j in self._jobs.items()}
            running = self._thread is not None and self._thread.is_alive()
        return {
            "ok": True,
            "researchOnly": True,
            "supervisorRunning": running,
            "startedAt": self._started_at or None,
            "uptimeSec": round(time.time() - self._started_at, 1) if self._started_at else None,
            "jobCount": len(jobs_status),
            "jobs": jobs_status,
            "generatedAt": int(time.time() * 1000),
        }


_SUPERVISOR: ResearchSupervisor | None = None
_SUPERVISOR_LOCK = threading.Lock()


def get_supervisor() -> ResearchSupervisor:
    global _SUPERVISOR
    with _SUPERVISOR_LOCK:
        if _SUPERVISOR is None:
            _SUPERVISOR = ResearchSupervisor()
        return _SUPERVISOR
