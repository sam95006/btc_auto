"""V18.2.30.1 Persistent Research Autonomy Service (Zeabur-ready).

Owns the long-running loop. Cursor validation remains bounded elsewhere.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.ai_provider_health_v301 import AIProviderHealthRegistry
from backend.nexus_research_ai_autonomy.boot_health_v301 import run_boot_health
from backend.nexus_research_ai_autonomy.cloud_paths_v301 import (
    campaign_root as resolve_campaign_root,
    lock_dir,
    resolve_demo_env_path,
    runtime_location,
    worker_instance_id,
)
from backend.nexus_research_ai_autonomy.research_autonomy_scheduler import (
    DEFAULT_CAMPAIGN_ROOT,
    ResearchAutonomyScheduler,
    SchedulerConfig,
)
from backend.nexus_research_ai_autonomy.research_cycle_v30 import build_cycle_bindings
from backend.nexus_research_ai_autonomy.research_flat_cycle_v30 import run_v29_opportunity_cycle
from backend.runtime.single_instance_guard import SingleInstanceError, SingleInstanceGuard

SCHEMA = "v18_2_30_1_research_autonomy_service_v1"
CAMPAIGN_CLASS_ZEABUR = "ZEABUR_LIVE_DEMO_CAMPAIGN"
CAMPAIGN_CLASS_LOCAL = "LOCAL_VERIFICATION"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _apply_safety_env() -> None:
    os.environ.setdefault("EXCHANGE_WRITE", "true")
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    os.environ.setdefault("NEXUS_RESEARCH_AUTONOMY", "1")


def _default_bindings(*, campaign_root: Path, dry: bool = False) -> dict[str, Any]:
    demo_client = None
    try:
        from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
        from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import load_demo_env

        env_path = resolve_demo_env_path()
        load_demo_env(env_path)
        demo_client = DemoWriteClient()
    except Exception:  # noqa: BLE001
        demo_client = None
    return build_cycle_bindings(
        campaign_root=campaign_root,
        demo_client=demo_client,
        dry=dry,
        flat_cycle_fn=run_v29_opportunity_cycle,
    )


class ResearchAutonomyService:
    """Persistent service: boot → lock → recover → cadence ticks."""

    def __init__(
        self,
        *,
        config: SchedulerConfig | None = None,
        bindings: dict[str, Any] | None = None,
        max_cycles: int | None = None,
        max_seconds: float | None = None,
        skip_boot: bool = False,
        skip_lock: bool = False,
    ) -> None:
        _apply_safety_env()
        self.config = config or SchedulerConfig(campaign_root=resolve_campaign_root())
        self.worker_instance_id = worker_instance_id()
        self.runtime_location = runtime_location()
        self.campaign_class = (
            CAMPAIGN_CLASS_ZEABUR if self.runtime_location == "ZEABUR" else CAMPAIGN_CLASS_LOCAL
        )
        self.started_at = _utc()
        self.ai = AIProviderHealthRegistry(
            store_path=self.config.campaign_root / "autonomy" / "ai_provider_health.json"
        )
        bindings = bindings or _default_bindings(campaign_root=self.config.campaign_root)
        self.scheduler = ResearchAutonomyScheduler(
            config=self.config,
            cycle_fn=bindings.get("cycle_fn"),
            manage_fn=bindings.get("manage_fn"),
            reconcile_fn=bindings.get("reconcile_fn"),
        )
        self.scheduler.health.runtime_location = self.runtime_location
        self.scheduler.health.worker_instance_id = self.worker_instance_id
        self.scheduler.health.campaign_class = self.campaign_class
        self.max_cycles = max_cycles
        self.max_seconds = max_seconds
        self.skip_boot = skip_boot
        self.skip_lock = skip_lock
        self._guard: SingleInstanceGuard | None = None
        self._boot: dict[str, Any] | None = None
        self._cycles_1h: list[float] = []

    def run_forever(self) -> dict[str, Any]:
        """Persistent loop for Zeabur/runtime daemon — NOT for Cursor validation."""
        if not self.skip_lock:
            try:
                self._guard = SingleInstanceGuard(
                    "nexus_research_autonomy",
                    lock_dir=str(lock_dir()),
                )
                self._guard.acquire()
            except SingleInstanceError as exc:
                payload = {
                    "schema": SCHEMA,
                    "ok": False,
                    "BOOT_READY": False,
                    "error": "DUPLICATE_WORKER",
                    "detail": str(exc)[:300],
                    "worker_instance_id": self.worker_instance_id,
                    "runtime_location": self.runtime_location,
                }
                _write_json(self.config.campaign_root / "autonomy" / "boot_failed.json", payload)
                return payload

        if not self.skip_boot:
            self._boot = run_boot_health(
                campaign=self.config.campaign_root,
                ai_registry=self.ai,
                probe_ai=True,
            )
            _write_json(self.config.campaign_root / "autonomy" / "boot_health.json", self._boot)
            if not self._boot.get("BOOT_READY"):
                self.scheduler.health.service_status = "DEGRADED"
                self.scheduler.health.degraded_reason = ",".join(self._boot.get("blockers") or ["BOOT_FAILED"])
                self.scheduler.save_state()
                if self._guard:
                    self._guard.release()
                return {
                    "schema": SCHEMA,
                    "ok": False,
                    "BOOT_READY": False,
                    "boot": self._boot,
                    "worker_instance_id": self.worker_instance_id,
                    "runtime_location": self.runtime_location,
                }

        self.scheduler.start()
        recovery = self.scheduler.restart_recovery()
        started = time.time()
        cycles = 0
        last: dict[str, Any] = {}
        while True:
            if self.scheduler.config.stop_file.exists():
                break
            if self.max_cycles is not None and cycles >= self.max_cycles:
                break
            if self.max_seconds is not None and (time.time() - started) >= self.max_seconds:
                break

            # Periodic AI health probe (every cycle is fine at 120s cadence)
            try:
                self.ai.probe_all()
            except Exception:  # noqa: BLE001
                pass
            ai_agg = self.ai.aggregate()
            self.scheduler.health.ai_state = ai_agg.get("ai_state")

            last = self.scheduler.run_one_autonomy_tick(
                context={
                    "service": True,
                    "ai_aggregate": ai_agg,
                    "worker_instance_id": self.worker_instance_id,
                    "runtime_location": self.runtime_location,
                    "campaign_class": self.campaign_class,
                }
            )
            cycles += 1
            now = time.time()
            self._cycles_1h = [t for t in self._cycles_1h if t >= now - 3600.0]
            self._cycles_1h.append(now)
            self._persist_service_heartbeat(cycles=cycles, last=last, ai_agg=ai_agg)
            self._persist_founder_feed(last=last, ai_agg=ai_agg)

            sleep_sec = float(self.config.cycle_sleep_sec)
            if last.get("service_status") == "MANAGING_POSITION":
                sleep_sec = float(self.config.manage_poll_sec)
            if last.get("skipped"):
                sleep_sec = min(sleep_sec, 5.0)
            end_sleep = time.time() + sleep_sec
            while time.time() < end_sleep:
                if self.scheduler.config.stop_file.exists():
                    break
                time.sleep(min(2.0, max(0.01, end_sleep - time.time())))

        self.scheduler.stop()
        if self._guard:
            self._guard.release()
        return {
            "schema": SCHEMA,
            "stopped_at": _utc(),
            "cycles_run": cycles,
            "recovery": recovery,
            "boot": self._boot,
            "last": last,
            "health": self.scheduler.health_snapshot(),
            "worker_instance_id": self.worker_instance_id,
            "runtime_location": self.runtime_location,
            "campaign_class": self.campaign_class,
        }

    def _persist_service_heartbeat(
        self, *, cycles: int, last: dict[str, Any], ai_agg: dict[str, Any]
    ) -> None:
        h = self.scheduler.health
        path = self.config.campaign_root / "autonomy" / "service_heartbeat.json"
        payload = {
            "schema": SCHEMA,
            "campaign_class": self.campaign_class,
            "runtime_location": self.runtime_location,
            "worker_instance_id": self.worker_instance_id,
            "worker_started_at": self.started_at,
            "last_heartbeat_at": _utc(),
            "service_status": last.get("service_status") or h.service_status,
            "last_cycle_started": h.last_cycle_started_at,
            "last_cycle_completed": h.last_cycle_completed_at,
            "next_cycle_due": h.next_cycle_due_at,
            "cycles_run": cycles,
            "cycles_1h": len(self._cycles_1h),
            "cycles_24h": h.cycles_24h,
            "successful_cycles_24h": h.successful_cycles_24h,
            "failed_cycles_24h": h.failed_cycles_24h,
            "waiting_market_valid": h.waiting_market_valid,
            "market_scan_complete": h.market_scan_complete,
            "cycle_ai_ready": h.cycle_ai_ready,
            "top_rejection_reasons": h.top_rejection_reasons,
            "ai": ai_agg,
            "health": h.to_dict(),
            "BOOT_READY": True if self._boot is None else bool(self._boot.get("BOOT_READY")),
        }
        _write_json(path, payload)
        # Founder-visible cloud status mirror
        _write_json(self.config.campaign_root / "autonomy" / "cloud_campaign_status.json", {
            "schema": "v18_2_30_1_cloud_campaign_status_v1",
            "campaign_class": self.campaign_class,
            "runtime_location": self.runtime_location,
            "service_status": payload["service_status"],
            "last_heartbeat_at": payload["last_heartbeat_at"],
            "worker_instance_id": self.worker_instance_id,
            "ai_state": (ai_agg or {}).get("ai_state"),
        })

    def _persist_founder_feed(self, *, last: dict[str, Any], ai_agg: dict[str, Any]) -> None:
        """Write Founder monitor feed under /data (shared volume), not D:\\."""
        from backend.nexus_research_ai_autonomy.cloud_paths_v301 import evidence_dir

        h = self.scheduler.health
        result = last.get("result") if isinstance(last.get("result"), dict) else {}
        feed = {
            "schema": "v18_2_30_1_founder_demo_monitor_live_v1",
            "generated_at": _utc(),
            "runtime_location": self.runtime_location,
            "campaign_class": self.campaign_class,
            "exchange_domain": "api-demo.bybit.com",
            "mainnet": False,
            "real_money": False,
            "position_state": "OPEN" if h.open_position else "FLAT",
            "autonomy": {
                "service_status": last.get("service_status") or h.service_status,
                "runtime_location": self.runtime_location,
                "worker_instance_id": self.worker_instance_id,
                "last_cycle": h.last_cycle_completed_at,
                "next_cycle": h.next_cycle_due_at,
                "cycles_24h": h.cycles_24h,
                "errors_24h": h.errors_24h,
                "open_position": h.open_position,
                "waiting_market_valid": h.waiting_market_valid,
                "top_rejection_reasons": h.top_rejection_reasons,
                "exchange_connectivity": h.exchange_connectivity,
                "market_data_health": h.market_data_health,
            },
            "ai_health": ai_agg,
            "last_completed_trade": None,
            "market": {
                "last_wait_reason": result.get("reason") or h.degraded_reason,
                "market_scan_complete": h.market_scan_complete,
                "candidate_count": h.candidate_count,
            },
            "intel_partner": {"status": "WAITING_PARTNER_OPENAPI", "partner_calls": 0},
            "secrets_redacted": True,
        }
        out = evidence_dir() / "founder_demo_monitor_live.json"
        _write_json(out, feed)
        # Also mirror beside campaign for ops without evidence_coordinator mount.
        _write_json(self.config.campaign_root / "autonomy" / "founder_demo_monitor_live.json", feed)


def launch_detached(
    *,
    repo_root: Path,
    campaign_root: Path | None = None,
    cycle_sleep_sec: float = 120.0,
    python_exe: str | None = None,
    exchange_write: bool = False,
) -> dict[str, Any]:
    """Start persistent autonomy as a detached OS process (local Windows helper)."""
    root = Path(campaign_root or resolve_campaign_root())
    (root / "autonomy").mkdir(parents=True, exist_ok=True)
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    py = python_exe or sys.executable
    stdout_log = logs / "autonomy_stdout.log"
    stderr_log = logs / "autonomy_stderr.log"
    cmd = [
        py,
        "-m",
        "backend.nexus_research_ai_autonomy.research_autonomy_service",
        "--run",
        "--campaign-root",
        str(root),
        "--cycle-sleep-sec",
        str(cycle_sleep_sec),
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    env["EXCHANGE_WRITE"] = "true" if exchange_write else "false"
    env["MAINNET"] = "false"
    env["REAL_MONEY"] = "false"
    env["NEXUS_RESEARCH_AUTONOMY"] = "1"
    env["NEXUS_CAMPAIGN_ROOT"] = str(root)

    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        )

    fout = open(stdout_log, "a", encoding="utf-8")
    ferr = open(stderr_log, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_root),
        env=env,
        stdout=fout,
        stderr=ferr,
        creationflags=creationflags,
        close_fds=True,
    )
    meta = {
        "schema": f"{SCHEMA}_launch",
        "pid": proc.pid,
        "campaign_root": str(root),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "exchange_write": exchange_write,
        "started_at": _utc(),
        "detached": True,
        "cursor_validation_runner": False,
        "runtime_location": runtime_location(),
    }
    _write_json(root / "autonomy" / "service_launch.json", meta)
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEXUS V18.2.30.1 Research Autonomy Service")
    parser.add_argument("--run", action="store_true", help="Run persistent autonomy loop")
    parser.add_argument(
        "--campaign-root",
        type=str,
        default=None,
        help="Cloud-safe campaign root (default: NEXUS_CAMPAIGN_ROOT or /data/campaigns/...)",
    )
    parser.add_argument("--cycle-sleep-sec", type=float, default=120.0)
    parser.add_argument("--manage-poll-sec", type=float, default=15.0)
    parser.add_argument("--max-cycles", type=int, default=None)
    parser.add_argument("--max-seconds", type=float, default=None)
    parser.add_argument("--skip-boot", action="store_true")
    parser.add_argument("--skip-lock", action="store_true")
    args = parser.parse_args(argv)

    if not args.run:
        print(json.dumps({"ok": False, "reason": "pass --run"}, indent=2))
        return 2

    root = Path(args.campaign_root) if args.campaign_root else resolve_campaign_root()
    os.environ["NEXUS_CAMPAIGN_ROOT"] = str(root)
    cfg = SchedulerConfig(
        campaign_root=root,
        cycle_sleep_sec=float(args.cycle_sleep_sec),
        manage_poll_sec=float(args.manage_poll_sec),
    )
    svc = ResearchAutonomyService(
        config=cfg,
        max_cycles=args.max_cycles,
        max_seconds=args.max_seconds,
        skip_boot=bool(args.skip_boot),
        skip_lock=bool(args.skip_lock),
    )
    result = svc.run_forever()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok", True) and result.get("BOOT_READY", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
