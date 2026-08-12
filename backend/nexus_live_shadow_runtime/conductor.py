"""Live Shadow Runtime Conductor — single writer authority for V18.1 Phase A."""
from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_ai_gateway_tool_sandbox import UnifiedAIGateway
from backend.nexus_incremental_backfill_live_ingest.pipeline import IngestPipeline
from backend.nexus_live_shadow_runtime.constants import (
    DATA_CLASSES,
    DEFAULT_BACKOFF_BASE_SEC,
    DEFAULT_BACKOFF_MAX_SEC,
    DEFAULT_CYCLE_SLEEP_SEC,
    DEFAULT_HEARTBEAT_INTERVAL_SEC,
    DEFAULT_MAX_CYCLES,
    DEFAULT_MAX_DISK_BYTES,
    DEFAULT_MAX_SECONDS,
    DEFAULT_RUNTIME_ROOT,
    EXIT_FILENAME,
    HEARTBEAT_FILENAME,
    LEDGER_FILENAME,
    LOCK_NAME,
    METRICS_FILENAME,
    OWNED_PATHS,
    PROJECTION_FILENAME,
    RESUME_FILENAME,
    REUSED_V18_PACKAGES,
    SCHEMA,
    SCHEMA_VERSION,
    STOP_REQUEST_FILENAME,
)
from backend.nexus_live_shadow_runtime.cycle import run_full_cycle
from backend.nexus_live_shadow_runtime.metrics import RuntimeMetrics
from backend.nexus_live_shadow_runtime.projection import PublicSafeProjectionWriter
from backend.nexus_live_shadow_runtime.state_machine import (
    InvalidRuntimeTransitionError,
    RuntimeStateMachine,
    utc_now,
)
from backend.nexus_official_market_adapters import OfficialMarketAdapterRegistry
from backend.nexus_shadow_decision_ledger import ShadowDecisionLedger
from backend.runtime.single_instance_guard import SingleInstanceError, SingleInstanceGuard


@dataclass
class ConductorConfig:
    runtime_root: Path = field(default_factory=lambda: DEFAULT_RUNTIME_ROOT)
    max_cycles: int = DEFAULT_MAX_CYCLES
    max_seconds: float = DEFAULT_MAX_SECONDS
    cycle_sleep_sec: float = DEFAULT_CYCLE_SLEEP_SEC
    backoff_base_sec: float = DEFAULT_BACKOFF_BASE_SEC
    backoff_max_sec: float = DEFAULT_BACKOFF_MAX_SEC
    heartbeat_interval_sec: float = DEFAULT_HEARTBEAT_INTERVAL_SEC
    max_disk_bytes: int = DEFAULT_MAX_DISK_BYTES
    live: bool = True


