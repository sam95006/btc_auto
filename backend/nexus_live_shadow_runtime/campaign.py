"""V18.2 Phase C — NEXUS_SHADOW_24H_QUALIFICATION_CAMPAIGN.

Extends LiveShadowRuntimeConductor (single authority). Does not invent a second pipeline.
Agent launches detached Runtime under D:\\NEXUS_RUNTIME; Runtime continues alone.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.nexus_live_shadow_runtime.campaign_checkpoint import (
    CompactCheckpointWriter,
    build_compact_checkpoint,
    utc_now,
)
from backend.nexus_live_shadow_runtime.conductor import ConductorConfig, LiveShadowRuntimeConductor
from backend.nexus_live_shadow_runtime.constants import (
    DEFAULT_BACKOFF_BASE_SEC,
    DEFAULT_BACKOFF_MAX_SEC,
    DEFAULT_HEARTBEAT_INTERVAL_SEC,
    DEFAULT_RUNTIME_ROOT,
    HEARTBEAT_FILENAME,
    LOCK_NAME,
)
from backend.nexus_live_shadow_runtime.cycle import preflight_adapters
from backend.nexus_live_shadow_runtime.metrics import RuntimeMetrics
from backend.nexus_official_market_adapters import OfficialMarketAdapterRegistry
from backend.nexus_provider.circuit_breaker import ProviderCircuitBreaker
from backend.runtime.single_instance_guard import SingleInstanceError, SingleInstanceGuard

CAMPAIGN_SCHEMA = "v18_2_shadow_24h_qualification_campaign_v1"
CAMPAIGN_PROGRAM = "NEXUS_SHADOW_24H_QUALIFICATION_CAMPAIGN"
DEFAULT_CAMPAIGNS_ROOT = Path(r"D:\NEXUS_RUNTIME\campaigns")
DEFAULT_TARGET_HOURS = 24.0
DEFAULT_CHECKPOINT_INTERVAL_SEC = 3600.0
DEFAULT_CYCLE_SLEEP_SEC = 60.0  # 1 cycle / minute — not a busy-loop
DEFAULT_MAX_DISK_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB campaign budget
DEFAULT_MAX_RESTARTS = 5
DEFAULT_LOG_BYTES = 8 * 1024 * 1024
DEFAULT_LOG_BACKUPS = 5
SOURCE_FAILURE_THRESHOLD = 5
SOURCE_COOLDOWN_SEC = 120.0

CAMPAIGN_STATES = frozenset(
    {
        "PREFLIGHT",
        "STARTING",
        "RUNNING",
        "DEGRADED",
        "BACKOFF",
        "STOPPING",
        "STOPPED",
        "FAILED_SAFE",
        "COMPLETED",
    }
)


def _ensure_runtime_root(path: Path) -> Path:
    root = Path(path)
    normalized = str(root).replace("/", "\\").upper()
    if not normalized.startswith("D:\\NEXUS_RUNTIME"):
        if os.environ.get("NEXUS_ALLOW_NON_RUNTIME_ROOT", "").strip() not in {"1", "true"}:
            raise RuntimeError(f"campaign_root_must_be_under_NEXUS_RUNTIME:{root}")
    return root


def make_campaign_id(*, prefix: str = "shadow_24h") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}"


def _dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


@dataclass
class CampaignConfig:
    campaign_id: str = field(default_factory=make_campaign_id)
    campaigns_root: Path = field(default_factory=lambda: DEFAULT_CAMPAIGNS_ROOT)
    target_duration_hours: float = DEFAULT_TARGET_HOURS
    checkpoint_interval_sec: float = DEFAULT_CHECKPOINT_INTERVAL_SEC
    cycle_sleep_sec: float = DEFAULT_CYCLE_SLEEP_SEC
    max_disk_bytes: int = DEFAULT_MAX_DISK_BYTES
    max_restarts: int = DEFAULT_MAX_RESTARTS
    backoff_base_sec: float = DEFAULT_BACKOFF_BASE_SEC
    backoff_max_sec: float = DEFAULT_BACKOFF_MAX_SEC
    heartbeat_interval_sec: float = DEFAULT_HEARTBEAT_INTERVAL_SEC
    live: bool = True

    @property
    def campaign_dir(self) -> Path:
        return Path(self.campaigns_root) / self.campaign_id

    @property
    def runtime_root(self) -> Path:
        return self.campaign_dir / "runtime"

    @property
    def checkpoint_dir(self) -> Path:
        return self.campaign_dir / "checkpoints"

    @property
    def logs_dir(self) -> Path:
        return self.campaign_dir / "logs"

    @property
    def target_seconds(self) -> float:
        return float(self.target_duration_hours) * 3600.0


class SourceCircuitBreaker:
    """Fail-closed source health gate (wraps ProviderCircuitBreaker)."""

    def __init__(
        self,
        *,
        failure_threshold: int = SOURCE_FAILURE_THRESHOLD,
        cooldown_seconds: float = SOURCE_COOLDOWN_SEC,
    ) -> None:
        self._cb = ProviderCircuitBreaker(
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
        )
        self.provider = "official_market_adapters"

    def record_success(self) -> None:
        self._cb.record_success(self.provider)

    def record_failure(self) -> bool:
        return self._cb.record_failure(self.provider)

    @property
    def open(self) -> bool:
        return self._cb.is_open(self.provider)

    def health_label(self) -> str:
        if self.open:
            return "CIRCUIT_OPEN"
        st = self._cb.status(self.provider)
        fails = int(st.get("failures") or 0)
        if fails > 0:
            return "DEGRADED"
        return "OK"

    def status(self) -> dict[str, Any]:
        return self._cb.status(self.provider)


def setup_log_rotation(logs_dir: Path, *, name: str = "campaign") -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"nexus.shadow_24h.{name}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.handlers.RotatingFileHandler(
        logs_dir / f"{name}.log",
        maxBytes=DEFAULT_LOG_BYTES,
        backupCount=DEFAULT_LOG_BACKUPS,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
    )
    logger.addHandler(handler)
    return logger


class Shadow24hQualificationCampaign:
    """24h qualification campaign — single authority via LiveShadowRuntimeConductor."""

    def __init__(self, config: CampaignConfig | None = None) -> None:
        self.config = config or CampaignConfig()
        _ensure_runtime_root(self.config.campaigns_root)
        self.campaign_dir = self.config.campaign_dir
        self.runtime_root = self.config.runtime_root
        self.checkpoint_dir = self.config.checkpoint_dir
        self.logs_dir = self.config.logs_dir
        for d in (self.campaign_dir, self.runtime_root, self.checkpoint_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.campaign_state = "PREFLIGHT"
        self.started_at: str | None = None
        self.target_end_at: str | None = None
        self._stop_requested = False
        self._guard: SingleInstanceGuard | None = None
        self._source_cb = SourceCircuitBreaker()
        self._checkpoints = CompactCheckpointWriter(self.checkpoint_dir)
        self._last_checkpoint_mono = 0.0
        self._t0_mono = 0.0
        self._restart_count = 0
        self._backoff_sec = float(self.config.backoff_base_sec)
        self.logger = setup_log_rotation(self.logs_dir)
        self.pid_path = self.campaign_dir / "campaign.pid"
        self.heartbeat_path = self.runtime_root / HEARTBEAT_FILENAME
        self.manifest_path = self.campaign_dir / "campaign_manifest.json"
        self.stop_path = self.campaign_dir / "stop_requested"
        self.exit_path = self.campaign_dir / "campaign_exit.json"

    # --- preflight ---------------------------------------------------------

    def preflight(self) -> dict[str, Any]:
        """Campaign preflight: root, disk, adapters, lock availability."""
        issues: list[str] = []
        root_ok = str(self.config.campaigns_root).replace("/", "\\").upper().startswith(
            "D:\\NEXUS_RUNTIME"
        )
        if not root_ok and os.environ.get("NEXUS_ALLOW_NON_RUNTIME_ROOT", "").strip() not in {
            "1",
            "true",
        }:
            issues.append("campaigns_root_not_under_D_NEXUS_RUNTIME")

        try:
            usage = os.statvfs(str(self.config.campaigns_root)) if hasattr(os, "statvfs") else None
        except Exception:  # noqa: BLE001
            usage = None
        free_bytes: int | None = None
        if usage is not None:
            free_bytes = int(usage.f_bavail * usage.f_frsize)
        else:
            try:
                import shutil

                free_bytes = int(shutil.disk_usage(str(self.config.campaigns_root)).free)
            except Exception:  # noqa: BLE001
                free_bytes = None
        if free_bytes is not None and free_bytes < self.config.max_disk_bytes:
            issues.append(f"insufficient_free_disk:{free_bytes}")

        metrics = RuntimeMetrics()
        registry = OfficialMarketAdapterRegistry(use_fixtures=not self.config.live)
        try:
            adapter_results, both_ok = preflight_adapters(registry, metrics)
        except Exception as exc:  # noqa: BLE001
            adapter_results = {"error": str(exc)}
            both_ok = False
            issues.append(f"adapter_preflight_exception:{type(exc).__name__}")

        any_ok = False
        if isinstance(adapter_results, dict):
            any_ok = any(
                isinstance(v, dict) and v.get("ok") for v in adapter_results.values()
            )
        if not any_ok:
            issues.append("no_adapter_healthy")

        # Probe lock without holding forever — release immediately.
        lock_ok = True
        try:
            probe = SingleInstanceGuard(
                f"{LOCK_NAME}_campaign",
                lock_dir=self.runtime_root / "locks",
            ).acquire()
            probe.release()
        except SingleInstanceError as exc:
            lock_ok = False
            issues.append(f"lock_busy:{exc}")

        disk_used = _dir_size_bytes(self.campaign_dir)
        if disk_used > self.config.max_disk_bytes:
            issues.append(f"campaign_disk_quota_exceeded:{disk_used}")

        passed = len(issues) == 0 and any_ok and lock_ok
        result = {
            "schema": f"{CAMPAIGN_SCHEMA}_preflight",
            "campaign_id": self.config.campaign_id,
            "passed": passed,
            "issues": issues,
            "both_adapters_ok": both_ok,
            "any_adapter_ok": any_ok,
            "adapter_results": adapter_results if isinstance(adapter_results, dict) else {},
            "lock_ok": lock_ok,
            "free_bytes": free_bytes,
            "disk_used_bytes": disk_used,
            "max_disk_bytes": self.config.max_disk_bytes,
            "runtime_root": str(self.runtime_root),
            "campaigns_root": str(self.config.campaigns_root),
            "live": self.config.live,
            "checked_at": utc_now(),
        }
        (self.campaign_dir / "preflight.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return result

    # --- lifecycle ---------------------------------------------------------

    def request_stop(self, *_args: Any, **_kwargs: Any) -> None:
        self._stop_requested = True

    def _stop_requested_file(self) -> bool:
        return self.stop_path.exists() or (self.runtime_root / "stop_requested").exists()

    def write_manifest(self, **extra: Any) -> dict[str, Any]:
        payload = {
            "schema": CAMPAIGN_SCHEMA,
            "program": CAMPAIGN_PROGRAM,
            "campaign_id": self.config.campaign_id,
            "campaign_state": self.campaign_state,
            "started_at": self.started_at,
            "target_end_at": self.target_end_at,
            "target_duration_hours": self.config.target_duration_hours,
            "pid": os.getpid(),
            "runtime_root": str(self.runtime_root),
            "checkpoint_dir": str(self.checkpoint_dir),
            "heartbeat_path": str(self.heartbeat_path),
            "pid_path": str(self.pid_path),
            "logs_dir": str(self.logs_dir),
            "max_disk_bytes": self.config.max_disk_bytes,
            "max_restarts": self.config.max_restarts,
            "checkpoint_interval_sec": self.config.checkpoint_interval_sec,
            "cycle_sleep_sec": self.config.cycle_sleep_sec,
            "observe_only": True,
            "exchange_write": False,
            "mainnet": False,
            "real_money": False,
            "updated_at": utc_now(),
            **extra,
        }
        self.manifest_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return payload

    def _write_pid(self) -> None:
        self.pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")

    def _write_checkpoint(self, *, force: bool = False, metrics: dict[str, Any] | None = None) -> Path | None:
        now = time.monotonic()
        if (
            not force
            and self._last_checkpoint_mono
            and (now - self._last_checkpoint_mono) < float(self.config.checkpoint_interval_sec)
        ):
            return None
        elapsed = now - self._t0_mono if self._t0_mono else 0.0
        hb_age = None
        if self.heartbeat_path.exists():
            try:
                hb = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
                hb_at = str(hb.get("heartbeat_at") or "")
                if hb_at:
                    # Parse ISO-ish Z timestamps.
                    cleaned = hb_at.replace("Z", "+00:00")
                    ts = datetime.fromisoformat(cleaned)
                    hb_age = max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
            except Exception:  # noqa: BLE001
                hb_age = None
        m = metrics or {}
        if not m and (self.runtime_root / "metrics.json").exists():
            try:
                m = json.loads((self.runtime_root / "metrics.json").read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                m = {}
        data_lag = None
        if self.heartbeat_path.exists():
            try:
                hb = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
                data_lag = hb.get("current_data_lag_ms")
            except Exception:  # noqa: BLE001
                data_lag = None
        payload = build_compact_checkpoint(
            campaign_id=self.config.campaign_id,
            campaign_state=self.campaign_state,
            started_at=self.started_at or utc_now(),
            elapsed_sec=elapsed,
            heartbeat_age_sec=hb_age,
            metrics=m,
            source_health=self._source_cb.health_label(),
            data_lag_ms=int(data_lag) if data_lag is not None else None,
        )
        path = self._checkpoints.write(payload)
        self._last_checkpoint_mono = now
        self.logger.info("checkpoint_written path=%s state=%s", path.name, self.campaign_state)
        return path

    def _disk_ok(self) -> bool:
        used = _dir_size_bytes(self.campaign_dir)
        return used <= int(self.config.max_disk_bytes)

    def _acquire_lock(self) -> None:
        self._guard = SingleInstanceGuard(
            f"{LOCK_NAME}_campaign",
            lock_dir=self.runtime_root / "locks",
        ).acquire()

    def _release_lock(self) -> None:
        if self._guard is not None:
            self._guard.release()
            self._guard = None

    def _run_conductor_segment(self, *, remaining_sec: float) -> dict[str, Any]:
        """Run one bounded conductor segment (same authority; resume-safe)."""
        # High cycle budget; time bound is the real stop.
        max_cycles = max(1, int(remaining_sec / max(1.0, float(self.config.cycle_sleep_sec))) + 5)
        cfg = ConductorConfig(
            runtime_root=self.runtime_root,
            max_cycles=max_cycles,
            max_seconds=max(1.0, float(remaining_sec)),
            cycle_sleep_sec=float(self.config.cycle_sleep_sec),
            backoff_base_sec=float(self.config.backoff_base_sec),
            backoff_max_sec=float(self.config.backoff_max_sec),
            heartbeat_interval_sec=float(self.config.heartbeat_interval_sec),
            max_disk_bytes=int(self.config.max_disk_bytes),
            live=bool(self.config.live),
        )
        conductor = LiveShadowRuntimeConductor(cfg)
        # Propagate stop into conductor via stop file.
        if self._stop_requested or self._stop_requested_file():
            (self.runtime_root / "stop_requested").write_text("1\n", encoding="utf-8")
        snap = conductor.run()
        metrics = snap.get("metrics") or {}
        # Source health from metrics.
        src_fail = int(metrics.get("source_read_failure_count") or 0)
        src_ok = int(metrics.get("source_read_success_count") or 0)
        if src_ok > 0 and src_fail == 0:
            self._source_cb.record_success()
        elif src_fail > 0:
            # Record proportional failures without fabricating.
            for _ in range(min(src_fail, SOURCE_FAILURE_THRESHOLD)):
                self._source_cb.record_failure()
        return snap

    def run(self) -> dict[str, Any]:
        """Long-running campaign loop. Agent must launch this detached."""
        self._t0_mono = time.monotonic()
        self.started_at = utc_now()
        end_dt = datetime.now(timezone.utc) + timedelta(seconds=self.config.target_seconds)
        self.target_end_at = end_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self.campaign_state = "STARTING"
        self._write_pid()
        self.write_manifest()
        self.logger.info(
            "campaign_start id=%s hours=%s",
            self.config.campaign_id,
            self.config.target_duration_hours,
        )

        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                signal.signal(sig, self.request_stop)
            except Exception:  # noqa: BLE001
                pass

        pf = self.preflight()
        if not pf.get("passed"):
            self.campaign_state = "FAILED_SAFE"
            reason = "preflight_failed:" + ",".join(pf.get("issues") or [])
            self.write_manifest(failure_reason=reason, preflight=pf)
            self._write_checkpoint(force=True)
            exit_payload = {
                "schema": f"{CAMPAIGN_SCHEMA}_exit",
                "campaign_id": self.config.campaign_id,
                "campaign_state": self.campaign_state,
                "reason": reason,
                "exited_at": utc_now(),
                "preflight": pf,
            }
            self.exit_path.write_text(
                json.dumps(exit_payload, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
            return self.snapshot(preflight=pf, failure_reason=reason)

        try:
            self._acquire_lock()
        except SingleInstanceError as exc:
            self.campaign_state = "FAILED_SAFE"
            reason = f"duplicate_campaign:{exc}"
            self.write_manifest(failure_reason=reason)
            self._write_checkpoint(force=True)
            self.exit_path.write_text(
                json.dumps(
                    {
                        "schema": f"{CAMPAIGN_SCHEMA}_exit",
                        "campaign_id": self.config.campaign_id,
                        "campaign_state": self.campaign_state,
                        "reason": reason,
                        "exited_at": utc_now(),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            return self.snapshot(failure_reason=reason)

        self.campaign_state = "RUNNING"
        self.write_manifest()
        self._write_checkpoint(force=True)

        final_reason = "target_duration_reached"
        try:
            while True:
                if self._stop_requested or self._stop_requested_file():
                    final_reason = "stop_requested"
                    break
                elapsed = time.monotonic() - self._t0_mono
                remaining = float(self.config.target_seconds) - elapsed
                if remaining <= 0:
                    final_reason = "target_duration_reached"
                    break
                if not self._disk_ok():
                    self.campaign_state = "FAILED_SAFE"
                    final_reason = "disk_quota_exceeded"
                    break
                if self._source_cb.open:
                    self.campaign_state = "BACKOFF"
                    self.write_manifest(source_circuit=self._source_cb.status())
                    sleep_for = min(self._backoff_sec, float(self.config.backoff_max_sec))
                    self.logger.warning("source_circuit_open backoff=%.1fs", sleep_for)
                    time.sleep(sleep_for)
                    self._backoff_sec = min(
                        self._backoff_sec * 2.0, float(self.config.backoff_max_sec)
                    )
                    # After backoff, if still open and restarts exhausted → fail-closed.
                    if self._source_cb.open and self._restart_count >= self.config.max_restarts:
                        self.campaign_state = "FAILED_SAFE"
                        final_reason = "source_circuit_open_exhausted"
                        break
                    self.campaign_state = "DEGRADED"
                    continue

                # Segment length: min(remaining, checkpoint interval) so we checkpoint regularly.
                segment = min(remaining, float(self.config.checkpoint_interval_sec))
                try:
                    snap = self._run_conductor_segment(remaining_sec=segment)
                    state = str(snap.get("runtime_state") or "")
                    metrics = snap.get("metrics") or {}
                    if state == "FAILED_SAFE":
                        self._restart_count += 1
                        self.campaign_state = "BACKOFF"
                        self.write_manifest(
                            runtime_restart_count=self._restart_count,
                            last_runtime_state=state,
                        )
                        self._write_checkpoint(force=True, metrics=metrics)
                        if self._restart_count > int(self.config.max_restarts):
                            self.campaign_state = "FAILED_SAFE"
                            final_reason = "restart_budget_exhausted"
                            break
                        sleep_for = min(self._backoff_sec, float(self.config.backoff_max_sec))
                        time.sleep(sleep_for)
                        self._backoff_sec = min(
                            self._backoff_sec * 2.0, float(self.config.backoff_max_sec)
                        )
                        continue
                    # Healthy segment
                    self._backoff_sec = float(self.config.backoff_base_sec)
                    if state == "DEGRADED":
                        self.campaign_state = "DEGRADED"
                    else:
                        self.campaign_state = "RUNNING"
                    self.write_manifest(
                        runtime_restart_count=self._restart_count,
                        last_runtime_state=state,
                    )
                    self._write_checkpoint(force=True, metrics=metrics)
                except Exception as exc:  # noqa: BLE001
                    self._restart_count += 1
                    self.logger.exception("segment_error")
                    self.campaign_state = "BACKOFF"
                    self.write_manifest(
                        last_error=f"{type(exc).__name__}:{exc}",
                        runtime_restart_count=self._restart_count,
                    )
                    self._write_checkpoint(force=True)
                    if self._restart_count > int(self.config.max_restarts):
                        self.campaign_state = "FAILED_SAFE"
                        final_reason = f"segment_error_exhausted:{type(exc).__name__}"
                        break
                    sleep_for = min(self._backoff_sec, float(self.config.backoff_max_sec))
                    time.sleep(sleep_for)
                    self._backoff_sec = min(
                        self._backoff_sec * 2.0, float(self.config.backoff_max_sec)
                    )

            if self.campaign_state not in {"FAILED_SAFE", "STOPPED", "COMPLETED"}:
                self.campaign_state = "STOPPING"
                self.write_manifest()
                self.campaign_state = "COMPLETED" if final_reason == "target_duration_reached" else "STOPPED"
        finally:
            self._write_checkpoint(force=True)
            self.write_manifest(failure_reason=final_reason if self.campaign_state == "FAILED_SAFE" else None)
            self.exit_path.write_text(
                json.dumps(
                    {
                        "schema": f"{CAMPAIGN_SCHEMA}_exit",
                        "campaign_id": self.config.campaign_id,
                        "campaign_state": self.campaign_state,
                        "reason": final_reason,
                        "exited_at": utc_now(),
                        "started_at": self.started_at,
                        "target_end_at": self.target_end_at,
                        "runtime_restart_count": self._restart_count,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self._release_lock()
            self.logger.info("campaign_exit state=%s reason=%s", self.campaign_state, final_reason)

        return self.snapshot(failure_reason=final_reason)

    def snapshot(self, **extra: Any) -> dict[str, Any]:
        return {
            "schema": CAMPAIGN_SCHEMA,
            "program": CAMPAIGN_PROGRAM,
            "campaign_id": self.config.campaign_id,
            "campaign_state": self.campaign_state,
            "started_at": self.started_at,
            "target_end_at": self.target_end_at,
            "pid": os.getpid(),
            "runtime_root": str(self.runtime_root),
            "checkpoint_dir": str(self.checkpoint_dir),
            "heartbeat_path": str(self.heartbeat_path),
            "manifest_path": str(self.manifest_path),
            "runtime_restart_count": self._restart_count,
            "source_circuit": self._source_cb.status(),
            **extra,
        }

    def resume_review(self) -> dict[str, Any]:
        """Coordinator-facing post-24h review (read-only)."""
        manifest = {}
        if self.manifest_path.exists():
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        latest_cp = None
        latest_path = self.checkpoint_dir / "checkpoint_latest.json"
        if latest_path.exists():
            latest_cp = json.loads(latest_path.read_text(encoding="utf-8"))
        exit_payload = None
        if self.exit_path.exists():
            exit_payload = json.loads(self.exit_path.read_text(encoding="utf-8"))
        hb = None
        if self.heartbeat_path.exists():
            hb = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
        pid_alive = False
        try:
            pid = int((self.pid_path.read_text(encoding="utf-8").strip() or "0"))
            if pid > 0:
                if os.name == "nt":
                    import ctypes

                    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                    if handle:
                        pid_alive = True
                        ctypes.windll.kernel32.CloseHandle(handle)
                else:
                    os.kill(pid, 0)
                    pid_alive = True
        except Exception:  # noqa: BLE001
            pid_alive = False

        state = str(
            (exit_payload or {}).get("campaign_state")
            or manifest.get("campaign_state")
            or "UNKNOWN"
        )
        eligible = int((latest_cp or {}).get("eligible") or 0)
        shadow_opened = int((latest_cp or {}).get("shadow_opened") or 0)
        status = "INCOMPLETE"
        if state == "COMPLETED":
            if eligible == 0 and shadow_opened == 0:
                status = "SHADOW_24H_OPERATIONAL_PASS_NO_ELIGIBLE_ENTRY"
            else:
                status = "SHADOW_24H_OPERATIONAL_PASS"
        elif state == "FAILED_SAFE":
            status = "FAILED_SAFE"
        elif state in {"RUNNING", "DEGRADED", "BACKOFF"} and pid_alive:
            status = "RUNNING"
        elif state in {"STOPPED"}:
            status = "STOPPED"

        return {
            "schema": f"{CAMPAIGN_SCHEMA}_resume_review",
            "campaign_id": self.config.campaign_id,
            "review_status": status,
            "campaign_state": state,
            "pid_alive": pid_alive,
            "manifest": manifest,
            "latest_checkpoint": latest_cp,
            "exit": exit_payload,
            "heartbeat": hb,
            "reviewed_at": utc_now(),
        }


def launch_detached(
    *,
    repo_root: Path,
    config: CampaignConfig,
    python_exe: str | None = None,
) -> dict[str, Any]:
    """Preflight in-process, then Start-Process detached campaign daemon."""
    campaign = Shadow24hQualificationCampaign(config)
    pf = campaign.preflight()
    if not pf.get("passed"):
        return {
            "schema": f"{CAMPAIGN_SCHEMA}_launch",
            "status": "FAILED_SAFE",
            "campaign_id": config.campaign_id,
            "campaign_state": "FAILED_SAFE",
            "live_started": False,
            "blocker": "preflight_failed",
            "preflight": pf,
            "pid": None,
            "started_at": None,
            "target_end_at": None,
            "campaign_dir": str(campaign.campaign_dir),
            "launched_at": utc_now(),
        }

    py = python_exe or sys.executable
    stdout_log = campaign.logs_dir / "daemon_stdout.log"
    stderr_log = campaign.logs_dir / "daemon_stderr.log"
    cmd = [
        py,
        "-m",
        "backend.nexus_live_shadow_runtime",
        "--campaign",
        "24h",
        "--mode",
        "run",
        "--campaign-id",
        config.campaign_id,
        "--campaigns-root",
        str(config.campaigns_root),
        "--target-duration-hours",
        str(config.target_duration_hours),
        "--checkpoint-interval-sec",
        str(config.checkpoint_interval_sec),
        "--cycle-sleep-sec",
        str(config.cycle_sleep_sec),
    ]
    if not config.live:
        cmd.append("--no-live")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["EXCHANGE_WRITE"] = "false"
    env["MAINNET"] = "false"
    env["REAL_MONEY"] = "false"
    env["NEXUS_SHADOW_CAMPAIGN_ID"] = config.campaign_id

    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        )

    fout = open(stdout_log, "a", encoding="utf-8")
    ferr = open(stderr_log, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            env=env,
            stdout=fout,
            stderr=ferr,
            creationflags=creationflags,
            close_fds=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "schema": f"{CAMPAIGN_SCHEMA}_launch",
            "status": "FAILED_SAFE",
            "campaign_id": config.campaign_id,
            "campaign_state": "FAILED_SAFE",
            "live_started": False,
            "blocker": f"spawn_failed:{type(exc).__name__}:{exc}",
            "preflight": pf,
            "pid": None,
            "started_at": None,
            "target_end_at": None,
            "campaign_dir": str(campaign.campaign_dir),
            "launched_at": utc_now(),
        }

    time.sleep(2.5)
    alive = proc.poll() is None
    started_at = utc_now()
    end_dt = datetime.now(timezone.utc) + timedelta(seconds=config.target_seconds)
    target_end_at = end_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # Do NOT overwrite campaign_manifest.json — daemon owns it after spawn.
    # Persist launcher binding separately for evidence / resume-review.
    launcher_bind = {
        "schema": f"{CAMPAIGN_SCHEMA}_launcher_bind",
        "campaign_id": config.campaign_id,
        "campaign_state": "RUNNING" if alive else "FAILED_SAFE",
        "launcher_pid": os.getpid(),
        "daemon_pid": proc.pid,
        "started_at": started_at,
        "target_end_at": target_end_at,
        "target_duration_hours": config.target_duration_hours,
        "runtime_root": str(campaign.runtime_root),
        "checkpoint_dir": str(campaign.checkpoint_dir),
        "heartbeat_path": str(campaign.heartbeat_path),
        "manifest_path": str(campaign.manifest_path),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "cmd": cmd,
        "updated_at": utc_now(),
    }
    (campaign.campaign_dir / "launcher_bind.json").write_text(
        json.dumps(launcher_bind, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (campaign.campaign_dir / "launcher_pid.txt").write_text(
        str(os.getpid()) + "\n", encoding="utf-8"
    )
    (campaign.campaign_dir / "daemon_pid.txt").write_text(str(proc.pid) + "\n", encoding="utf-8")

    # If daemon already wrote manifest, leave it; else seed a minimal RUNNING bind.
    if not campaign.manifest_path.exists():
        campaign.manifest_path.write_text(
            json.dumps(
                {
                    "schema": CAMPAIGN_SCHEMA,
                    "program": CAMPAIGN_PROGRAM,
                    "campaign_id": config.campaign_id,
                    "campaign_state": "RUNNING" if alive else "FAILED_SAFE",
                    "pid": proc.pid,
                    "started_at": started_at,
                    "target_end_at": target_end_at,
                    "runtime_root": str(campaign.runtime_root),
                    "checkpoint_dir": str(campaign.checkpoint_dir),
                    "heartbeat_path": str(campaign.heartbeat_path),
                    "updated_at": utc_now(),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    status = "RUNNING" if alive else "FAILED_SAFE"
    return {
        "schema": f"{CAMPAIGN_SCHEMA}_launch",
        "status": status,
        "campaign_id": config.campaign_id,
        "campaign_state": status,
        "live_started": bool(alive),
        "blocker": None if alive else "daemon_exited_immediately",
        "preflight": pf,
        "pid": proc.pid,
        "started_at": started_at,
        "target_end_at": target_end_at,
        "campaign_dir": str(campaign.campaign_dir),
        "runtime_root": str(campaign.runtime_root),
        "checkpoint_dir": str(campaign.checkpoint_dir),
        "heartbeat_path": str(campaign.heartbeat_path),
        "manifest_path": str(campaign.manifest_path),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "launched_at": utc_now(),
    }
