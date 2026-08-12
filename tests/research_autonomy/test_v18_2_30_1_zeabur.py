"""V18.2.30.1 unit tests — cloud paths, AI wait semantics, multi-cycle cadence."""

from __future__ import annotations

import os
from pathlib import Path

from backend.nexus_research_ai_autonomy.ai_provider_health_v301 import AIProviderHealthRegistry
from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root, runtime_location
from backend.nexus_research_ai_autonomy.research_autonomy_scheduler import (
    ResearchAutonomyScheduler,
    SchedulerConfig,
)
from backend.nexus_research_ai_autonomy.research_autonomy_service import ResearchAutonomyService


def test_cloud_campaign_root_zeabur(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_RUNTIME_LOCATION", "ZEABUR")
    monkeypatch.setenv("NEXUS_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.delenv("NEXUS_CAMPAIGN_ROOT", raising=False)
    assert runtime_location() == "ZEABUR"
    root = campaign_root()
    assert str(root).replace("\\", "/").endswith("/campaigns/research_v18_2_30")
    assert str(tmp_path / "data") in str(root) or str(root).startswith(str(tmp_path))


def test_ai_failure_is_degraded_not_waiting_market(tmp_path: Path) -> None:
    def cycle(_ctx):
        return {
            "ok": False,
            "WAIT": False,
            "executed": False,
            "ai_failed": True,
            "ai_state": "AI_QUOTA_EXHAUSTED",
            "cycle_ai_ready": False,
            "market_scan_complete": False,
            "reason": "AI_QUOTA_EXHAUSTED",
        }

    def reconcile():
        return {"ok": True, "open": False}

    sched = ResearchAutonomyScheduler(
        config=SchedulerConfig(campaign_root=tmp_path, cycle_sleep_sec=0.01),
        cycle_fn=cycle,
        reconcile_fn=reconcile,
    )
    sched.start()
    r = sched.run_one_autonomy_tick()
    assert r["service_status"] == "DEGRADED"
    assert r["service_status"] != "WAITING_MARKET"
    assert sched.health.degraded_reason == "AI_QUOTA_EXHAUSTED"


def test_valid_wait_requires_scan_and_ai_ready(tmp_path: Path) -> None:
    def cycle(_ctx):
        return {
            "ok": True,
            "WAIT": True,
            "executed": False,
            "reason": "NO_VALID_MARKET_OPPORTUNITY",
            "market_scan_complete": True,
            "cycle_ai_ready": True,
            "candidate_count": 12,
            "top_rejection_reasons": ["ENTRY_QUALITY"],
        }

    sched = ResearchAutonomyScheduler(
        config=SchedulerConfig(campaign_root=tmp_path, cycle_sleep_sec=0.01),
        cycle_fn=cycle,
        reconcile_fn=lambda: {"ok": True, "open": False},
    )
    sched.start()
    r = sched.run_one_autonomy_tick()
    assert r["service_status"] == "WAITING_MARKET"
    assert sched.health.waiting_market_valid is True


def test_bounded_multi_cycle_cadence(tmp_path: Path) -> None:
    n = {"i": 0}

    def cycle(_ctx):
        n["i"] += 1
        return {
            "ok": True,
            "WAIT": True,
            "executed": False,
            "market_scan_complete": True,
            "cycle_ai_ready": True,
            "reason": f"WAIT_{n['i']}",
        }

    svc = ResearchAutonomyService(
        config=SchedulerConfig(campaign_root=tmp_path, cycle_sleep_sec=0.05),
        bindings={
            "cycle_fn": cycle,
            "manage_fn": lambda _c: {"ok": True, "closed": False},
            "reconcile_fn": lambda: {"ok": True, "open": False},
        },
        max_cycles=3,
        max_seconds=10.0,
        skip_boot=True,
        skip_lock=True,
    )
    out = svc.run_forever()
    assert out["cycles_run"] == 3
    hb = tmp_path / "autonomy" / "service_heartbeat.json"
    assert hb.is_file()


def test_ai_registry_classifies_quota(tmp_path: Path) -> None:
    reg = AIProviderHealthRegistry(store_path=tmp_path / "ai.json")
    cls, code = reg.classify_http_error(429, '{"error":{"code":"insufficient_quota"}}')
    assert cls == "QUOTA"
    ph = reg.record(
        profile="GROQ_MAIN_REASONER",
        provider="groq",
        model="x",
        ok=False,
        status="HTTP_429",
        error_class=cls,
        error_code=code,
    )
    assert ph.ai_state == "AI_QUOTA_EXHAUSTED"
    agg = reg.aggregate()
    assert agg["quota_exhausted"] is True


def test_dockerfile_autonomy_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "Dockerfile.autonomy").is_file()
    text = (root / "Dockerfile.autonomy").read_text(encoding="utf-8")
    assert "research_autonomy_service" in text
    assert "gunicorn" not in text.lower() or "Do NOT start Gunicorn" in text
    assert "/data/campaigns/research_v18_2_30" in text
