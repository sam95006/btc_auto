"""V18.2.30 Research Autonomy Scheduler / lesson replay unit tests."""

from __future__ import annotations

from pathlib import Path

from backend.nexus_research_ai_autonomy.lesson_replay_v30 import (
    evaluate_candidate_lesson_replay,
    summarize_lesson_pipeline,
)
from backend.nexus_research_ai_autonomy.research_autonomy_scheduler import (
    ResearchAutonomyScheduler,
    SchedulerConfig,
)


def test_wait_does_not_stop_and_single_flight(tmp_path: Path) -> None:
    def cycle(_ctx):
        return {"ok": True, "WAIT": True, "reason": "NO_VALID", "executed": False}

    def reconcile():
        return {"ok": True, "open": False, "exchange_connectivity": "OK"}

    sched = ResearchAutonomyScheduler(
        config=SchedulerConfig(campaign_root=tmp_path, cycle_sleep_sec=1.0),
        cycle_fn=cycle,
        manage_fn=lambda _c: {"ok": True, "closed": False},
        reconcile_fn=reconcile,
    )
    sched.start()
    r = sched.run_one_autonomy_tick()
    assert r["ok"] is True
    assert r["service_status"] == "WAITING_MARKET"
    assert sched.health.service_status != "STOPPED"

    sched._in_flight = True  # noqa: SLF001
    skip = sched.run_one_autonomy_tick()
    assert skip.get("skipped") is True
    sched._in_flight = False  # noqa: SLF001


def test_position_first_skips_entry(tmp_path: Path) -> None:
    calls = {"cycle": 0, "manage": 0}

    def cycle(_ctx):
        calls["cycle"] += 1
        return {"ok": True, "WAIT": True, "executed": False}

    def manage(_ctx):
        calls["manage"] += 1
        return {"ok": True, "closed": False, "POSITION_STILL_OPEN_MANAGED": True, "action": "HOLD"}

    def reconcile():
        return {"ok": True, "open": True, "POSITION_STILL_OPEN_MANAGED": True}

    sched = ResearchAutonomyScheduler(
        config=SchedulerConfig(campaign_root=tmp_path),
        cycle_fn=cycle,
        manage_fn=manage,
        reconcile_fn=reconcile,
    )
    sched.start()
    r = sched.run_one_autonomy_tick()
    assert r["service_status"] == "MANAGING_POSITION"
    assert calls["manage"] == 1
    assert calls["cycle"] == 0


def test_restart_recovery_manage_vs_flat(tmp_path: Path) -> None:
    open_flag = {"open": True}

    def reconcile():
        return {"ok": True, "open": open_flag["open"], "POSITION_STILL_OPEN_MANAGED": open_flag["open"]}

    sched = ResearchAutonomyScheduler(
        config=SchedulerConfig(campaign_root=tmp_path),
        reconcile_fn=reconcile,
    )
    rec = sched.restart_recovery()
    assert rec["service_status"] == "MANAGING_POSITION"
    open_flag["open"] = False
    rec2 = sched.restart_recovery()
    assert rec2["service_status"] == "RUNNING"
    assert rec2["no_duplicate_entry_guarantee"] is True


def test_lesson_replay_insufficient_evidence() -> None:
    res = evaluate_candidate_lesson_replay(
        {"lesson_id": "L1", "mistake_signature": "NOISE_ENTRY", "state": "CANDIDATE", "origin_trade_id": "t0"},
        historical_trades=[
            {
                "trade_id": "t0",
                "net_realized": -1,
                "mistake_signature": "NOISE_ENTRY",
                "accounting_status": "ACCOUNTING_COMPLETE",
                "lifecycle_purpose": "RESEARCH_PNL_TRADE",
            }
        ],
    )
    assert res.insufficient_evidence is True
    assert res.lesson_stage == "CANDIDATE"
    assert res.replay_pass is False


def test_lesson_replay_pass_with_sample() -> None:
    hist = []
    for i in range(8):
        hist.append(
            {
                "trade_id": f"t{i}",
                "net_realized": -1.0 if i % 2 == 0 else 1.0,
                "mistake_signature": "NOISE_ENTRY" if i % 2 == 0 else "OTHER",
                "accounting_status": "ACCOUNTING_COMPLETE",
                "lifecycle_purpose": "RESEARCH_PNL_TRADE",
            }
        )
    res = evaluate_candidate_lesson_replay(
        {
            "lesson_id": "L2",
            "mistake_signature": "NOISE_ENTRY",
            "state": "CANDIDATE",
            "origin_trade_id": "origin",
        },
        historical_trades=hist,
    )
    assert res.sample_count >= 5
    assert res.insufficient_evidence is False
    pipe = summarize_lesson_pipeline([{"state": res.lesson_stage}])
    assert "candidate" in pipe
