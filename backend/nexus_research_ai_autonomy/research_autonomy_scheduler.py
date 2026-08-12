"""V18.2.30 Research Autonomy Scheduler — persistent Demo research cadence.

Position-first, single-flight, restart-recoverable.
Does NOT embed an unbounded Cursor while-True validation runner.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA = "v18_2_30_1_research_autonomy_scheduler_v1"

SERVICE_STATES = frozenset(
    {
        "RUNNING",
        "WAITING_MARKET",
        "MANAGING_POSITION",
        "DEGRADED",
        "STOPPED",
    }
)

# Cloud-safe default; overridden by NEXUS_CAMPAIGN_ROOT / SchedulerConfig.
def _default_campaign_root() -> Path:
    try:
        from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root

        return campaign_root()
    except Exception:  # noqa: BLE001
        return Path("/data/campaigns/research_v18_2_30")


DEFAULT_CAMPAIGN_ROOT = _default_campaign_root()
DEFAULT_CYCLE_SLEEP_SEC = 120.0
DEFAULT_MANAGE_POLL_SEC = 15.0
DEFAULT_MAX_MANAGE_TICKS = 8


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SchedulerConfig:
    campaign_root: Path = field(default_factory=_default_campaign_root)
    cycle_sleep_sec: float = DEFAULT_CYCLE_SLEEP_SEC
    manage_poll_sec: float = DEFAULT_MANAGE_POLL_SEC
    max_manage_ticks_per_invocation: int = DEFAULT_MAX_MANAGE_TICKS
    max_concurrent_research_positions: int = 1
    backoff_base_sec: float = 5.0
    backoff_max_sec: float = 300.0

    @property
    def state_path(self) -> Path:
        return self.campaign_root / "autonomy" / "scheduler_state.json"

    @property
    def position_checkpoint_path(self) -> Path:
        return self.campaign_root / "autonomy" / "research_pnl_position.json"

    @property
    def stop_file(self) -> Path:
        return self.campaign_root / "autonomy" / "STOP"


@dataclass
class SchedulerHealth:
    service_status: str = "STOPPED"
    last_cycle_started_at: str | None = None
    last_cycle_completed_at: str | None = None
    next_cycle_due_at: str | None = None
    last_cycle_duration_sec: float | None = None
    last_cycle_status: str | None = None
    cycles_completed: int = 0
    cycles_wait: int = 0
    cycles_error: int = 0
    cycles_24h: int = 0
    errors_24h: int = 0
    successful_cycles_24h: int = 0
    failed_cycles_24h: int = 0
    open_position: bool = False
    exchange_connectivity: str = "UNKNOWN"
    market_data_health: str = "UNKNOWN"
    single_flight: bool = True
    position_aware: bool = True
    restart_recovery: bool = True
    degraded_reason: str | None = None
    # V30.1 WAITING_MARKET semantics
    cycle_ai_ready: bool | None = None
    market_scan_complete: bool | None = None
    candidate_count: int | None = None
    # For MANAGING_POSITION stdout: avoid showing stale scan provenance.
    last_flat_scan_candidate_count: int | None = None
    last_flat_scan_at: str | None = None
    top_rejection_reasons: list | None = None
    waiting_market_valid: bool | None = None
    ai_state: str | None = None
    runtime_location: str | None = None
    worker_instance_id: str | None = None
    campaign_class: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchAutonomyScheduler:
    """Owns cadence + health. Invokes one bounded cycle function at a time."""

    def __init__(
        self,
        *,
        config: SchedulerConfig | None = None,
        cycle_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        manage_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        reconcile_fn: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config or SchedulerConfig()
        self.cycle_fn = cycle_fn
        self.manage_fn = manage_fn
        self.reconcile_fn = reconcile_fn
        self.health = SchedulerHealth(updated_at=_utc())
        self._lock = threading.Lock()
        self._in_flight = False
        self._stop_requested = False
        self._cycle_timestamps: list[float] = []
        self._error_timestamps: list[float] = []
        self._success_timestamps: list[float] = []
        self.config.campaign_root.mkdir(parents=True, exist_ok=True)
        (self.config.campaign_root / "autonomy").mkdir(parents=True, exist_ok=True)
        self._load_state()

    # --- persistence ---
    def _load_state(self) -> None:
        p = self.config.state_path
        if not p.is_file():
            return
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            h = raw.get("health") or {}
            for k, v in h.items():
                if hasattr(self.health, k):
                    setattr(self.health, k, v)
            if self.health.service_status not in SERVICE_STATES:
                self.health.service_status = "STOPPED"
        except Exception:  # noqa: BLE001
            self.health.service_status = "DEGRADED"
            self.health.degraded_reason = "scheduler_state_load_failed"

    def save_state(self) -> None:
        self.health.updated_at = _utc()
        payload = {
            "schema": SCHEMA,
            "saved_at": _utc(),
            "health": self.health.to_dict(),
            "config": {
                "cycle_sleep_sec": self.config.cycle_sleep_sec,
                "manage_poll_sec": self.config.manage_poll_sec,
                "max_manage_ticks_per_invocation": self.config.max_manage_ticks_per_invocation,
                "max_concurrent_research_positions": self.config.max_concurrent_research_positions,
            },
        }
        self.config.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(self.config.state_path)

    def start(self) -> dict[str, Any]:
        self._stop_requested = False
        if self.config.stop_file.exists():
            try:
                self.config.stop_file.unlink()
            except OSError:
                pass
        self.health.service_status = "RUNNING"
        self.health.degraded_reason = None
        self.save_state()
        return {"ok": True, "service_status": self.health.service_status}

    def stop(self) -> dict[str, Any]:
        self._stop_requested = True
        self.config.stop_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.stop_file.write_text(_utc() + "\n", encoding="utf-8")
        self.health.service_status = "STOPPED"
        self.save_state()
        return {"ok": True, "service_status": self.health.service_status}

    def health_snapshot(self) -> dict[str, Any]:
        self._roll_24h_windows()
        return {
            "schema": SCHEMA,
            "scheduler_ready": True,
            "persistent_service": True,
            "service_status": self.health.service_status,
            "single_flight": True,
            "position_aware": True,
            "restart_recovery": True,
            "health": self.health.to_dict(),
            "stop_requested": self._stop_requested or self.config.stop_file.exists(),
        }

    def _roll_24h_windows(self) -> None:
        cutoff = time.time() - 86400.0
        self._cycle_timestamps = [t for t in self._cycle_timestamps if t >= cutoff]
        self._error_timestamps = [t for t in self._error_timestamps if t >= cutoff]
        self._success_timestamps = [t for t in self._success_timestamps if t >= cutoff]
        self.health.cycles_24h = len(self._cycle_timestamps)
        self.health.errors_24h = len(self._error_timestamps)
        self.health.failed_cycles_24h = len(self._error_timestamps)
        self.health.successful_cycles_24h = len(self._success_timestamps)

    def _set_next_due(self, sleep_sec: float | None = None) -> None:
        due = time.time() + float(sleep_sec if sleep_sec is not None else self.config.cycle_sleep_sec)
        self.health.next_cycle_due_at = datetime.fromtimestamp(due, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    def run_one_autonomy_tick(self, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """One bounded scheduler tick: reconcile → manage OR entry cycle OR WAIT.

        Never starts a second tick while in-flight (single-flight).
        """
        context = dict(context or {})
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return {
                "ok": False,
                "skipped": True,
                "reason": "single_flight_busy",
                "service_status": self.health.service_status,
            }
        try:
            if self._in_flight:
                return {"ok": False, "skipped": True, "reason": "single_flight_busy"}
            if self._stop_requested or self.config.stop_file.exists():
                self.health.service_status = "STOPPED"
                self.save_state()
                return {"ok": True, "stopped": True, "service_status": "STOPPED"}

            self._in_flight = True
            started = time.time()
            self.health.last_cycle_started_at = _utc()
            self.health.service_status = "RUNNING"
            self.save_state()

            try:
                recon = self.reconcile_fn() if self.reconcile_fn else {"open": False}
                open_pos = bool(recon.get("open") or recon.get("POSITION_STILL_OPEN_MANAGED"))
                self.health.open_position = open_pos
                self.health.exchange_connectivity = recon.get("exchange_connectivity") or (
                    "OK" if recon.get("ok", True) else "DEGRADED"
                )

                if open_pos:
                    self.health.service_status = "MANAGING_POSITION"
                    manage_ctx = {
                        **context,
                        "reconcile": recon,
                        "max_manage_ticks": self.config.max_manage_ticks_per_invocation,
                        "manage_poll_sec": self.config.manage_poll_sec,
                    }
                    result = (
                        self.manage_fn(manage_ctx)
                        if self.manage_fn
                        else {
                            "ok": True,
                            "action": "HOLD",
                            "reason": "manage_fn_not_bound",
                            "POSITION_STILL_OPEN_MANAGED": True,
                        }
                    )
                    status = "MANAGING_POSITION"
                    if result.get("closed"):
                        status = "RUNNING"
                        self.health.open_position = False
                else:
                    # FLAT → one full opportunity cycle
                    result = (
                        self.cycle_fn(context)
                        if self.cycle_fn
                        else {"ok": True, "WAIT": True, "reason": "cycle_fn_not_bound"}
                    )
                    # V30.1: AI failure must NOT collapse into WAITING_MARKET
                    ai_failed = bool(result.get("ai_failed") or result.get("ai_entry_blocked"))
                    ai_state = result.get("ai_state")
                    self.health.ai_state = str(ai_state) if ai_state else self.health.ai_state
                    self.health.cycle_ai_ready = result.get("cycle_ai_ready")
                    self.health.market_scan_complete = result.get("market_scan_complete")
                    self.health.candidate_count = result.get("candidate_count")
                    # Record scan provenance for MANAGING_POSITION stdout.
                    self.health.last_flat_scan_candidate_count = self.health.candidate_count
                    self.health.last_flat_scan_at = _utc()
                    reasons = result.get("top_rejection_reasons")
                    self.health.top_rejection_reasons = list(reasons) if isinstance(reasons, list) else reasons

                    if ai_failed:
                        status = "DEGRADED"
                        self.health.degraded_reason = str(
                            result.get("ai_state") or result.get("reason") or "AI_UNAVAILABLE"
                        )
                        self.health.waiting_market_valid = False
                        self.health.cycles_error += 1
                        self._error_timestamps.append(time.time())
                    elif result.get("WAIT"):
                        # WAITING_MARKET only when scan completed and AI/data pipeline OK
                        scan_ok = bool(result.get("market_scan_complete", True))
                        ai_ok = result.get("cycle_ai_ready", True)
                        if scan_ok and ai_ok:
                            status = "WAITING_MARKET"
                            self.health.waiting_market_valid = True
                            self.health.cycles_wait += 1
                            self.health.degraded_reason = None
                        else:
                            status = "DEGRADED"
                            self.health.waiting_market_valid = False
                            self.health.degraded_reason = str(
                                result.get("reason") or "PIPELINE_INCOMPLETE"
                            )
                            self.health.cycles_error += 1
                            self._error_timestamps.append(time.time())
                    elif result.get("executed"):
                        status = "RUNNING"
                        self.health.waiting_market_valid = None
                        self.health.degraded_reason = None
                        if result.get("POSITION_STILL_OPEN_MANAGED") or result.get("position_open"):
                            self.health.open_position = True
                            status = "MANAGING_POSITION"
                    else:
                        if result.get("ok", True):
                            status = "WAITING_MARKET"
                            self.health.waiting_market_valid = bool(
                                result.get("market_scan_complete", False)
                            )
                            self.health.cycles_wait += 1
                        else:
                            status = "DEGRADED"
                            self.health.waiting_market_valid = False
                            self.health.degraded_reason = str(result.get("reason") or "CYCLE_FAILED")

                duration = time.time() - started
                self.health.last_cycle_completed_at = _utc()
                self.health.last_cycle_duration_sec = round(duration, 3)
                self.health.last_cycle_status = status
                self.health.service_status = status
                self.health.cycles_completed += 1
                self._cycle_timestamps.append(time.time())
                if status != "DEGRADED":
                    self._success_timestamps.append(time.time())
                self._roll_24h_windows()
                self._set_next_due()
                self.save_state()
                reconcile_public = (
                    {k: v for k, v in recon.items() if k != "manager"}
                    if isinstance(recon, dict)
                    else None
                )
                return {
                    "ok": True if status != "DEGRADED" else False,
                    "service_status": status,
                    "duration_sec": duration,
                    "result": result,
                    "reconcile": reconcile_public,
                    "health": self.health.to_dict(),
                }
            except Exception as exc:  # noqa: BLE001
                self.health.cycles_error += 1
                self._error_timestamps.append(time.time())
                self._roll_24h_windows()
                self.health.service_status = "DEGRADED"
                self.health.degraded_reason = type(exc).__name__
                self.health.last_cycle_completed_at = _utc()
                self.health.last_cycle_status = "ERROR"
                backoff = min(
                    self.config.backoff_max_sec,
                    self.config.backoff_base_sec * (2 ** min(5, self.health.cycles_error)),
                )
                self._set_next_due(backoff)
                self.save_state()
                return {
                    "ok": False,
                    "service_status": "DEGRADED",
                    "error": type(exc).__name__,
                    "detail": str(exc)[:400],
                    "blocks_trading_risk": False,
                    "health": self.health.to_dict(),
                }
        finally:
            self._in_flight = False
            self._lock.release()

    def restart_recovery(self) -> dict[str, Any]:
        """After process restart: restore scheduler state then Bybit-first reconcile."""
        self._load_state()
        recon = self.reconcile_fn() if self.reconcile_fn else {"open": False, "ok": True}
        if recon.get("open") or recon.get("POSITION_STILL_OPEN_MANAGED"):
            self.health.service_status = "MANAGING_POSITION"
            self.health.open_position = True
        else:
            self.health.service_status = "RUNNING"
            self.health.open_position = False
        self.health.exchange_connectivity = recon.get("exchange_connectivity") or "OK"
        self.save_state()
        recon_public = {k: v for k, v in recon.items() if k != "manager"}
        return {
            "ok": True,
            "restart_recovery": True,
            "service_status": self.health.service_status,
            "reconcile": recon_public,
            "no_duplicate_entry_guarantee": True,
        }
