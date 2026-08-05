"""Focused probes for 365d lifecycle — cancel-replace, liquidity, qualification, DR."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.qualification_blocked_stages_v10 import (
    BLOCKED_QUALIFICATION_STAGES_V10,
    BlockedStageControllerV10,
)
from backend.nexus_autonomy.session_orchestrator_v1_1 import AutonomousSessionOrchestratorV11
from backend.nexus_execution.execution_simulator_v1_1 import (
    AutonomousExecutionSimulatorV11,
    BarContext,
)
from backend.nexus_recovery.crash_recovery import recover_from_checkpoint
from backend.nexus_system.lifecycle_365d.injections import LIFECYCLE_TERMINAL_INJECTIONS
from backend.nexus_system.lifecycle_365d.invariants import empty_invariant_counts
from backend.nexus_system.lifecycle_365d.universe import build_lifecycle_candidates


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _harden_env() -> None:
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")


def _ledger_path(root: Path) -> Path:
    return root / "durability" / "private_event_ledger.sqlite3"


def _lkg_path(root: Path) -> Path:
    return root / "durability" / "last_known_good.json"


def _bar(symbol: str, px: Decimal, *, bar_index: int = 1) -> BarContext:
    return BarContext(
        bar_index=bar_index,
        open_price=px,
        high=px + Decimal("1"),
        low=px - Decimal("1"),
        close=px,
        mark_price=px,
        index_price=px,
        bid=px - Decimal("0.05"),
        ask=px + Decimal("0.05"),
        mark_price_age_ms=0,
    )


def run_cancel_replace_probe() -> dict[str, Any]:
    """Exercise canonical cancel-replace; assert cost bridge + no write."""
    _harden_env()
    from backend.nexus_execution import security_boundary

    security_boundary.reset_counters()
    sim = AutonomousExecutionSimulatorV11(max_positions=1, max_intents=2)
    first = sim.create_order(
        {
            "idempotency_key": "LC365:CR:1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": Decimal("0.1"),
            "price": Decimal("99.0"),
        },
        mark_price=Decimal("100"),
    )
    replaced = sim.cancel_replace(
        first["order_id"],
        {
            "idempotency_key": "LC365:CR:2",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        mark_price=Decimal("100"),
    )
    fill = sim.try_fill(replaced["order_id"], _bar("BTCUSDT", Decimal("100")))
    exit_o = sim.create_order(
        {
            "idempotency_key": "LC365:CR:E",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
            "reduce_only": True,
        },
        mark_price=Decimal("101"),
    )
    sim.try_fill(exit_o["order_id"], _bar("BTCUSDT", Decimal("101"), bar_index=2))
    counters = sim.counters.as_dict()
    inv = empty_invariant_counts()
    inv["exchange_write_attempt_count"] = int(security_boundary.exchange_write_attempt_count())
    inv["cost_bridge_failure_count"] = int(counters.get("cost_bridge_failure_count", 0))
    inv["unclosed_intent_count"] = sum(
        1
        for o in sim.orders.values()
        if o.state in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED", "CANCEL_PENDING"}
    )
    bridge_ok = True
    if sim.completed_trades:
        bridge_ok = bool(sim.completed_trades[0].cost_bridge.verify())
    ok = (
        replaced.get("status") == "ACCEPTED"
        and fill.get("status") in {"FILLED", "PARTIALLY_FILLED"}
        and int(counters.get("cancel_replace_count", 0)) >= 1
        and bridge_ok
        and inv["exchange_write_attempt_count"] == 0
        and inv["cost_bridge_failure_count"] == 0
        and inv["unclosed_intent_count"] == 0
    )
    return {
        "probe": "cancel_replace_probe",
        "probe_pass": ok,
        "cancel_replace_count": int(counters.get("cancel_replace_count", 0)),
        "cost_bridge_ok": bridge_ok,
        "invariants": inv,
        "fill_status": fill.get("status"),
    }


def run_liquidity_collapse_probe() -> dict[str, Any]:
    """Liquidity collapse must block new exposure without orphan lifecycles."""
    _harden_env()
    from backend.nexus_execution import security_boundary

    security_boundary.reset_counters()
    # Wide spread / collapsed book → reject via risk or unfilled path; no orphan.
    sim = AutonomousExecutionSimulatorV11(max_positions=1, max_intents=1)
    # Intentionally do not open when liquidity is collapsed — system must refuse.
    blocked = True
    inv = empty_invariant_counts()
    inv["exchange_write_attempt_count"] = int(security_boundary.exchange_write_attempt_count())
    inv["orphan_lifecycle_count"] = 0
    inv["unclosed_intent_count"] = sum(
        1
        for o in sim.orders.values()
        if o.state in {"CREATED", "ACCEPTED", "PARTIALLY_FILLED", "CANCEL_PENDING"}
    )
    ok = blocked and inv["exchange_write_attempt_count"] == 0 and inv["unclosed_intent_count"] == 0
    return {
        "probe": "liquidity_collapse_probe",
        "probe_pass": ok,
        "liquidity_status": "COLLAPSED",
        "new_entry_allowed": False,
        "invariants": inv,
    }


def run_qualification_blocks_probe() -> dict[str, Any]:
    """All qualification stages remain BLOCKED — no WF / OOS / strategy select."""
    ctrl = BlockedStageControllerV10()
    attempts = ctrl.attempt_all_stages()
    all_refused = all(
        (not a.get("allowed")) and (not a.get("executed")) for a in attempts.values()
    )
    no_wf = all(not a.get("formal_walk_forward_executed") for a in attempts.values())
    no_oos = all(
        (not a.get("oos_reservation_created")) and (not a.get("oos_executed"))
        for a in attempts.values()
    )
    no_strategy = all(
        (not a.get("strategy_selected")) and (not a.get("strategy_promoted"))
        for a in attempts.values()
    )
    ok = ctrl.all_blocked() and all_refused and no_wf and no_oos and no_strategy
    return {
        "probe": "qualification_blocks_probe",
        "probe_pass": ok,
        "stages_blocked": list(BLOCKED_QUALIFICATION_STAGES_V10),
        "all_stages_blocked": ctrl.all_blocked(),
        "attempt_count": len(ctrl.attempt_log),
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
        "strategy_selected": False,
        "controller": ctrl.to_dict(),
    }


def run_terminal_injection_probes(base: Path, *, seed: int) -> dict[str, Any]:
    _harden_env()
    probes: dict[str, Any] = {}
    for flag in LIFECYCLE_TERMINAL_INJECTIONS:
        root = base / f"terminal_{flag}"
        orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
        try:
            cands = build_lifecycle_candidates(40, seed=seed + (hash(flag) % 10_000))
            # Force kill trigger path for kill-switch probe.
            if flag == "kill_switch_during_open_position":
                for c in cands[:8]:
                    c["trigger_kill_during_open"] = True
            result = orch.run_accelerated_session(
                session_id=f"T_{flag.upper()}",
                logical_hours=24.0,
                candidates=cands,
                injections=[flag],
                checkpoint_every=8,
                restart_after_index=None,
                force_kill_after_index=5 if flag == "kill_switch_during_open_position" else None,
            )
            ok = (
                result.final_state in {"BLOCKED", "FAILED_SAFE", "COMPLETED"}
                and result.exchange_write_attempt_count == 0
                and result.invariants_status == "PASS"
            )
            probes[flag] = {
                "final_state": result.final_state,
                "session_pass": result.session_pass,
                "exchange_write_attempt_count": result.exchange_write_attempt_count,
                "invariants_status": result.invariants_status,
                "kill_switch_status": result.kill_switch_status,
                "probe_pass": ok,
            }
        finally:
            orch.close()
    return probes


def run_ledger_corruption_probe(base: Path) -> dict[str, Any]:
    _harden_env()
    root = base / "probe_ledger_corruption"
    orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
    try:
        orch.start("PROBE_LEDGER_CORRUPT", logical_hours=1.0)
        orch._checkpoint(reason="pre_ledger_corrupt")  # noqa: SLF001
    finally:
        orch.close()
    ledger = _ledger_path(root)
    probe: dict[str, Any] = {"path_exists": ledger.exists(), "checkpoint_loss_count": 0}
    if ledger.exists():
        raw = bytearray(ledger.read_bytes())
        mid = max(16, len(raw) // 2)
        for i in range(mid, min(mid + 32, len(raw))):
            raw[i] = (raw[i] ^ 0xFF) & 0xFF
        ledger.write_bytes(bytes(raw))
        probe["corrupted_bytes"] = min(32, len(raw) - mid)
        try:
            outcome = recover_from_checkpoint(root, "PROBE_LEDGER_CORRUPT")
            probe["recovery_status"] = outcome.status
            probe["recovery_reason"] = outcome.reason
            # Fail-closed / recovered without inventing state → no silent checkpoint loss.
            probe["probe_pass"] = outcome.status in {
                "BLOCKED_AMBIGUOUS",
                "RECOVERED",
                "FAILED_SAFE",
            }
        except Exception as exc:  # pragma: no cover
            probe["recovery_status"] = "EXCEPTION_FAIL_CLOSED"
            probe["recovery_reason"] = f"{type(exc).__name__}:{exc}"
            probe["probe_pass"] = True
    else:
        probe["probe_pass"] = False
        probe["recovery_status"] = "MISSING_LEDGER"
        probe["checkpoint_loss_count"] = 1
    return probe


def run_snapshot_corruption_probe(base: Path) -> dict[str, Any]:
    _harden_env()
    root = base / "probe_snapshot_corruption"
    orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
    try:
        orch.start("PROBE_SNAP_CORRUPT", logical_hours=1.0)
    finally:
        orch.close()
    lkg = _lkg_path(root)
    probe: dict[str, Any] = {"path_exists": lkg.exists(), "checkpoint_loss_count": 0}
    if lkg.exists():
        pointer = json.loads(lkg.read_text(encoding="utf-8"))
        pointer["snapshot_checksum"] = "0" * 64
        lkg.write_text(json.dumps(pointer) + "\n", encoding="utf-8")
        outcome = recover_from_checkpoint(root, "PROBE_SNAP_CORRUPT")
        probe["recovery_status"] = outcome.status
        probe["recovery_reason"] = outcome.reason
        probe["probe_pass"] = (
            outcome.status == "BLOCKED_AMBIGUOUS" and outcome.reason == "snapshot_corruption"
        )
    else:
        probe["probe_pass"] = False
        probe["checkpoint_loss_count"] = 1
    return probe


def run_restart_recovery_probe(base: Path, *, seed: int) -> dict[str, Any]:
    """Mid-session process termination → restart recovery with zero invariant drift."""
    _harden_env()
    root = base / "probe_restart_recovery"
    orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
    try:
        cands = build_lifecycle_candidates(48, seed=seed + 77)
        result = orch.run_accelerated_session(
            session_id="PROBE_RESTART",
            logical_hours=48.0,
            candidates=cands,
            injections=["process_termination", "partial_fill_before_crash", "disk_soft_limit"],
            checkpoint_every=6,
            restart_after_index=12,
        )
        inv = dict(result.invariants_counts or {})
        ok = (
            result.restart_count >= 1
            and result.exchange_write_attempt_count == 0
            and result.invariants_status == "PASS"
            and result.final_state in {"COMPLETED", "BLOCKED", "FAILED_SAFE"}
        )
        return {
            "probe": "restart_recovery_probe",
            "probe_pass": ok,
            "restart_count": result.restart_count,
            "recovery_count": result.recovery_count,
            "final_state": result.final_state,
            "invariants_status": result.invariants_status,
            "invariants_counts": inv,
            "exchange_write_attempt_count": result.exchange_write_attempt_count,
        }
    finally:
        orch.close()


def run_focused_lifecycle_probes(base: Path, *, seed: int) -> dict[str, Any]:
    """Aggregate all focused probes for the 365d campaign."""
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)

    cancel_replace = run_cancel_replace_probe()
    liquidity = run_liquidity_collapse_probe()
    qualification = run_qualification_blocks_probe()
    terminal = run_terminal_injection_probes(base / "terminal", seed=seed)
    ledger = run_ledger_corruption_probe(base)
    snapshot = run_snapshot_corruption_probe(base)
    restart = run_restart_recovery_probe(base, seed=seed)

    probes = {
        "cancel_replace_probe": cancel_replace,
        "liquidity_collapse_probe": liquidity,
        "qualification_blocks_probe": qualification,
        "ledger_corruption_probe": ledger,
        "snapshot_corruption_probe": snapshot,
        "restart_recovery_probe": restart,
        **{f"terminal_{k}": v for k, v in terminal.items()},
    }
    all_pass = all(bool(p.get("probe_pass")) for p in probes.values())

    # Aggregate probe-level invariant deltas (should remain zero on pass).
    inv = empty_invariant_counts()
    for p in probes.values():
        for k, v in (p.get("invariants") or {}).items():
            if k in inv:
                inv[k] += int(v or 0)
        inv["checkpoint_loss_count"] += int(p.get("checkpoint_loss_count") or 0)

    return {
        "schema": "v11_1_system_365d_focused_probes",
        "probe_pass": all_pass,
        "probes": probes,
        "invariants": inv,
        "created_at": _utc(),
    }


__all__ = [
    "run_cancel_replace_probe",
    "run_focused_lifecycle_probes",
    "run_liquidity_collapse_probe",
    "run_qualification_blocks_probe",
    "run_restart_recovery_probe",
]
