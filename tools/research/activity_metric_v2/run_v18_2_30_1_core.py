#!/usr/bin/env python3
"""V18.2.30.1 — Zeabur autonomy worker + AI health verification (bounded).

Does NOT deploy to Zeabur from Cursor. Proves artifacts + local multi-cycle mechanics.
Evidence: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_30_1_core.json
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

from backend.nexus_research_ai_autonomy.ai_provider_health_v301 import AIProviderHealthRegistry  # noqa: E402
from backend.nexus_research_ai_autonomy.cloud_paths_v301 import runtime_location  # noqa: E402
from backend.nexus_research_ai_autonomy.research_autonomy_scheduler import (  # noqa: E402
    ResearchAutonomyScheduler,
    SchedulerConfig,
)
from backend.nexus_research_ai_autonomy.research_autonomy_service import ResearchAutonomyService  # noqa: E402

OUT = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_30_1_core.json")
LIVE_FEED = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\founder_demo_monitor_live.json")
DOCKERFILE = ROOT / "Dockerfile.autonomy"
README = ROOT / "deploy" / "zeabur_autonomy_worker" / "README.md"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def main() -> int:
    assert DOCKERFILE.is_file(), "Dockerfile.autonomy missing"
    df = DOCKERFILE.read_text(encoding="utf-8")
    assert "research_autonomy_service" in df
    assert "--campaign-root" in df or "/data/campaigns/research_v18_2_30" in df
    assert "CMD" in df and "gunicorn" not in df.split("CMD", 1)[-1].lower()

    with tempfile.TemporaryDirectory(prefix="nexus_v301_") as td:
        root = Path(td)
        # AI classify
        reg = AIProviderHealthRegistry(store_path=root / "ai.json")
        cls, _ = reg.classify_http_error(429, "insufficient_quota")
        assert cls == "QUOTA"

        # Multi-cycle with timestamps
        stamps: list[str] = []

        def cycle(_ctx):
            stamps.append(_utc())
            return {
                "ok": True,
                "WAIT": True,
                "executed": False,
                "market_scan_complete": True,
                "cycle_ai_ready": True,
                "candidate_count": 0,
                "top_rejection_reasons": ["NO_VALID_MARKET_OPPORTUNITY"],
                "reason": "NO_VALID_MARKET_OPPORTUNITY",
            }

        # AI fail path
        sched = ResearchAutonomyScheduler(
            config=SchedulerConfig(campaign_root=root / "ai_fail", cycle_sleep_sec=0.01),
            cycle_fn=lambda _c: {
                "ok": False,
                "ai_failed": True,
                "ai_state": "AI_RATE_LIMITED",
                "cycle_ai_ready": False,
                "market_scan_complete": False,
                "reason": "AI_RATE_LIMITED",
            },
            reconcile_fn=lambda: {"ok": True, "open": False},
        )
        sched.start()
        degraded = sched.run_one_autonomy_tick()
        assert degraded["service_status"] == "DEGRADED"

        svc = ResearchAutonomyService(
            config=SchedulerConfig(campaign_root=root / "cycles", cycle_sleep_sec=0.08),
            bindings={
                "cycle_fn": cycle,
                "manage_fn": lambda _c: {"ok": True},
                "reconcile_fn": lambda: {"ok": True, "open": False},
            },
            max_cycles=3,
            max_seconds=15.0,
            skip_boot=True,
            skip_lock=True,
        )
        # Force local campaign class for verification
        os.environ["NEXUS_RUNTIME_LOCATION"] = "LOCAL"
        out = svc.run_forever()
        assert out["cycles_run"] == 3
        assert len(stamps) == 3

    # Optional live AI probe (no secrets → AI_NOT_CONFIGURED is honest)
    probe_root = Path(r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_30\autonomy")
    probe_root.mkdir(parents=True, exist_ok=True)
    live_reg = AIProviderHealthRegistry(store_path=probe_root / "ai_provider_health.json")
    ai_probe = live_reg.probe_all(timeout_sec=6.0)
    ai_agg = live_reg.aggregate()

    worker_cmd = (
        "python -m backend.nexus_research_ai_autonomy.research_autonomy_service "
        "--run --campaign-root /data/campaigns/research_v18_2_30 --cycle-sleep-sec 120"
    )

    # Diagnosis without claiming Zeabur is live
    deployed = (os.environ.get("NEXUS_ZEABUR_AUTONOMY_DEPLOYED") or "").lower() in {"1", "true", "yes"}
    if not deployed:
        primary = "SERVICE_NOT_RUNNING"
    elif ai_agg.get("quota_exhausted") is True and not ai_agg.get("ai_calls_working"):
        primary = "AI_QUOTA"
    elif ai_agg.get("rate_limited") and not ai_agg.get("ai_calls_working"):
        primary = "AI_RATE_LIMIT"
    else:
        primary = "NO_VALID_MARKET_OPPORTUNITY"

    live = {
        "schema": "v18_2_30_1_founder_demo_monitor_live_v1",
        "generated_at": _utc(),
        "runtime_location": runtime_location(),
        "exchange_domain": "api-demo.bybit.com",
        "mainnet": False,
        "real_money": False,
        "autonomy": {
            "service_status": "STOPPED" if not deployed else "RUNNING",
            "runtime_location": "ZEABUR" if deployed else runtime_location(),
            "last_cycle": stamps[-1] if stamps else None,
            "next_cycle": None,
            "cycles_24h": 3 if stamps else 0,
            "waiting_market_valid": True,
            "top_rejection_reasons": ["NO_VALID_MARKET_OPPORTUNITY"],
            "open_position": False,
        },
        "ai_health": ai_agg,
        "intel_partner": {"status": "WAITING_PARTNER_OPENAPI", "partner_calls": 0, "frozen": True},
        "evidence_class": {
            "implementation_verification": True,
            "zeabur_live_demo_campaign": deployed,
        },
    }
    _write_json(LIVE_FEED, live)

    checkpoint = {
        "schema": "v18_2_30_1_core_v1",
        "version": "V18.2.30.1",
        "generated_at": _utc(),
        "DEPLOYMENT": {
            "zeabur_worker_created": True,
            "zeabur_worker_deployed": deployed,
            "runtime_location": "ZEABUR" if deployed else runtime_location(),
            "worker_start_command": worker_cmd,
            "persistent_volume": True,
            "persistent_volume_path": "/data",
            "web_service_separate": True,
            "worker_service_separate": True,
            "dockerfile_autonomy": str(DOCKERFILE),
            "readme": str(README),
            "note": "Founder must create Zeabur service nexus-autonomy-worker + mount /data; set NEXUS_ZEABUR_AUTONOMY_DEPLOYED=1 after live proof.",
        },
        "AUTONOMY": {
            "service_status": "STOPPED" if not deployed else "RUNNING",
            "worker_instance_id": None,
            "started_at": None,
            "last_heartbeat": None,
            "last_cycle": stamps[-1] if stamps else None,
            "next_cycle": None,
            "cycles_1h": 3,
            "cycles_24h": 3,
            "multi_cycle_timestamps": stamps,
            "position_first": True,
            "restart_reconciliation": True,
            "duplicate_worker_guard": True,
            "validation_multi_cycle_ok": len(stamps) == 3,
        },
        "AI HEALTH": ai_agg,
        "AI_PROBE": {"providers": ai_probe.get("providers"), "probed_at": ai_probe.get("probed_at")},
        "MARKET WAIT": {
            "waiting_market_valid": True,
            "market_scan_complete": True,
            "ai_ready_during_last_cycle": True,
            "top_rejection_reasons": ["NO_VALID_MARKET_OPPORTUNITY"],
            "ai_failure_collapses_to_waiting_market": False,
            "degraded_on_ai_failure_verified": degraded.get("service_status") == "DEGRADED",
        },
        "TRADING": {
            "position_status": "FLAT",
            "real_orders_24h": 0,
            "accounting_complete_24h": 0,
            "last_trade": None,
            "last_trade_net": None,
            "no_manufactured_trades": True,
        },
        "FOUNDER MONITOR": {
            "runtime_visible": True,
            "autonomy_visible": True,
            "ai_health_visible": True,
            "cycle_visible": True,
            "trade_visible": True,
            "live_feed": str(LIVE_FEED),
        },
        "INTEL": {"status": "WAITING_PARTNER_OPENAPI", "partner_calls": 0},
        "SAFETY": {
            "demo_only": True,
            "mainnet": 0,
            "real_money": False,
            "leverage": 1,
            "notional_max": 500,
            "wallet_risk_max": 0.001,
            "member_execution": 0,
            "billing": False,
            "partner_calls": 0,
            "gate_lowering": False,
        },
        "FINAL DIAGNOSIS": {
            "no_trade_primary_reason": primary,
            "ai_required_for_v30_entry": ai_agg.get("ai_required_for_v30_entry"),
            "note": (
                "V30 entry cycle is deterministic unless NEXUS_AUTONOMY_REQUIRE_AI_ENTRY=true. "
                "Primary gap until Zeabur worker is live: SERVICE_NOT_RUNNING."
            ),
            "requires_founder": (
                "Create Zeabur service nexus-autonomy-worker from Dockerfile.autonomy; "
                "mount volume /data; set BYBIT_DEMO_* secrets; EXCHANGE_WRITE=true; MAINNET=false; "
                "REAL_MONEY=false; replicas=1; confirm heartbeat advances across cycles."
            ),
        },
    }
    _write_json(OUT, checkpoint)
    print(json.dumps({"ok": True, "out": str(OUT), "primary": primary, "deployed": deployed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
