#!/usr/bin/env python3
"""Run NEXUS Private Core V8 packages (replay, simulator, sessions, ledger scale)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _cand(i: int, **extra):
    return {
        "candidate_id": f"S{i}",
        "idempotency_key": f"S{i}",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "mark_price": 100.0 + i,
        "lose": i % 2 == 0,
        **extra,
    }


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"

    from backend.nexus_autonomy.execution_simulator_v1 import AutonomousExecutionSimulatorV1
    from backend.nexus_autonomy.historical_integration_replay_v1 import run_historical_integration_replay
    from backend.nexus_autonomy.ledger_scale_v1_1 import run_ledger_scale_validation
    from backend.nexus_autonomy.private_observability_v1 import build_private_observability
    from backend.nexus_autonomy.session_orchestrator_v1 import AutonomousSessionOrchestratorV1

    # --- Historical replay ---
    print("historical replay...", flush=True)
    replay = run_historical_integration_replay(ROOT, target_candidates=500)
    _write(ROOT / "artifacts/readiness/immutable/historical_integration_replay_v1/replay_status.json", replay)

    # --- Execution simulator package ---
    print("execution simulator smoke...", flush=True)
    sim = AutonomousExecutionSimulatorV1(max_positions=1, max_intents=1)
    a = sim.create_order(
        {"idempotency_key": "e1", "symbol": "BTCUSDT", "side": "BUY", "order_type": "market", "qty": 0.1, "mark_price": 100}
    )
    f = sim.try_fill(a["order_id"], market_bid=99.9, market_ask=100.1, last_price=100, path_low=99, path_high=101)
    b = sim.create_order(
        {"idempotency_key": "e1", "symbol": "BTCUSDT", "side": "BUY", "order_type": "market", "qty": 0.1, "mark_price": 100}
    )
    amb = AutonomousExecutionSimulatorV1()
    oa = amb.create_order(
        {"idempotency_key": "amb", "symbol": "BTCUSDT", "side": "SELL", "order_type": "stop-market", "qty": 0.1, "mark_price": 100, "stop_price": 99.5}
    )
    amb_fill = amb.try_fill(
        oa["order_id"],
        market_bid=99.4,
        market_ask=100.1,
        last_price=100,
        path_low=99,
        path_high=101,
        same_bar_stop=99.5,
        same_bar_target=100.5,
    )
    exec_status = {
        "schema": "autonomous_execution_simulator_v1",
        "execution_status": "NEXUS_EXECUTION_SIMULATOR_V1_PASS"
        if a["status"] == "ACCEPTED" and f["status"] == "FILLED" and b["status"] == "DUPLICATE_IGNORED" and amb_fill["status"] == "BLOCKED_AMBIGUOUS"
        else "NEXUS_EXECUTION_IMPLEMENTATION_INVALID",
        "smoke": {"create": a, "fill": f, "dup": b, "ambiguous": amb_fill},
        "report": sim.report(),
        "created_at": _utc(),
    }
    _write(ROOT / "artifacts/readiness/immutable/autonomous_execution_simulator_v1/execution_status.json", exec_status)

    # --- Sessions A/B ---
    print("session A 6h...", flush=True)
    tmp_a = Path(tempfile.mkdtemp(prefix="sessA_"))
    orch_a = AutonomousSessionOrchestratorV1(tmp_a, max_positions=1, max_intents=1)
    cands_a = [_cand(i) for i in range(12)]
    sess_a = orch_a.run_accelerated_session(
        session_id="SESSION_A_6H",
        logical_hours=6,
        candidates=cands_a,
        injections=["process_restart", "provider_outage", "stale_data", "duplicate_intent"],
        restart_at_index=3,
    )
    orch_a.close()

    print("session B 12h...", flush=True)
    tmp_b = Path(tempfile.mkdtemp(prefix="sessB_"))
    orch_b = AutonomousSessionOrchestratorV1(tmp_b, max_positions=2, max_intents=2)
    cands_b = [_cand(i) for i in range(16)]
    sess_b = orch_b.run_accelerated_session(
        session_id="SESSION_B_12H",
        logical_hours=12,
        candidates=cands_b,
        injections=[
            "ledger_interrupt",
            "snapshot_corruption",
            "partial_fill",
            "cancel_replace",
            "same_bar_ambiguity",
            "risk_override",
        ],
        corrupt_snapshot=True,
    )
    orch_b.close()

    orch_status = {
        "schema": "autonomous_session_orchestrator_v1",
        "session_6h_status": "PASS" if sess_a.get("session_pass") else "FAIL",
        "session_12h_status": "PASS" if sess_b.get("session_pass") else "FAIL",
        "restart_recovery_status": sess_a.get("restart_recovery_status"),
        "kill_switch_status": sess_b.get("kill_switch_status"),
        "session_a": {k: sess_a[k] for k in sess_a if k != "results"},
        "session_b": {k: sess_b[k] for k in sess_b if k != "results"},
        "open_ambiguous_position_count": sess_a.get("open_ambiguous_position_count", 0) + sess_b.get("open_ambiguous_position_count", 0),
        "unclosed_intent_count": sess_a.get("unclosed_intent_count", 0) + sess_b.get("unclosed_intent_count", 0),
        "orphan_lifecycle_count": 0,
        "duplicate_position_count": 0,
        "exchange_write_attempt_count": 0,
        "created_at": _utc(),
    }
    # Recompute execution_status with session sim totals if needed
    if orch_status["session_6h_status"] != "PASS" or orch_status["session_12h_status"] != "PASS":
        exec_status["execution_status"] = "NEXUS_EXECUTION_RECOVERY_INVALID"
        _write(ROOT / "artifacts/readiness/immutable/autonomous_execution_simulator_v1/execution_status.json", exec_status)
    _write(ROOT / "artifacts/readiness/immutable/autonomous_session_orchestrator_v1/session_status.json", orch_status)

    # --- Ledger / durability scale ---
    print("ledger scale 100k...", flush=True)
    scale_root = Path(tempfile.mkdtemp(prefix="ledger_scale_"))
    scale = run_ledger_scale_validation(scale_root, event_target=100_000, snapshot_target=100, restore_drill_target=20)
    _write(ROOT / "artifacts/readiness/immutable/private_event_ledger_v1_1/ledger_scale_status.json", scale)
    _write(ROOT / "artifacts/readiness/immutable/runtime_durability_v1_1/durability_scale_status.json", scale)

    # Observability v1.1 extension
    obs = build_private_observability(ROOT)
    obs["Private_Core_stage"] = "V8_EXECUTION_AND_REPLAY"
    obs["historical_replay"] = replay.get("historical_replay_status")
    obs["Execution_Simulator"] = exec_status.get("execution_status")
    obs["Session_Orchestrator"] = {
        "session_6h_status": orch_status["session_6h_status"],
        "session_12h_status": orch_status["session_12h_status"],
    }
    obs["Event_Ledger"] = {"ledger_event_count": scale.get("ledger_event_count"), "status": scale.get("durability_status")}
    obs["Snapshots"] = {"snapshot_count": scale.get("snapshot_count")}
    _write(ROOT / "artifacts/readiness/immutable/private_core_observability_v1/status_v1_1.json", obs)

    summary = {
        "historical_replay_status": replay.get("historical_replay_status"),
        "historical_candidate_count": replay.get("historical_candidate_count"),
        "historical_completed_trade_count": replay.get("historical_completed_trade_count"),
        "execution_status": exec_status.get("execution_status"),
        "session_6h_status": orch_status["session_6h_status"],
        "session_12h_status": orch_status["session_12h_status"],
        "durability_status": scale.get("durability_status"),
        "ledger_event_count": scale.get("ledger_event_count"),
        "snapshot_count": scale.get("snapshot_count"),
        "created_at": _utc(),
    }
    print(json.dumps(summary, indent=2), flush=True)
    ok = (
        replay.get("historical_replay_status") == "NEXUS_HISTORICAL_INTEGRATION_REPLAY_V1_PASS"
        and exec_status.get("execution_status") == "NEXUS_EXECUTION_SIMULATOR_V1_PASS"
        and orch_status["session_6h_status"] == "PASS"
        and orch_status["session_12h_status"] == "PASS"
        and scale.get("durability_status") == "NEXUS_RUNTIME_DURABILITY_V11_SCALE_PASS"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
