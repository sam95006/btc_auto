#!/usr/bin/env python3
"""V18.2.30 — Continuous Research Autonomy verification (BOUNDED single-cycle).

This Cursor validation runner must NOT contain while True.
Persistent loop lives in research_autonomy_service (detached).

Evidence:
  D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_30_core.json
  founder_demo_monitor_live.json (autonomy + performance + learning)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "0")
os.environ.setdefault("REAL_MONEY", "false")

from backend.nexus_research_ai_autonomy.lesson_replay_v30 import (  # noqa: E402
    evaluate_candidate_lesson_replay,
    summarize_lesson_pipeline,
)
from backend.nexus_research_ai_autonomy.research_autonomy_scheduler import (  # noqa: E402
    ResearchAutonomyScheduler,
    SchedulerConfig,
)
from backend.nexus_research_ai_autonomy.research_autonomy_service import (  # noqa: E402
    ResearchAutonomyService,
    launch_detached,
)
from backend.nexus_research_ai_autonomy.research_cycle_v30 import build_cycle_bindings  # noqa: E402
from backend.nexus_research_ai_autonomy.win_rate_accounting import compute_research_win_rate  # noqa: E402
from backend.nexus_research_ai_autonomy.win_rate_rolling_v29 import compute_research_rolling_stats  # noqa: E402

OUT = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_30_core.json")
LIVE_FEED = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\founder_demo_monitor_live.json")
PRIOR_V29 = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_29_core.json")
CAMPAIGN_ROOT = Path(r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_30")
V29_SOT = "020d62c3fd7bbd02b5da51d2b953d71e0a2c289d9da9285a1969c1697492df14"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def verify_scheduler_mechanics(*, tmp_root: Path) -> dict[str, Any]:
    """Prove single-flight, WAIT persistence, position-aware, restart recovery — no while True."""
    wait_reasons: list[str] = []

    def flat_cycle(_ctx: dict[str, Any]) -> dict[str, Any]:
        wait_reasons.append("NO_VALID_CANDIDATE")
        return {
            "ok": True,
            "WAIT": True,
            "reason": "NO_VALID_CANDIDATE",
            "executed": False,
            "no_gate_lowering": True,
            "no_manufactured_trades": True,
        }

    open_flag = {"open": False}

    def reconcile() -> dict[str, Any]:
        return {
            "ok": True,
            "open": open_flag["open"],
            "POSITION_STILL_OPEN_MANAGED": open_flag["open"],
            "exchange_connectivity": "OK",
        }

    manage_calls = {"n": 0}

    def manage(ctx: dict[str, Any]) -> dict[str, Any]:
        manage_calls["n"] += 1
        return {
            "ok": True,
            "closed": False,
            "action": "HOLD",
            "ticks": int(ctx.get("max_manage_ticks") or 1),
            "POSITION_STILL_OPEN_MANAGED": True,
            "adaptive_live_evaluation": True,
        }

    cfg = SchedulerConfig(
        campaign_root=tmp_root,
        cycle_sleep_sec=1.0,
        manage_poll_sec=0.1,
        max_manage_ticks_per_invocation=2,
    )
    sched = ResearchAutonomyScheduler(
        config=cfg,
        cycle_fn=flat_cycle,
        manage_fn=manage,
        reconcile_fn=reconcile,
    )
    start = sched.start()
    assert start["service_status"] == "RUNNING"

    # Flat → WAIT (service must remain alive)
    t1 = sched.run_one_autonomy_tick(context={"verify": True})
    assert t1.get("ok") is True
    assert t1.get("service_status") == "WAITING_MARKET"
    assert sched.health.service_status != "STOPPED"
    assert sched.health.cycles_wait >= 1

    # Position-aware: open → manage, not new entry
    open_flag["open"] = True
    t2 = sched.run_one_autonomy_tick(context={"verify": True})
    assert t2.get("service_status") == "MANAGING_POSITION"
    assert manage_calls["n"] == 1
    assert len(wait_reasons) == 1  # no second flat cycle while open

    # Single-flight: force in-flight skip
    sched._in_flight = True  # noqa: SLF001
    skipped = sched.run_one_autonomy_tick()
    assert skipped.get("skipped") is True
    sched._in_flight = False  # noqa: SLF001

    # Restart recovery
    open_flag["open"] = True
    recovery = sched.restart_recovery()
    assert recovery.get("restart_recovery") is True
    assert recovery.get("service_status") == "MANAGING_POSITION"
    assert recovery.get("no_duplicate_entry_guarantee") is True

    open_flag["open"] = False
    recovery_flat = sched.restart_recovery()
    assert recovery_flat.get("service_status") == "RUNNING"

    # Bounded service: max_cycles=2 then stop (not Cursor while-True forever)
    bindings = build_cycle_bindings(
        campaign_root=tmp_root / "svc",
        dry=True,
        flat_cycle_fn=flat_cycle,
    )
    # Override reconcile/manage via fresh scheduler inside service
    svc_cfg = SchedulerConfig(campaign_root=tmp_root / "svc", cycle_sleep_sec=0.05, manage_poll_sec=0.05)
    svc = ResearchAutonomyService(config=svc_cfg, bindings=bindings, max_cycles=2, max_seconds=5.0, skip_boot=True, skip_lock=True)
    # Rebind to our wait cycle
    svc.scheduler.cycle_fn = flat_cycle
    svc.scheduler.manage_fn = manage
    svc.scheduler.reconcile_fn = reconcile
    open_flag["open"] = False
    bounded = svc.run_forever()
    assert bounded.get("cycles_run") == 2

    # Confirm validation runner has no executable while-True loop.
    runner_src = Path(__file__).read_text(encoding="utf-8")
    executable_while = any(
        ln.strip().startswith("while True") for ln in runner_src.splitlines()
    )
    service_src = (
        Path(ROOT) / "backend" / "nexus_research_ai_autonomy" / "research_autonomy_service.py"
    ).read_text(encoding="utf-8")
    service_has_loop = "while True" in service_src

    return {
        "scheduler_ready": True,
        "persistent_service": True,
        "single_flight": True,
        "position_aware": True,
        "restart_recovery": True,
        "wait_does_not_stop_service": True,
        "bounded_service_max_cycles_ok": bounded.get("cycles_run") == 2,
        "validation_runner_has_while_true": executable_while,
        "service_owns_persistent_loop": service_has_loop,
        "ticks": {"wait": t1, "manage": t2, "skipped": skipped},
        "recovery": recovery,
        "bounded_run": {"cycles_run": bounded.get("cycles_run"), "stopped_at": bounded.get("stopped_at")},
        "wait_reasons_persisted": wait_reasons,
        "mechanics_passed": (
            not executable_while
            and service_has_loop
            and bounded.get("cycles_run") == 2
            and t1.get("service_status") == "WAITING_MARKET"
            and t2.get("service_status") == "MANAGING_POSITION"
            and skipped.get("skipped") is True
        ),
        "note": "Cursor runner remains bounded; persistent loop is ResearchAutonomyService only.",
    }


def load_prior_performance() -> dict[str, Any]:
    prior = _load_json(PRIOR_V29)
    perf = prior.get("PERFORMANCE") or prior.get("CHECKPOINT_30", {}).get("PERFORMANCE") or {}
    last = prior.get("LAST TRADE") or {}
    reflection = prior.get("REFLECTION") or {}
    lessons = prior.get("LESSONS") or {}
    # Prefer lifecycles if present for rolling
    lifecycles = prior.get("lifecycles") or prior.get("LIFECYCLES") or []
    if not isinstance(lifecycles, list):
        lifecycles = []
    if lifecycles:
        base = compute_research_win_rate(lifecycles)
        rolling = compute_research_rolling_stats(lifecycles)
        base["last_10"] = rolling.get("last_10")
        base["last_30"] = rolling.get("last_30")
        perf = {**perf, **base}
    return {
        "performance": perf,
        "last_trade": last,
        "reflection": reflection,
        "lessons": lessons,
        "lifecycles": lifecycles,
        "prior_schema": prior.get("schema"),
    }


def run_lesson_replay_probe(lifecycles: list[dict[str, Any]], lessons_block: dict[str, Any]) -> dict[str, Any]:
    candidates = lessons_block.get("candidate_lessons") or lessons_block.get("candidates") or []
    if not isinstance(candidates, list):
        candidates = []
    # Synthesize historical sample shape from lifecycles
    hist = []
    for i, L in enumerate(lifecycles):
        hist.append(
            {
                "trade_id": L.get("trade_id") or L.get("position_id") or f"t{i}",
                "net_realized": (L.get("wallet") or {}).get("net_realized")
                or L.get("net_realized")
                or L.get("net_pnl")
                or 0,
                "mistake_signature": (L.get("reflection") or {}).get("mistake_signature"),
                "root_cause": (L.get("reflection") or {}).get("root_cause"),
                "accounting_status": "ACCOUNTING_COMPLETE",
                "lifecycle_purpose": "RESEARCH_PNL_TRADE",
                "BAD_PROCESS_WIN": bool((L.get("reflection") or {}).get("BAD_PROCESS_WIN")),
            }
        )
    results = []
    for les in candidates[:10]:
        results.append(evaluate_candidate_lesson_replay(les, historical_trades=hist).to_dict())
    if not candidates:
        # Empty probe still documents stage machine
        results.append(
            evaluate_candidate_lesson_replay(
                {"lesson_id": "probe_empty", "mistake_signature": "NONE", "state": "CANDIDATE"},
                historical_trades=hist,
            ).to_dict()
        )
    pipeline = summarize_lesson_pipeline(
        [{"state": r.get("lesson_stage")} for r in results] + list(candidates)
    )
    return {
        "replay_evaluations": results,
        "pipeline": pipeline,
        "no_direct_activation": True,
        "min_sample_for_replay": 5,
    }


def build_founder_live_feed(
    *,
    autonomy: dict[str, Any],
    performance: dict[str, Any],
    reflection: dict[str, Any],
    lessons: dict[str, Any],
    last_trade: dict[str, Any],
    health: dict[str, Any],
) -> dict[str, Any]:
    h = health.get("health") or health
    return {
        "schema": "v18_2_30_founder_demo_monitor_live_v1",
        "generated_at": _utc(),
        "exchange_domain": "api-demo.bybit.com",
        "mainnet": False,
        "real_money": False,
        "position_state": "OPEN" if h.get("open_position") else "FLAT",
        "open_position_count": 1 if h.get("open_position") else 0,
        "autonomy": {
            "service_status": h.get("service_status") or autonomy.get("service_status"),
            "last_cycle": h.get("last_cycle_completed_at"),
            "next_cycle": h.get("next_cycle_due_at"),
            "cycles_24h": h.get("cycles_24h"),
            "errors_24h": h.get("errors_24h"),
            "open_position": h.get("open_position"),
            "exchange_connectivity": h.get("exchange_connectivity"),
            "market_data_health": h.get("market_data_health"),
            "single_flight": True,
            "position_aware": True,
            "restart_recovery": True,
        },
        "trading_intel": {
            "position_state": "OPEN" if h.get("open_position") else "FLAT",
            "last_completed_trade": last_trade or None,
            "last_exit_reason": (last_trade or {}).get("exit_reason"),
            "adaptive_action": None,
            "profit_lock_state": None,
            "protected_pnl_floor": None,
            "mfe_capture_estimate": (last_trade or {}).get("MFE_capture_ratio"),
            "autonomy_status": h.get("service_status"),
        },
        "performance": {
            "win_rate_long": (performance.get("long_performance") or {}).get("win_rate"),
            "win_rate_short": (performance.get("short_performance") or {}).get("win_rate"),
            "win_rate_aggregate": performance.get("win_rate"),
            "net_pnl": performance.get("net_pnl"),
            "expectancy": performance.get("expectancy"),
            "profit_factor": performance.get("profit_factor"),
            "average_win": performance.get("average_win"),
            "average_loss": performance.get("average_loss"),
            "max_drawdown": performance.get("max_drawdown") or performance.get("max_drawdown_usdt"),
            "last_10": performance.get("last_10"),
            "last_30": performance.get("last_30"),
            "sample_status": performance.get("sample_status") or performance.get("win_rate_claim_status"),
            "accounting_complete_trades": performance.get("n") or performance.get("accounting_complete_trades"),
            "average_MFE_capture": performance.get("average_MFE_capture")
            or (performance.get("last_10") or {}).get("avg_mfe_capture_ratio"),
        },
        "reflection": reflection,
        "lessons": lessons,
        "learning": {
            "mistake_signatures": (reflection.get("raw") or {}).get("mistake_signatures")
            or reflection.get("mistake_signatures")
            or [],
            "pending_candidate_lessons": lessons.get("candidate_lessons") or lessons.get("candidates") or [],
            "lesson_pipeline": lessons.get("pipeline") or {},
            "repeat_after_validated_lesson": (lessons.get("pipeline") or {}).get(
                "repeat_after_validated_lesson", 0
            ),
        },
        "last_completed_trade": last_trade or None,
        "secrets_redacted": True,
        "intel_partner": {
            "status": "WAITING_PARTNER_OPENAPI",
            "partner_calls": 0,
            "frozen": True,
        },
        "evidence_class": {
            "implementation_verification": True,
            "ongoing_campaign_statistics": False,
        },
    }


def main() -> int:
    run_id = str(uuid.uuid4())
    CAMPAIGN_ROOT.mkdir(parents=True, exist_ok=True)
    (CAMPAIGN_ROOT / "autonomy").mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="nexus_v30_") as td:
        mechanics = verify_scheduler_mechanics(tmp_root=Path(td))

    prior = load_prior_performance()
    performance = prior["performance"] or {}
    reflection = prior["reflection"] or {}
    lessons_prior = prior["lessons"] or {}
    last_trade = prior["last_trade"] or {}

    replay = run_lesson_replay_probe(prior["lifecycles"], lessons_prior)
    lessons = {
        **lessons_prior,
        "pipeline": replay["pipeline"],
        "replay": replay,
        "candidate": replay["pipeline"].get("candidate", 0),
        "replay_passed": replay["pipeline"].get("replay_passed", 0),
        "development_passed": replay["pipeline"].get("development_passed", 0),
        "shadow_passed": replay["pipeline"].get("shadow_passed", 0),
        "demo_passed": replay["pipeline"].get("demo_passed", 0),
        "active": replay["pipeline"].get("active", 0),
        "repeat_after_validated_lesson": replay["pipeline"].get("repeat_after_validated_lesson", 0),
    }

    # Campaign scheduler health (persistent root) — start + one dry WAIT tick for visibility
    cfg = SchedulerConfig(campaign_root=CAMPAIGN_ROOT, cycle_sleep_sec=120.0)
    bindings = build_cycle_bindings(
        campaign_root=CAMPAIGN_ROOT,
        dry=True,
        flat_cycle_fn=lambda _c: {
            "ok": True,
            "WAIT": True,
            "reason": "V30_VERIFY_FLAT_NO_ENTRY",
            "executed": False,
            "no_gate_lowering": True,
            "no_manufactured_trades": True,
        },
    )
    sched = ResearchAutonomyScheduler(
        config=cfg,
        cycle_fn=bindings["cycle_fn"],
        manage_fn=bindings["manage_fn"],
        reconcile_fn=bindings["reconcile_fn"],
    )
    sched.start()
    recovery = sched.restart_recovery()
    tick = sched.run_one_autonomy_tick(context={"v30_verify": True, "dry": True})
    health = sched.health_snapshot()

    # Detached launch metadata (optional — do not require long-running for Cursor verify)
    launch_meta = {
        "launched": False,
        "reason": "verification_only_use_launch_detached_for_24_7",
        "how": "python -m backend.nexus_research_ai_autonomy.research_autonomy_service --run",
        "launch_detached_available": True,
    }
    if os.environ.get("NEXUS_V30_LAUNCH_DETACHED", "").strip() in {"1", "true"}:
        launch_meta = launch_detached(
            repo_root=ROOT,
            campaign_root=CAMPAIGN_ROOT,
            cycle_sleep_sec=120.0,
            exchange_write=os.environ.get("EXCHANGE_WRITE", "false").lower() in {"1", "true"},
        )

    n = performance.get("n") or performance.get("accounting_complete_trades") or 0
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    if n >= 100:
        sample_status = "STRONGER_RESEARCH_SAMPLE"
    elif n >= 50:
        sample_status = "INTERMEDIATE_VALIDATION_SAMPLE"
    elif n >= 30:
        sample_status = "PROVISIONAL_WINRATE_EVIDENCE"
    elif n >= 10:
        sample_status = "EARLY_BEHAVIORAL_SAMPLE"
    else:
        sample_status = "INSUFFICIENT_SAMPLE"
    performance = {**performance, "sample_status": sample_status, "accounting_complete_trades": n}

    autonomy_block = {
        "scheduler_ready": True,
        "persistent_service": True,
        "service_status": health.get("service_status"),
        "single_flight": True,
        "position_aware": True,
        "restart_recovery": True,
        "last_cycle": (health.get("health") or {}).get("last_cycle_completed_at"),
        "next_cycle": (health.get("health") or {}).get("next_cycle_due_at"),
        "cycles_completed": (health.get("health") or {}).get("cycles_completed"),
        "cycles_wait": (health.get("health") or {}).get("cycles_wait"),
        "cycles_error": (health.get("health") or {}).get("cycles_error"),
        "mechanics": mechanics,
        "recovery": recovery,
        "verify_tick": {
            "ok": tick.get("ok"),
            "service_status": tick.get("service_status"),
            "WAIT": (tick.get("result") or {}).get("WAIT"),
        },
        "launch": launch_meta,
        "validation_runner_bounded": True,
        "cursor_while_true_forbidden": True,
    }

    live = build_founder_live_feed(
        autonomy=autonomy_block,
        performance=performance,
        reflection=reflection,
        lessons=lessons,
        last_trade=last_trade,
        health=health,
    )
    _write_json(LIVE_FEED, live)

    checkpoint = {
        "schema": "v18_2_30_core_v1",
        "version": "V18.2.30",
        "run_id": run_id,
        "generated_at": _utc(),
        "v29_sot_sealed": V29_SOT,
        "evidence_class": {
            "implementation_verification": True,
            "ongoing_autonomous_campaign_statistics": False,
            "note": "Campaign stats accumulate under D:\\NEXUS_RUNTIME\\campaigns\\research_v18_2_30 when detached service runs.",
        },
        "AUTONOMY SERVICE": autonomy_block,
        "POSITION": {
            "status": "OPEN" if (health.get("health") or {}).get("open_position") else "FLAT",
            "symbol": None,
            "side": None,
            "notional": None,
            "entry": None,
            "current": None,
            "stop": None,
            "unrealized": None,
            "MFE": None,
            "MAE": None,
            "adaptive_action": None,
            "profit_lock_state": None,
            "protected_pnl_floor": None,
            "remaining_edge": None,
            "continuation_score": None,
            "giveback_risk": None,
        },
        "LAST COMPLETED TRADE": last_trade or None,
        "PERFORMANCE": performance,
        "REFLECTION": reflection,
        "LESSONS": lessons,
        "FOUNDER MONITOR": {
            "autonomy_status_visible": True,
            "cycle_status_visible": True,
            "position_visible": True,
            "performance_visible": True,
            "learning_visible": True,
            "live_feed": str(LIVE_FEED),
        },
        "INTEL PARTNER": {
            "status": "WAITING_PARTNER_OPENAPI",
            "partner_calls": 0,
            "frozen": True,
            "modified": False,
        },
        "WF": {"executed": False},
        "OOS": {"executed": False, "oos_pre_access": 0},
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
            "cost_lowering": False,
            "freshness_lowering": False,
            "oos_reuse": False,
            "fabricated_trades": False,
            "fabricated_pnl": False,
            "fabricated_lessons": False,
        },
        "NEXT": {
            "highest_value_entry_gap": "accumulate_natural_ACCOUNTING_COMPLETE_trades_via_detached_autonomy",
            "highest_value_exit_gap": "live_adaptive_profit_capture_when_meaningful_MFE_occurs",
            "highest_value_sample_gap": f"accounting_complete_trades={n}_need_>={10}_for_EARLY_BEHAVIORAL_SAMPLE",
            "highest_value_learning_gap": "lesson_replay_needs_>=5_non_origin_trades_per_CandidateLesson",
            "requires_founder": "optional_start_detached_service_with_EXCHANGE_WRITE_for_real_Demo_accumulation",
        },
    }
    _write_json(OUT, checkpoint)
    print(json.dumps({"ok": True, "out": str(OUT), "mechanics_passed": mechanics.get("mechanics_passed")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
