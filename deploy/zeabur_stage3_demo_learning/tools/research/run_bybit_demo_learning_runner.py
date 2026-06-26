#!/usr/bin/env python3
"""Stage 3 Bybit demo/testnet learning runner — mock / dry-run / demo-order."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_client import (  # noqa: E402
    BybitDemoClient,
    BybitDemoClientError,
    DemoOrderNotAllowedError,
    OrderIntent,
)
from tools.research.bybit_demo_learning_common import (  # noqa: E402
    BYBIT_DEMO_BASE_URL,
    MAX_LEVERAGE,
    MAX_MARGIN_USD,
    utc_now_iso,
)
from tools.research.stage3_learning_loop import (  # noqa: E402
    Stage3LearningLoop,
    append_jsonl,
    resolve_output_dir,
)

from tools.research.stage3_demo_order_session import run_demo_order_micro_session  # noqa: E402
from tools.research.stage3_operator_go import (  # noqa: E402
    demo_order_operator_go_present,
    operator_go_24h_metadata,
    operator_go_24h_present,
    operator_go_metadata,
    operator_go_present,
)

READINESS_REPORT = ROOT / "data/external_alpha/reports/stage3_demo_learning_runner_readiness.json"


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def run_strict_env_gate(*, in_container: bool = False) -> Dict[str, Any]:
    from tools.research.check_bybit_demo_learning_env import run_strict_check

    load_local = not in_container
    check_pkg = not in_container
    if Path("/data").is_dir() and os.environ.get("NEXUS_DATA_DIR") == "/data":
        in_container = True
        load_local = False
        check_pkg = False
    result = run_strict_check(load_local_env=load_local, check_package=check_pkg)
    if not result.get("strict_env_passed"):
        print(json.dumps(result, indent=2))
        raise SystemExit(1)
    return result


def _initial_stop_scan(loop: Stage3LearningLoop) -> None:
    if _truthy(os.environ.get("BYBIT_MAINNET_ALLOWED")):
        loop.stop.trigger("bybit_mainnet_detected")
    if _truthy(os.environ.get("REAL_MONEY")):
        loop.stop.trigger("real_money_detected")
    if os.environ.get("NEXUS_ZEABUR_SERVICE_NAME", "").strip().lower() == "btc-auto":
        loop.stop.trigger("btc_auto_production_touched")
    kill = os.environ.get("NEXUS_KILL_SWITCH", "enabled").strip().lower()
    if kill in {"0", "false", "off", "disabled"}:
        loop.stop.trigger("kill_switch_disabled")
    if not _truthy(os.environ.get("REQUIRE_STOP_LOSS")):
        loop.stop.trigger("missing_stop_loss")
    if not _truthy(os.environ.get("REQUIRE_MAX_HOLD")):
        loop.stop.trigger("missing_max_hold")


def _balance_fields(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "balance_snapshot_id": snapshot.get("snapshot_id"),
        "account_total_equity": snapshot.get("total_equity"),
        "account_available_balance": snapshot.get("available_balance"),
        "account_wallet_balance": snapshot.get("wallet_balance"),
        "balance_read_ok": snapshot.get("balance_read_ok"),
        "max_allowed_margin": snapshot.get("max_allowed_margin"),
    }


def _evaluate_balance_stops(snapshot: Dict[str, Any], loop: Stage3LearningLoop) -> bool:
    """Return True if would_order is allowed (dry-run observation-only gate)."""
    if not snapshot.get("balance_read_ok"):
        loop.stop.trigger("balance_read_failed")
        loop.state.stats["balance_read_failed_count"] += 1
        return False
    if snapshot.get("wallet_coin_missing"):
        loop.stop.trigger("wallet_coin_missing")
        return False
    avail = float(snapshot.get("available_balance") or 0)
    equity = float(snapshot.get("total_equity") or 0)
    if avail <= 0:
        loop.stop.trigger("account_available_balance_zero")
        return False
    if equity <= 0:
        loop.stop.trigger("account_total_equity_zero")
        return False
    if avail < MAX_MARGIN_USD:
        loop.stop.trigger("account_available_below_max_margin")
        return False
    return True


def _record_balance_snapshot(loop: Stage3LearningLoop, snapshot: Dict[str, Any]) -> None:
    append_jsonl(loop.path("account_snapshots.jsonl"), snapshot)


def _record_decision(loop: Stage3LearningLoop, row: Dict[str, Any], snapshot: Optional[Dict[str, Any]] = None) -> str:
    decision_id = row.get("decision_id") or str(uuid.uuid4())
    row["decision_id"] = decision_id
    row["recorded_at_utc"] = utc_now_iso()
    if snapshot:
        row.update(_balance_fields(snapshot))
    append_jsonl(loop.path("decisions.jsonl"), row)
    return decision_id


def _record_order(loop: Stage3LearningLoop, row: Dict[str, Any]) -> None:
    row["recorded_at_utc"] = utc_now_iso()
    append_jsonl(loop.path("orders.jsonl"), row)


def _record_trade(loop: Stage3LearningLoop, trade: Dict[str, Any]) -> None:
    append_jsonl(loop.path("trade_results.jsonl"), trade)


def _fetch_balance_snapshot(client: BybitDemoClient, loop: Stage3LearningLoop) -> Dict[str, Any]:
    try:
        snapshot = client.get_account_balance()
    except (BybitDemoClientError, OSError) as exc:
        loop.state.stats["balance_read_failed_count"] += 1
        loop.stop.trigger("balance_read_failed", str(exc)[:120])
        snapshot = {
            "snapshot_id": str(uuid.uuid4()),
            "ts": utc_now_iso(),
            "source": "bybit_demo",
            "account_type": "UNIFIED",
            "coin": "USDT",
            "total_equity": 0,
            "wallet_balance": 0,
            "available_balance": 0,
            "used_margin": 0,
            "unrealized_pnl": 0,
            "max_margin_usd": MAX_MARGIN_USD,
            "max_leverage": MAX_LEVERAGE,
            "max_open_positions": 1,
            "max_allowed_margin": 0,
            "balance_read_ok": False,
            "mainnet_detected": False,
            "real_money_detected": _truthy(os.environ.get("REAL_MONEY")),
            "wallet_coin_missing": False,
            "mode": client.mode,
            "error": str(exc)[:200],
        }
    _record_balance_snapshot(loop, snapshot)
    return snapshot


def _execute_simulated_trade(
    *,
    loop: Stage3LearningLoop,
    client: BybitDemoClient,
    snapshot: Dict[str, Any],
    side: str,
    regime: str,
    failure_reason: str,
    close_pnl: float,
    exit_reason: str,
    scenario: str,
    would_order: bool,
) -> Dict[str, Any]:
    ticker = client.fetch_ticker()
    price = float(ticker.get("lastPrice") or ticker.get("last_price") or 3200.0)
    conf_before = loop.state.confidence
    size_before = loop.state.position_size
    max_allowed = float(snapshot.get("max_allowed_margin") or 0)
    margin_usd = min(size_before, MAX_MARGIN_USD, max_allowed if max_allowed > 0 else MAX_MARGIN_USD)
    stop = price * (0.98 if side.upper() == "BUY" else 1.02)
    decision_id = _record_decision(
        loop,
        {
            "scenario": scenario,
            "symbol": "ETHUSDT",
            "side": side,
            "regime": regime,
            "failure_reason": failure_reason,
            "confidence": conf_before,
            "position_size": size_before,
            "action": "would_order" if would_order else "observe_only",
            "would_order": would_order,
            "last_price": price,
        },
        snapshot,
    )
    if not would_order:
        return {"decision_id": decision_id, "would_order": False}

    intent = OrderIntent(
        symbol="ETHUSDT",
        side=side,
        qty=round(margin_usd / price, 6),
        price=price,
        stop_loss=stop,
        max_hold_seconds=900,
        leverage=min(MAX_LEVERAGE, 3),
        margin_usd=margin_usd,
    )
    order = client.simulate_order(intent, order_id_prefix=client.mode)
    signal_id = f"sig-{scenario}-{uuid.uuid4().hex[:8]}"
    _record_order(loop, {**order, "decision_id": decision_id, "signal_id": signal_id, "would_order": True})
    exit_price = price * (1.0 + (close_pnl / max(margin_usd, 1.0)))
    trade = loop.build_trade_record(
        decision_id=decision_id,
        signal_id=signal_id,
        order_id=order["order_id"],
        symbol="ETHUSDT",
        side=side,
        entry_price=price,
        exit_price=round(exit_price, 4),
        close_pnl=close_pnl,
        exit_reason=exit_reason,
        confidence_before=conf_before,
        confidence_after=conf_before,
        position_size_before=size_before,
        position_size_after=size_before,
        reflection_created=False,
        patch_created=False,
        patch_applied_to_next_decision=False,
        repeated_mistake_detected=False,
        repeated_mistake_blocked=False,
    )
    client.close_position()
    if close_pnl < 0:
        trade = loop.record_loss_reflection_patch(
            decision_id=decision_id,
            trade=trade,
            regime=regime,
            failure_reason=failure_reason,
        )
    _record_trade(loop, trade)
    return trade


def _try_same_setup_reentry(
    *,
    loop: Stage3LearningLoop,
    snapshot: Dict[str, Any],
    side: str,
    regime: str,
    failure_reason: str,
    would_order: bool,
) -> Dict[str, Any]:
    eval_result = loop.evaluate_same_setup(
        symbol="ETHUSDT",
        side=side,
        regime=regime,
        failure_reason=failure_reason,
        decision_source="controlled_demo_order",
    )
    decision_id = _record_decision(
        loop,
        {
            "scenario": "same_setup_reentry",
            "symbol": "ETHUSDT",
            "side": side,
            "regime": regime,
            "failure_reason": failure_reason,
            "action": "skip" if eval_result["skip_trade"] or not would_order else "enter",
            "would_order": would_order and not eval_result["skip_trade"],
            **eval_result,
        },
        snapshot,
    )
    if eval_result["skip_trade"] or not would_order:
        blocked_trade = loop.build_trade_record(
            decision_id=decision_id,
            signal_id=f"sig-blocked-{uuid.uuid4().hex[:8]}",
            order_id="blocked-no-order",
            symbol="ETHUSDT",
            side=side,
            entry_price=0,
            exit_price=0,
            close_pnl=0,
            exit_reason="repeated_mistake_blocked" if eval_result["skip_trade"] else "balance_or_gate_blocked",
            confidence_before=eval_result["confidence"],
            confidence_after=eval_result["confidence"],
            position_size_before=eval_result["position_size"],
            position_size_after=eval_result["position_size"],
            reflection_created=False,
            patch_created=False,
            patch_applied_to_next_decision=eval_result["patch_applied_to_next_decision"],
            repeated_mistake_detected=eval_result["repeated_mistake_detected"],
            repeated_mistake_blocked=bool(eval_result["skip_trade"]),
        )
        for fld in (
            "setup_key",
            "patch_id",
            "dedup_key",
            "blocked_event_counted",
            "blocked_tick_counted",
            "last_blocked_at_utc",
            "cooldown_until_utc",
        ):
            if fld in eval_result:
                blocked_trade[fld] = eval_result[fld]
        _record_trade(loop, blocked_trade)
        return blocked_trade
    return eval_result


def run_scenario_step(
    step: int,
    loop: Stage3LearningLoop,
    client: BybitDemoClient,
    snapshot: Dict[str, Any],
    would_order: bool,
) -> Optional[str]:
    if step == 0:
        _execute_simulated_trade(
            loop=loop,
            client=client,
            snapshot=snapshot,
            side="BUY",
            regime="range_low",
            failure_reason="stop_loss_hit",
            close_pnl=-2.5,
            exit_reason="stop_loss",
            scenario="initial_loss",
            would_order=would_order,
        )
        return "initial_loss"
    if step == 1:
        _try_same_setup_reentry(
            loop=loop,
            snapshot=snapshot,
            side="BUY",
            regime="range_low",
            failure_reason="stop_loss_hit",
            would_order=would_order,
        )
        return "same_setup_blocked"
    if step == 2:
        _execute_simulated_trade(
            loop=loop,
            client=client,
            snapshot=snapshot,
            side="SELL",
            regime="trend_down",
            failure_reason="signal_exit",
            close_pnl=1.2,
            exit_reason="signal",
            scenario="winning_trade",
            would_order=would_order,
        )
        return "winning_trade"
    return None


def _prepare_output_dir(output_dir: Path, *, fresh: bool) -> None:
    if fresh and output_dir.is_dir():
        for name in (
            "decisions.jsonl",
            "orders.jsonl",
            "trade_results.jsonl",
            "reflection_records.jsonl",
            "applied_learning_patches.jsonl",
            "account_snapshots.jsonl",
            "runner_audit.json",
            "stop_conditions.json",
            "demo_order_session_report.json",
        ):
            p = output_dir / name
            if p.is_file():
                p.unlink()


def _is_24h_run(max_orders: int) -> bool:
    return operator_go_24h_present() and max_orders > 1


def run_loop(
    *,
    mode: str,
    duration_minutes: float,
    poll_interval_seconds: float,
    fresh_output: bool = True,
    max_orders: int = 1,
) -> Dict[str, Any]:
    is_24h = _is_24h_run(max_orders)
    if mode == "demo-order":
        if is_24h:
            if not operator_go_24h_present():
                raise DemoOrderNotAllowedError(
                    "OPERATOR_GO_STAGE3_24H_RUNNER not set; 24h demo-order refused"
                )
            from tools.research.preflight_stage3_24h_runner import run_preflight as run_24h_preflight

            in_container = Path("/data").is_dir() and os.environ.get("NEXUS_DATA_DIR") == "/data"
            preflight = run_24h_preflight(load_local_env=not in_container)
            if not preflight.get("preflight_passed"):
                print(json.dumps({"preflight_errors": preflight.get("preflight_errors")}, indent=2))
                raise SystemExit(1)
        else:
            if not operator_go_present():
                raise DemoOrderNotAllowedError(
                    "OPERATOR_GO_STAGE3_C1_DEMO_ORDER not set; demo-order refused"
                )
            from tools.research.preflight_stage3_demo_order import run_preflight

            in_container = Path("/data").is_dir() and os.environ.get("NEXUS_DATA_DIR") == "/data"
            preflight = run_preflight(load_local_env=not in_container)
            if not preflight.get("preflight_passed"):
                print(json.dumps({"preflight_errors": preflight.get("preflight_errors")}, indent=2))
                raise SystemExit(1)

    strict = run_strict_env_gate()
    output_dir = resolve_output_dir()
    _prepare_output_dir(output_dir, fresh=not is_24h and fresh_output)
    loop = Stage3LearningLoop(output_dir)
    _initial_stop_scan(loop)
    if loop.stop.should_stop:
        loop.write_stop_conditions()
        raise SystemExit(1)

    allow_demo = mode == "demo-order" and demo_order_operator_go_present()
    client = BybitDemoClient(mode, allow_demo_order=allow_demo)
    started = time.time()
    end = started + duration_minutes * 60.0
    step = 0
    actions: List[str] = []
    latest_snapshot: Dict[str, Any] = {}
    tick = 0
    session_report: Dict[str, Any] = {}
    session_reports: List[Dict[str, Any]] = []
    orders_sent = 0
    observe_ticks_after_orders_full = 0
    orders_full_at_utc: str | None = None
    runner_phase = "RUNNING"
    run_completed_at_utc: str | None = None

    if mode == "demo-order" and is_24h:
        balance_before: float | None = None
        while time.time() < end and not loop.stop.should_stop:
            snapshot = _fetch_balance_snapshot(client, loop)
            latest_snapshot = snapshot
            tick += 1
            if balance_before is None:
                balance_before = float(snapshot.get("available_balance") or 0)
            if not _evaluate_balance_stops(snapshot, loop):
                break
            open_positions = client.count_open_positions()
            if open_positions > 0:
                ticker = client.fetch_ticker()
                _record_decision(
                    loop,
                    {
                        "scenario": "24h_open_position_observe",
                        "symbol": "ETHUSDT",
                        "action": "observe_open_position",
                        "tick": tick,
                        "runner_phase": runner_phase,
                        "last_price": float(ticker.get("lastPrice") or 0),
                    },
                    snapshot,
                )
            elif orders_sent < max_orders:
                session_report = run_demo_order_micro_session(
                    loop=loop,
                    client=client,
                    snapshot=snapshot,
                    max_orders=1,
                    poll_interval_seconds=poll_interval_seconds,
                    duration_minutes=min(10.0, max(1.0, (end - time.time()) / 60.0)),
                )
                session_reports.append(session_report)
                if session_report.get("demo_order_sent"):
                    orders_sent += 1
                    actions.append(f"demo_order_micro_session_{orders_sent}")
                    if orders_sent >= max_orders and orders_full_at_utc is None:
                        orders_full_at_utc = utc_now_iso()
                        runner_phase = "OBSERVING_AFTER_MAX_ORDERS"
                elif session_report.get("blocked_repeated_mistake"):
                    actions.append("blocked_repeated_mistake")
                if loop.stop.should_stop:
                    break
            else:
                runner_phase = "OBSERVING_AFTER_MAX_ORDERS"
                observe_ticks_after_orders_full += 1
                ticker = client.fetch_ticker()
                _record_decision(
                    loop,
                    {
                        "scenario": "24h_market_scan",
                        "symbol": "ETHUSDT",
                        "action": "observe_only",
                        "tick": tick,
                        "runner_phase": runner_phase,
                        "observe_ticks_after_orders_full": observe_ticks_after_orders_full,
                        "last_price": float(ticker.get("lastPrice") or 0),
                    },
                    snapshot,
                )
            if time.time() >= end:
                break
            time.sleep(poll_interval_seconds)
        run_completed_at_utc = utc_now_iso()
        try:
            from tools.research.read_stage3_24h_status import write_status

            write_status(
                orders_sent=orders_sent,
                run_started=True,
                run_completed=True,
                duration_minutes_target=duration_minutes,
                max_orders_per_day=max_orders,
                observe_ticks_after_orders_full=observe_ticks_after_orders_full,
                orders_full_at_utc=orders_full_at_utc,
                run_completed_at_utc=run_completed_at_utc,
                runner_phase=runner_phase,
            )
        except Exception:
            pass
    elif mode == "demo-order":
        snapshot = _fetch_balance_snapshot(client, loop)
        latest_snapshot = snapshot
        if not _evaluate_balance_stops(snapshot, loop):
            loop.write_stop_conditions()
            raise SystemExit(1)
        if client.count_open_positions() > 0:
            loop.stop.trigger("open_positions_exceeds_cap")
            loop.write_stop_conditions()
            raise SystemExit(1)
        session_report = run_demo_order_micro_session(
            loop=loop,
            client=client,
            snapshot=snapshot,
            max_orders=max_orders,
            poll_interval_seconds=poll_interval_seconds,
            duration_minutes=duration_minutes,
        )
        actions.append("demo_order_micro_session")
        orders_sent = 1
        while time.time() < end:
            latest_snapshot = _fetch_balance_snapshot(client, loop)
            tick += 1
            time.sleep(poll_interval_seconds)
    else:
        while time.time() < end:
            snapshot = _fetch_balance_snapshot(client, loop)
            latest_snapshot = snapshot
            would_order = _evaluate_balance_stops(snapshot, loop)
            if mode in {"mock", "dry-run"} and tick < 3:
                action = run_scenario_step(step, loop, client, snapshot, would_order)
                if action:
                    actions.append(action)
                step += 1
            elif mode == "dry-run":
                ticker = client.fetch_ticker()
                _record_decision(
                    loop,
                    {
                        "scenario": "dry_run_observation",
                        "symbol": "ETHUSDT",
                        "action": "observe_only" if not would_order else "would_order_candidate",
                        "would_order": would_order,
                        "last_price": float(ticker.get("lastPrice") or 0),
                        "tick": tick,
                    },
                    snapshot,
                )
            tick += 1
            if time.time() >= end:
                break
            time.sleep(poll_interval_seconds)

    elapsed_minutes = round((time.time() - started) / 60.0, 4)
    audit = {
        "record_type": "stage3_demo_learning_runner_audit",
        "generated_at_utc": utc_now_iso(),
        "phase": "D" if is_24h else ("C+2" if mode == "demo-order" else ("B" if mode == "dry-run" else "A")),
        "mode": mode,
        "duration_minutes": duration_minutes,
        "elapsed_minutes": elapsed_minutes,
        "poll_interval_seconds": poll_interval_seconds,
        "tick_count": tick,
        "max_orders": max_orders,
        "orders_sent": orders_sent,
        "run_completed": True,
        "strict_env_passed": strict.get("strict_env_passed"),
        "operator_go_present": demo_order_operator_go_present(),
        "operator_go_24h_present": operator_go_24h_present(),
        "operator_go_metadata": operator_go_metadata(),
        "operator_go_24h_metadata": operator_go_24h_metadata(),
        "is_24h_run": is_24h,
        "output_dir": str(output_dir),
        "actions": actions,
        "session_report": session_report,
        "session_reports": session_reports,
        "stats": loop.state.stats,
        "final_confidence": loop.state.confidence,
        "final_position_size": loop.state.position_size,
        "stop_triggered": loop.stop.triggered,
        "bybit_base_url": BYBIT_DEMO_BASE_URL,
        "demo_order_sent": orders_sent > 0,
        "runner_started": True,
        "zeabur_runner_started_24h": is_24h,
        "balance_snapshot_written": True,
        "latest_balance": {
            "balance_read_ok": latest_snapshot.get("balance_read_ok"),
            "coin": latest_snapshot.get("coin"),
            "total_equity": latest_snapshot.get("total_equity"),
            "wallet_balance": latest_snapshot.get("wallet_balance"),
            "available_balance": latest_snapshot.get("available_balance"),
            "used_margin": latest_snapshot.get("used_margin"),
            "unrealized_pnl": latest_snapshot.get("unrealized_pnl"),
            "wallet_coin_missing": latest_snapshot.get("wallet_coin_missing"),
        },
        "balance_read_failed": loop.state.stats.get("balance_read_failed_count", 0) > 0,
    }
    if is_24h:
        audit.update(
            {
                "observe_ticks_after_orders_full": observe_ticks_after_orders_full,
                "orders_full_at_utc": orders_full_at_utc,
                "run_completed_at_utc": run_completed_at_utc,
                "runner_phase": runner_phase,
            }
        )
    loop.write_audit(audit)
    loop.write_stop_conditions()
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3 Bybit demo learning runner")
    parser.add_argument("--mode", choices=["mock", "dry-run", "demo-order"], required=True)
    parser.add_argument("--duration-minutes", type=float, default=3.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=15.0)
    parser.add_argument("--max-orders", type=int, default=1)
    parser.add_argument("--no-fresh-output", action="store_true")
    args = parser.parse_args()

    if args.mode == "demo-order":
        if operator_go_24h_present() and args.max_orders > 1:
            pass
        elif not operator_go_present():
            print(
                json.dumps(
                    {
                        "error": "demo-order refused",
                        "reason": "OPERATOR_GO_STAGE3_C1_DEMO_ORDER or OPERATOR_GO_STAGE3_24H_RUNNER not set",
                    },
                    indent=2,
                )
            )
            return 1
        elif args.max_orders != 1:
            print(json.dumps({"error": "C+1 micro session allows max_orders=1 only without 24h GO"}, indent=2))
            return 1

    try:
        audit = run_loop(
            mode=args.mode,
            duration_minutes=args.duration_minutes,
            poll_interval_seconds=args.poll_interval_seconds,
            fresh_output=not args.no_fresh_output,
            max_orders=args.max_orders,
        )
    except DemoOrderNotAllowedError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    print(
        json.dumps(
            {
                "mode": args.mode,
                "output_dir": audit["output_dir"],
                "actions": audit["actions"],
                "tick_count": audit["tick_count"],
                "demo_order_sent": audit.get("demo_order_sent"),
                "session_report": audit.get("session_report"),
                "latest_balance": audit.get("latest_balance"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
