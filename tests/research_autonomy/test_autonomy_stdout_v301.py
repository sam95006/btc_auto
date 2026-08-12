"""V30.1 stdout observability tests — free-log autonomy heartbeat."""

from __future__ import annotations

from pathlib import Path

from backend.nexus_research_ai_autonomy.autonomy_stdout_v301 import (
    log_boot,
    log_cycle,
    log_error,
    log_manage,
    log_order,
    log_trade_complete,
    observe_completed_tick,
)
from backend.nexus_research_ai_autonomy.research_autonomy_scheduler import (
    ResearchAutonomyScheduler,
    SchedulerConfig,
    SchedulerHealth,
)
from backend.nexus_research_ai_autonomy.research_autonomy_service import ResearchAutonomyService


def test_boot_log_redacts_secrets(capsys) -> None:
    log_boot(
        runtime="ZEABUR",
        boot_ready=True,
        exchange="api-demo.bybit.com",
        worker_id="worker-abc123",
    )
    out = capsys.readouterr().out
    assert "[NEXUS-AUTONOMY] BOOT" in out
    assert "runtime=ZEABUR" in out
    assert "boot_ready=True" in out
    assert "exchange=api-demo.bybit.com" in out
    assert "worker=worker-abc123" in out
    assert "BYBIT_DEMO_API_KEY" not in out


def test_cycle_manage_error_order_trade_logs(capsys) -> None:
    health = SchedulerHealth(
        service_status="MANAGING_POSITION",
        last_cycle_started_at="2026-08-12T06:00:00Z",
        last_cycle_completed_at="2026-08-12T06:00:05Z",
        next_cycle_due_at="2026-08-12T06:02:05Z",
        open_position=True,
        market_scan_complete=True,
        candidate_count=7,
    )
    last = {
        "service_status": "MANAGING_POSITION",
        "duration_sec": 5.0,
        "reconcile": {"symbol": "BTCUSDT", "side": "LONG", "open": True},
        "result": {
            "closed": True,
            "action": "EXIT_STOP",
            "tick_detail": [
                {
                    "adaptive_action": "HOLD",
                    "open_position_telemetry": {"mfe_usdt": 1.2, "mae_usdt": -0.4},
                },
                {
                    "closed": True,
                    "lifecycle": {
                        "symbol": "BTCUSDT",
                        "side": "LONG",
                        "exit_reason": "STOP_LOSS",
                        "exact_pnl_accounting": {"calculated_net_pnl": -0.55},
                        "wallet_reconciliation": {"WALLET_RECONCILIATION_PASS": True},
                    },
                },
            ],
        },
    }
    observe_completed_tick(cycle_n=3, last=last, health=health)
    out = capsys.readouterr().out
    assert "[NEXUS-AUTONOMY] CYCLE" in out
    assert "n=3" in out
    assert "status=MANAGING_POSITION" in out
    assert "[NEXUS-AUTONOMY] MANAGE" in out
    assert "symbol=BTCUSDT" in out
    assert "MFE=1.2" in out
    assert "[NEXUS-AUTONOMY] TRADE_COMPLETE" in out
    assert "exit_reason=STOP_LOSS" in out
    assert "api_secret" not in out.lower()

    capsys.readouterr()
    log_error(cycle=4, error_class="AI_QUOTA_EXHAUSTED", service_status="DEGRADED", next_retry="t+120")
    err = capsys.readouterr().out
    assert "[NEXUS-AUTONOMY] ERROR" in err
    assert "error_class=AI_QUOTA_EXHAUSTED" in err

    capsys.readouterr()
    log_order(symbol="ETHUSDT", side="SHORT", demo=True, notional=350.0, result="ACCEPTED")
    order = capsys.readouterr().out
    assert "[NEXUS-AUTONOMY] ORDER" in order
    assert "demo=True" in order
    assert "notional=350.0" in order


def test_service_emits_boot_and_cycle_stdout(capsys, tmp_path: Path) -> None:
    def cycle(_ctx):
        return {
            "ok": True,
            "WAIT": True,
            "executed": False,
            "market_scan_complete": True,
            "cycle_ai_ready": True,
            "candidate_count": 4,
            "reason": "NO_VALID_MARKET_OPPORTUNITY",
        }

    svc = ResearchAutonomyService(
        config=SchedulerConfig(campaign_root=tmp_path, cycle_sleep_sec=0.01),
        bindings={
            "cycle_fn": cycle,
            "manage_fn": lambda _c: {"ok": True, "closed": False},
            "reconcile_fn": lambda: {"ok": True, "open": False},
        },
        max_cycles=2,
        max_seconds=5.0,
        skip_boot=True,
        skip_lock=True,
    )
    out = svc.run_forever()
    captured = capsys.readouterr().out
    assert out["cycles_run"] == 2
    assert "[NEXUS-AUTONOMY] BOOT" in captured
    assert captured.count("[NEXUS-AUTONOMY] CYCLE") == 2
    assert "status=WAITING_MARKET" in captured
    assert (tmp_path / "autonomy" / "service_heartbeat.json").is_file()


def test_manage_tick_stdout_via_scheduler(capsys, tmp_path: Path) -> None:
    def manage(_ctx):
        return {
            "ok": True,
            "closed": False,
            "action": "HOLD",
            "tick_detail": [
                {
                    "adaptive_action": "HOLD",
                    "open_position_telemetry": {
                        "symbol": "SOLUSDT",
                        "side": "SHORT",
                        "mfe_usdt": 0.8,
                        "mae_usdt": -0.2,
                    },
                }
            ],
        }

    sched = ResearchAutonomyScheduler(
        config=SchedulerConfig(campaign_root=tmp_path),
        cycle_fn=lambda _c: {"ok": True, "WAIT": True, "executed": False},
        manage_fn=manage,
        reconcile_fn=lambda: {
            "ok": True,
            "open": True,
            "symbol": "SOLUSDT",
            "side": "SHORT",
        },
    )
    sched.start()
    tick = sched.run_one_autonomy_tick()
    observe_completed_tick(cycle_n=1, last=tick, health=sched.health)
    out = capsys.readouterr().out
    assert "[NEXUS-AUTONOMY] CYCLE" in out
    assert "[NEXUS-AUTONOMY] MANAGE" in out
    assert "symbol=SOLUSDT" in out