class LiveShadowRuntimeConductor:
    """Single-authority Live Shadow Runtime Conductor.

    Integrates existing V18 packages; does not invent a parallel pipeline.
    Reuses ``backend.runtime.single_instance_guard.SingleInstanceGuard``.
    """

    def __init__(self, config: ConductorConfig | None = None) -> None:
        self.config = config or ConductorConfig()
        self.root = Path(self.config.runtime_root)
        if not str(self.root).replace("/", "\\").upper().startswith("D:\\NEXUS_RUNTIME"):
            # Soft guard: prefer RUNTIME_ROOT; allow tests under temp if env set.
            if os.environ.get("NEXUS_ALLOW_NON_RUNTIME_ROOT", "").strip() not in {"1", "true"}:
                raise RuntimeError(f"runtime_root_must_be_under_NEXUS_RUNTIME:{self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        self.sm = RuntimeStateMachine(initial="STARTING")
        self.metrics = RuntimeMetrics()
        self.started_at = utc_now()
        self.last_successful_cycle_at: str | None = None
        self.last_cycle_duration_sec: float | None = None
        self.last_shadow_decision: dict[str, Any] | None = None
        self.current_universe_size: int = 0
        self.current_data_lag_ms: int | None = None
        self.data_class: str = "BOUNDED_LIVE_SMOKE"
        self._stop_requested = False
        self._guard: SingleInstanceGuard | None = None
        self._backoff_sec = float(self.config.backoff_base_sec)
        self._last_heartbeat_mono = 0.0

        self.ingest = IngestPipeline(
            self.root / "ingest",
            max_disk_bytes=self.config.max_disk_bytes,
        )
        self.ledger = ShadowDecisionLedger(self.root / LEDGER_FILENAME)
        self.projection = PublicSafeProjectionWriter(self.root / PROJECTION_FILENAME)
        self.registry = OfficialMarketAdapterRegistry(use_fixtures=False)
        self.ai_gateway = UnifiedAIGateway.from_env(mock=True)

        self._load_resume()

    # --- persistence -------------------------------------------------------

    def _load_resume(self) -> None:
        path = self.root / RESUME_FILENAME
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.metrics.runtime_restart_count = int(data.get("runtime_restart_count") or 0) + 1
            self.last_successful_cycle_at = data.get("last_successful_cycle_at")
            prev_cycles = int(data.get("runtime_cycles_completed") or 0)
            # Do not auto-fill zeros to hide prior failures — restore honestly.
            self.metrics.runtime_cycles_completed = prev_cycles
            self.metrics.runtime_cycles_failed = int(data.get("runtime_cycles_failed") or 0)
        except Exception:  # noqa: BLE001
            self.metrics.runtime_restart_count += 1

    def _write_resume(self) -> None:
        payload = {
            "schema": SCHEMA,
            "updated_at": utc_now(),
            "runtime_state": self.sm.state,
            "started_at": self.started_at,
            "last_successful_cycle_at": self.last_successful_cycle_at,
            "last_cycle_duration_sec": self.last_cycle_duration_sec,
            "runtime_cycles_completed": self.metrics.runtime_cycles_completed,
            "runtime_cycles_failed": self.metrics.runtime_cycles_failed,
            "runtime_restart_count": self.metrics.runtime_restart_count,
            "data_class": self.data_class,
            "failure_reason": self.sm.failure_reason,
            "last_shadow_decision": self.last_shadow_decision,
            "current_universe_size": self.current_universe_size,
            "current_data_lag_ms": self.current_data_lag_ms,
        }
        (self.root / RESUME_FILENAME).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _write_heartbeat(self, *, force: bool = False) -> None:
        now_mono = time.monotonic()
        if (
            not force
            and (now_mono - self._last_heartbeat_mono) < self.config.heartbeat_interval_sec
        ):
            return
        self._last_heartbeat_mono = now_mono
        payload = {
            "schema": f"{SCHEMA}_heartbeat",
            "pid": os.getpid(),
            "runtime_state": self.sm.state,
            "heartbeat_at": utc_now(),
            "started_at": self.started_at,
            "last_successful_cycle_at": self.last_successful_cycle_at,
            "last_cycle_duration_sec": self.last_cycle_duration_sec,
            "current_universe_size": self.current_universe_size,
            "current_data_lag_ms": self.current_data_lag_ms,
            "last_shadow_decision": self.last_shadow_decision,
            "runtime_restart_count": self.metrics.runtime_restart_count,
            "failure_reason": self.sm.failure_reason,
            "data_class": self.data_class,
            "metrics": self.metrics.to_dict(),
        }
        (self.root / HEARTBEAT_FILENAME).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (self.root / METRICS_FILENAME).write_text(
            json.dumps(self.metrics.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _write_exit(self, *, status: str, reason: str = "") -> None:
        payload = {
            "schema": f"{SCHEMA}_exit",
            "status": status,
            "reason": reason,
            "exited_at": utc_now(),
            "runtime_state": self.sm.state,
            "data_class": self.data_class,
            "metrics": self.metrics.to_dict(),
            "started_at": self.started_at,
            "last_successful_cycle_at": self.last_successful_cycle_at,
            "runtime_smoke_duration_hint_sec": None,
            "owned_paths": list(OWNED_PATHS),
            "reused_packages": list(REUSED_V18_PACKAGES),
        }
        (self.root / EXIT_FILENAME).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    # --- lifecycle ---------------------------------------------------------

    def request_stop(self, *_args: Any, **_kwargs: Any) -> None:
        self._stop_requested = True

    def _stop_file_present(self) -> bool:
        return (self.root / STOP_REQUEST_FILENAME).exists()

    def acquire_lock(self) -> None:
        lock_dir = self.root / "locks"
        try:
            self._guard = SingleInstanceGuard(LOCK_NAME, lock_dir=lock_dir).acquire()
        except SingleInstanceError as exc:
            self.sm.transition("FAILED_SAFE", reason=f"duplicate_writer:{exc}")
            self.data_class = "FAILED_SAFE"
            raise

    def release_lock(self) -> None:
        if self._guard is not None:
            self._guard.release()
            self._guard = None

    def resolve_data_class(self, *, both_ok: bool, any_ok: bool, degraded: bool) -> str:
        if not any_ok:
            return "FAILED_SAFE"
        if both_ok and not degraded:
            # Bounded smoke still labels as BOUNDED_LIVE_SMOKE unless continuous ops claimed.
            return "BOUNDED_LIVE_SMOKE" if self.config.max_cycles < 10_000 else "LIVE_READ_ONLY"
        if any_ok:
            return "LIVE_PARTIAL_DEGRADED"
        return "FAILED_SAFE"

    def run(self) -> dict[str, Any]:
        """Bounded run: preflight → cycles → graceful stop. No busy-loop."""
        t_start = time.monotonic()
        try:
            self.acquire_lock()
        except SingleInstanceError:
            self._write_heartbeat(force=True)
            self._write_exit(status="FAILED_SAFE", reason="duplicate_writer")
            return self.snapshot()

        # Install signal handlers for graceful shutdown.
        for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
            if sig is None:
                continue
            try:
                signal.signal(sig, self.request_stop)
            except Exception:  # noqa: BLE001
                pass

        try:
            self.sm.transition("PREFLIGHT", reason="lock_acquired")
            self._write_heartbeat(force=True)

            # Preflight both adapters once.
            from backend.nexus_live_shadow_runtime.cycle import preflight_adapters

            preflight, both_ok = preflight_adapters(self.registry, self.metrics)
            any_ok = any(v.get("ok") for v in preflight.values())
            self.data_class = self.resolve_data_class(
                both_ok=both_ok, any_ok=any_ok, degraded=not both_ok
            )
            if not any_ok:
                self.sm.transition("FAILED_SAFE", reason="both_adapters_failed_preflight")
                # Still attempt one fail-closed cycle for real counters + ledger/projection.
                self._run_one_cycle(cycle_index=0)
                self._write_resume()
                self._write_heartbeat(force=True)
                self._write_exit(status="FAILED_SAFE", reason="both_adapters_failed_preflight")
                return self.snapshot(duration_sec=time.monotonic() - t_start)

            if not both_ok:
                self.sm.transition("DEGRADED", reason="partial_adapter_preflight")
            else:
                self.sm.transition("RUNNING", reason="preflight_ok")

            cycles = 0
            while cycles < int(self.config.max_cycles):
                if self._stop_requested or self._stop_file_present():
                    break
                if (time.monotonic() - t_start) >= float(self.config.max_seconds):
                    break
                if self.sm.state in {"FAILED_SAFE", "STOPPED", "STOPPING"}:
                    break

                try:
                    self._run_one_cycle(cycle_index=cycles)
                    cycles += 1
                    self._backoff_sec = float(self.config.backoff_base_sec)
                    # Brief sleep between cycles — not a busy-loop poll.
                    time.sleep(max(0.0, float(self.config.cycle_sleep_sec)))
                except Exception as exc:  # noqa: BLE001 — fail-closed per cycle
                    self.metrics.bump("runtime_cycles_failed")
                    self._enter_backoff(reason=f"cycle_error:{type(exc).__name__}:{exc}")
                    if self.sm.state == "FAILED_SAFE":
                        break

            # Graceful stop.
            if self.sm.state not in {"FAILED_SAFE", "STOPPED", "STOPPING"}:
                self.sm.transition("STOPPING", reason="bounds_reached_or_stop_requested")
            if self.sm.state == "STOPPING":
                self.sm.transition("STOPPED", reason="graceful_shutdown")
            self._write_resume()
            self._write_heartbeat(force=True)
            self._write_exit(status=self.sm.state, reason="complete")
            return self.snapshot(duration_sec=time.monotonic() - t_start)
        except Exception as exc:  # noqa: BLE001
            try:
                if self.sm.state not in {"FAILED_SAFE", "STOPPED"}:
                    if self.sm.state == "STOPPING":
                        self.sm.transition("FAILED_SAFE", reason=str(exc))
                    elif self.sm.state in {
                        "STARTING",
                        "PREFLIGHT",
                        "RUNNING",
                        "DEGRADED",
                        "PAUSED",
                        "BACKOFF",
                    }:
                        self.sm.transition("FAILED_SAFE", reason=str(exc))
            except InvalidRuntimeTransitionError:
                pass
            self.data_class = "FAILED_SAFE"
            self._write_resume()
            self._write_heartbeat(force=True)
            self._write_exit(status="FAILED_SAFE", reason=str(exc))
            return self.snapshot(duration_sec=time.monotonic() - t_start)
        finally:
            self.release_lock()

    def _enter_backoff(self, *, reason: str) -> None:
        if self.sm.state in {"RUNNING", "DEGRADED", "PAUSED"}:
            self.sm.transition("BACKOFF", reason=reason)
        sleep_for = min(self._backoff_sec, float(self.config.backoff_max_sec))
        time.sleep(sleep_for)
        self._backoff_sec = min(self._backoff_sec * 2.0, float(self.config.backoff_max_sec))
        if self.sm.state == "BACKOFF":
            # Resume degraded after backoff unless stop requested.
            if self._stop_requested:
                self.sm.transition("STOPPING", reason="stop_during_backoff")
            else:
                self.sm.transition("DEGRADED", reason="backoff_complete")

    def _run_one_cycle(self, *, cycle_index: int) -> None:
        t0 = time.monotonic()
        ctx = run_full_cycle(
            registry=self.registry,
            ingest=self.ingest,
            ledger=self.ledger,
            ai_gateway=self.ai_gateway,
            metrics=self.metrics,
            data_class=self.data_class,
            cycle_index=cycle_index,
        )
        duration = time.monotonic() - t0
        self.last_cycle_duration_sec = duration
        funnel = (ctx.universe or {}).get("funnel") or {}
        self.current_universe_size = int(funnel.get("total_exchange_contracts") or 0)
        self.current_data_lag_ms = ctx.data_lag_ms
        if ctx.decision:
            self.last_shadow_decision = {
                "decision_id": ctx.decision.get("decision_id"),
                "decision": ctx.decision.get("decision"),
                "symbol": ctx.decision.get("symbol"),
                "data_class": ctx.decision.get("data_class"),
                "as_of": ctx.decision.get("as_of"),
            }
            # Public-safe projection
            proj = self.projection.append(
                {
                    "schema": SCHEMA,
                    "shadow_decision_id": ctx.ledger_record_id or ctx.decision.get("decision_id"),
                    "lifecycle_state": "OBSERVED",
                    "final_shadow_decision": {
                        "kind": ctx.decision.get("decision"),
                        "decision": ctx.decision.get("decision"),
                    },
                    "data_class": self.data_class,
                    "symbol": ctx.decision.get("symbol"),
                    "decision": ctx.decision.get("decision"),
                    "decision_status": ctx.decision.get("decision_status"),
                    "as_of": ctx.decision.get("as_of"),
                    "runtime_state": self.sm.state,
                    "cycle_index": cycle_index,
                    "virtual_research_position": False,
                    "sealed": False,
                    "content_hash": None,
                }
            )
            ctx.projection = proj

        if ctx.failure_reason == "both_adapters_failed":
            self.data_class = "FAILED_SAFE"
            self.metrics.bump("runtime_cycles_failed")
            if self.sm.state in {"RUNNING", "DEGRADED", "PREFLIGHT", "BACKOFF", "PAUSED"}:
                # Prefer BACKOFF then FAILED_SAFE if repeated; for total failure → FAILED_SAFE.
                if self.sm.state != "FAILED_SAFE":
                    try:
                        if self.sm.state in {"RUNNING", "DEGRADED", "PAUSED", "BACKOFF"}:
                            self.sm.transition("FAILED_SAFE", reason=ctx.failure_reason)
                        elif self.sm.state == "PREFLIGHT":
                            self.sm.transition("FAILED_SAFE", reason=ctx.failure_reason)
                    except InvalidRuntimeTransitionError:
                        pass
        else:
            if ctx.degraded and self.sm.state == "RUNNING":
                self.sm.transition("DEGRADED", reason="cycle_degraded")
                self.data_class = self.resolve_data_class(
                    both_ok=False, any_ok=True, degraded=True
                )
            self.metrics.bump("runtime_cycles_completed")
            self.last_successful_cycle_at = utc_now()

        self.metrics.assert_safety_invariants()
        self._write_resume()
        self._write_heartbeat()

    def snapshot(self, *, duration_sec: float | None = None) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "runtime_state": self.sm.state,
            "data_class": self.data_class if self.data_class in DATA_CLASSES else "FAILED_SAFE",
            "started_at": self.started_at,
            "last_successful_cycle_at": self.last_successful_cycle_at,
            "last_cycle_duration_sec": self.last_cycle_duration_sec,
            "runtime_smoke_duration_seconds": duration_sec,
            "current_universe_size": self.current_universe_size,
            "current_data_lag_ms": self.current_data_lag_ms,
            "last_shadow_decision": self.last_shadow_decision,
            "runtime_restart_count": self.metrics.runtime_restart_count,
            "failure_reason": self.sm.failure_reason,
            "metrics": self.metrics.to_dict(),
            "transition_history": self.sm.history(),
            "runtime_root": str(self.root),
            "projection_writes": self.projection.write_count,
            "owned_paths": list(OWNED_PATHS),
            "reused_packages": list(REUSED_V18_PACKAGES),
        }


def run_bounded_smoke(
    *,
    runtime_root: Path | None = None,
    max_cycles: int = DEFAULT_MAX_CYCLES,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    live: bool = True,
) -> dict[str, Any]:
    cfg = ConductorConfig(
        runtime_root=Path(runtime_root or DEFAULT_RUNTIME_ROOT),
        max_cycles=max_cycles,
        max_seconds=max_seconds,
        live=live,
    )
    return LiveShadowRuntimeConductor(cfg).run()
