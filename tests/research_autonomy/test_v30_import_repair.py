"""V29 import repair — stable V30 production cycle tests."""

from __future__ import annotations

from backend.nexus_research_ai_autonomy.research_flat_cycle_v30 import run_v29_opportunity_cycle


def test_v30_production_cycle_dry_scan() -> None:
    out = run_v29_opportunity_cycle({"ai_aggregate": {"ai_calls_working": True}})
    assert out.get("reason") != "V29_IMPORT_FAILED"
    assert out.get("market_scan_complete") is True
    assert isinstance(out.get("candidate_count"), int)
    assert out.get("candidate_count", 0) >= 0


def test_v30_production_import_module() -> None:
    import backend.nexus_research_ai_autonomy.research_flat_cycle_v30  # noqa: F401
    from backend.nexus_research_ai_autonomy import v30_production_cycle as prod

    r = prod.run_dry_flat_cycle(exchange_write=False)
    assert r["market_scan_complete"] is True
    assert r["candidate_count"] is not None


def test_error_stdout_includes_detail(capsys) -> None:
    from backend.nexus_research_ai_autonomy.autonomy_stdout_v301 import observe_completed_tick
    from backend.nexus_research_ai_autonomy.research_autonomy_scheduler import SchedulerHealth

    health = SchedulerHealth(service_status="DEGRADED")
    last = {
        "service_status": "DEGRADED",
        "ok": False,
        "result": {
            "reason": "V29_IMPORT_FAILED",
            "detail": "ModuleNotFoundError:No module named 'backend.nexus_activity_metric_v2.activity_recovery'",
        },
    }
    observe_completed_tick(cycle_n=2, last=last, health=health)
    out = capsys.readouterr().out
    assert "error_detail=" in out
    assert "activity_recovery" in out
