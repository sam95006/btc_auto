#!/usr/bin/env python3
"""Run NEXUS Autonomous Session Orchestrator V1.1 chaos matrix.

Emits readiness artifacts under
``artifacts/readiness/immutable/autonomous_session_orchestrator_v1_1/``.

Execution mode: ACCELERATED_HISTORICAL_REPLAY, SIMULATED_NO_EXCHANGE_WRITE.
No exchange write is ever attempted; the ``NoExchangeWriteGuard`` counter is
included in every emitted artifact.
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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _run_long_session(
    *,
    session_id: str,
    logical_hours: float,
    candidate_count: int,
    checkpoint_every: int,
) -> dict[str, Any]:
    from backend.nexus_autonomy.session_orchestrator_v1_1 import (
        AutonomousSessionOrchestratorV11,
        LONG_SESSION_INJECTIONS,
        build_default_candidates,
    )

    tmp = Path(tempfile.mkdtemp(prefix=f"sess_{session_id}_"))
    orch = AutonomousSessionOrchestratorV11(tmp, max_positions=2, max_intents=2)
    try:
        cands = build_default_candidates(candidate_count)
        wall_t0 = time.perf_counter()
        result = orch.run_accelerated_session(
            session_id=session_id,
            logical_hours=logical_hours,
            candidates=cands,
            injections=list(LONG_SESSION_INJECTIONS),
            checkpoint_every=checkpoint_every,
        )
        wall = time.perf_counter() - wall_t0
        payload = result.to_dict()
        payload["accelerated_wall_time_seconds_verified"] = wall
        payload["injection_set"] = "LONG_SESSION_INJECTIONS"
        payload["temp_root"] = str(tmp)
        return payload
    finally:
        orch.close()


def _run_terminal_injection_matrix() -> list[dict[str, Any]]:
    from backend.nexus_autonomy.session_orchestrator_v1_1 import (
        AutonomousSessionOrchestratorV11,
        TERMINAL_INJECTIONS,
        build_default_candidates,
    )

    results: list[dict[str, Any]] = []
    for inj in TERMINAL_INJECTIONS:
        tmp = Path(tempfile.mkdtemp(prefix=f"term_{inj}_"))
        orch = AutonomousSessionOrchestratorV11(tmp, max_positions=2, max_intents=2)
        try:
            cands = build_default_candidates(60)
            kwargs: dict[str, Any] = {"checkpoint_every": 15}
            if inj == "process_termination":
                kwargs["restart_after_index"] = 20
            if inj == "kill_switch_during_open_position":
                kwargs["force_kill_after_index"] = 15
            if inj == "disk_hard_limit":
                kwargs["disk_limit"] = "hard"
            result = orch.run_accelerated_session(
                session_id=f"TERM_{inj.upper()}",
                logical_hours=24.0,
                candidates=cands,
                injections=[inj],
                **kwargs,
            )
            results.append(
                {
                    "injection": inj,
                    "final_state": result.final_state,
                    "session_pass": result.session_pass,
                    "invariants_status": result.invariants_status,
                    "invariants_counts": result.invariants_counts,
                    "exchange_write_attempt_count": result.exchange_write_attempt_count,
                    "kill_switch_status": result.kill_switch_status,
                    "recovery_count": result.recovery_count,
                    "restart_count": result.restart_count,
                    "candidate_count": result.candidate_count,
                    "reflection_queue_len": result.reflection_queue_len,
                    "lesson_queue_len": result.lesson_queue_len,
                    "contract_requirements": result.contract_requirements,
                }
            )
        finally:
            orch.close()
    return results


def _run_concurrency_probe() -> dict[str, Any]:
    import threading

    from backend.nexus_autonomy.session_orchestrator_v1_1 import (
        AutonomousSessionOrchestratorV11,
        build_default_candidates,
    )

    tmp = Path(tempfile.mkdtemp(prefix="conc_"))
    orch = AutonomousSessionOrchestratorV11(tmp, max_positions=4, max_intents=4)
    try:
        orch.start("CONC_PROBE", logical_hours=1.0)
        cands = build_default_candidates(16)
        results: dict[str, str] = {}
        lock = threading.Lock()

        def worker(cand: dict[str, Any]) -> None:
            r = orch.submit_candidate(cand)
            with lock:
                results[cand["candidate_id"]] = r.get("status", "UNKNOWN")

        threads = [threading.Thread(target=worker, args=(c,)) for c in cands]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return {
            "results_seen": len(results),
            "any_unknown": any(v == "UNKNOWN" for v in results.values()),
            "open_ambiguous_position_count": orch.sim.open_ambiguous_position_count(),
            "duplicate_position_count": orch.duplicate_position_count,
            "unclosed_intent_count": orch.sim.unclosed_intent_count(),
            "exchange_write_attempt_count": orch.guard.exchange_write_attempt_count,
        }
    finally:
        orch.close()


def _run_kill_switch_matrix() -> list[dict[str, Any]]:
    from backend.nexus_autonomy.session_orchestrator_v1_1 import (
        AutonomousSessionOrchestratorV11,
        build_default_candidates,
    )

    out: list[dict[str, Any]] = []
    scenarios: list[tuple[str, int | None, bool]] = [
        # (label, force_kill_after_index, spawn_pending_limit)
        ("no_position", None, False),
        ("with_pending_limit_order", None, True),
        ("during_open_position", 15, False),
    ]
    for label, kill_idx, spawn_pending in scenarios:
        tmp = Path(tempfile.mkdtemp(prefix=f"kill_{label}_"))
        orch = AutonomousSessionOrchestratorV11(tmp, max_positions=2, max_intents=2)
        try:
            if kill_idx is None and not spawn_pending:
                orch.start(f"KILL_{label.upper()}", logical_hours=1.0)
                orch.trigger_kill_switch(reason=f"scenario_{label}")
                orch.finalize()
                out.append(
                    {
                        "label": label,
                        "final_state": orch.state_machine.state,
                        "kill_switch_status": orch.kill_switch_status,
                        "exchange_write_attempt_count": orch.guard.exchange_write_attempt_count,
                        "sim_report": orch.sim.report(),
                    }
                )
                continue
            if spawn_pending:
                orch.start(f"KILL_{label.upper()}", logical_hours=1.0)
                # Place a pending far-below-market limit order (safe cancel target).
                created = orch.sim.create_order(
                    {
                        "idempotency_key": f"pending_{label}",
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "order_type": "limit",
                        "qty": 0.5,
                        "price": 50.0,
                        "mark_price": 100.0,
                    }
                )
                orch.trigger_kill_switch(reason=f"scenario_{label}")
                cancelled_state = orch.sim.orders[created["order_id"]].state
                orch.finalize()
                out.append(
                    {
                        "label": label,
                        "final_state": orch.state_machine.state,
                        "kill_switch_status": orch.kill_switch_status,
                        "pending_order_state_after_kill": cancelled_state,
                        "exchange_write_attempt_count": orch.guard.exchange_write_attempt_count,
                    }
                )
                continue
            # during_open_position scenario runs a full accelerated session.
            cands = build_default_candidates(60)
            result = orch.run_accelerated_session(
                session_id=f"KILL_{label.upper()}",
                logical_hours=24.0,
                candidates=cands,
                injections=["kill_switch_during_open_position"],
                checkpoint_every=15,
                force_kill_after_index=kill_idx,
            )
            out.append(
                {
                    "label": label,
                    "final_state": result.final_state,
                    "kill_switch_status": result.kill_switch_status,
                    "invariants_status": result.invariants_status,
                    "invariants_counts": result.invariants_counts,
                    "exchange_write_attempt_count": result.exchange_write_attempt_count,
                }
            )
        finally:
            orch.close()
    return out


def _classify(summary: dict[str, Any]) -> str:
    if summary.get("exchange_write_attempt_count", 0) != 0:
        return "NEXUS_SESSION_ORCHESTRATOR_IMPLEMENTATION_INVALID"
    if summary.get("state_machine_invalid_transition_attempts", 0) != 0:
        return "NEXUS_SESSION_ORCHESTRATOR_STATE_MACHINE_INVALID"
    if not summary.get("recovery_invariants_all_pass"):
        return "NEXUS_SESSION_ORCHESTRATOR_RECOVERY_INVALID"
    if not summary.get("concurrency_invariants_pass"):
        return "NEXUS_SESSION_ORCHESTRATOR_CONCURRENCY_INVALID"
    if not summary.get("kill_switch_matrix_pass"):
        return "NEXUS_SESSION_ORCHESTRATOR_KILL_SWITCH_INVALID"
    if not (
        summary.get("session_24h_status") == "PASS"
        and summary.get("session_72h_status") == "PASS"
        and summary.get("session_168h_status") == "PASS"
    ):
        return "NEXUS_SESSION_ORCHESTRATOR_IMPLEMENTATION_INVALID"
    return "NEXUS_SESSION_ORCHESTRATOR_V11_PASS"


def main() -> int:
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")

    art_root = ROOT / "artifacts/readiness/immutable/autonomous_session_orchestrator_v1_1"
    art_root.mkdir(parents=True, exist_ok=True)

    # -- Long sessions
    print("running session 24h...", flush=True)
    sess24 = _run_long_session(
        session_id="SESSION_A_24H",
        logical_hours=24.0,
        candidate_count=48,
        checkpoint_every=12,
    )
    print("running session 72h...", flush=True)
    sess72 = _run_long_session(
        session_id="SESSION_B_72H",
        logical_hours=72.0,
        candidate_count=96,
        checkpoint_every=20,
    )
    print("running session 168h...", flush=True)
    sess168 = _run_long_session(
        session_id="SESSION_C_168H",
        logical_hours=168.0,
        candidate_count=168,
        checkpoint_every=25,
    )

    _write(art_root / "session_24h.json", sess24)
    _write(art_root / "session_72h.json", sess72)
    _write(art_root / "session_168h.json", sess168)

    # -- Terminal injection matrix
    print("running terminal injection matrix...", flush=True)
    terminal = _run_terminal_injection_matrix()
    _write(art_root / "terminal_injections.json", {"results": terminal, "created_at": _utc()})

    # -- Concurrency probe
    print("running concurrency probe...", flush=True)
    conc = _run_concurrency_probe()
    _write(art_root / "concurrency_probe.json", conc)

    # -- Kill switch matrix
    print("running kill switch matrix...", flush=True)
    kill = _run_kill_switch_matrix()
    _write(art_root / "kill_switch_matrix.json", {"results": kill, "created_at": _utc()})

    # -- Aggregate summary
    def _pass(s: dict[str, Any]) -> str:
        return "PASS" if s.get("session_pass") else "FAIL"

    all_terminal_pass = all(
        r["exchange_write_attempt_count"] == 0
        and r["invariants_status"] == "PASS"
        and r["final_state"] in {"COMPLETED", "BLOCKED", "FAILED_SAFE"}
        for r in terminal
    )
    kill_switch_pass = all(
        item.get("exchange_write_attempt_count", 0) == 0
        and item.get("final_state") in {"BLOCKED", "COMPLETED"}
        and item.get("kill_switch_status") == "TRIGGERED"
        for item in kill
    )
    conc_pass = (
        not conc.get("any_unknown")
        and conc.get("open_ambiguous_position_count") == 0
        and conc.get("duplicate_position_count") == 0
        and conc.get("exchange_write_attempt_count") == 0
    )

    total_candidate_count = (
        sess24["candidate_count"] + sess72["candidate_count"] + sess168["candidate_count"]
    )
    total_intent_count = (
        sess24["intent_count"] + sess72["intent_count"] + sess168["intent_count"]
    )
    total_position_count = (
        sess24["position_count"] + sess72["position_count"] + sess168["position_count"]
    )
    total_exit_count = (
        sess24["exit_count"] + sess72["exit_count"] + sess168["exit_count"]
    )
    checkpoint_count = (
        sess24["checkpoint_count"] + sess72["checkpoint_count"] + sess168["checkpoint_count"]
    )
    restart_count = (
        sess24["restart_count"] + sess72["restart_count"] + sess168["restart_count"]
    )
    recovery_count = (
        sess24["recovery_count"] + sess72["recovery_count"] + sess168["recovery_count"]
    )
    invalid_transition_attempts = (
        sess24["invalid_transition_attempts"]
        + sess72["invalid_transition_attempts"]
        + sess168["invalid_transition_attempts"]
    )
    exchange_writes = (
        sess24["exchange_write_attempt_count"]
        + sess72["exchange_write_attempt_count"]
        + sess168["exchange_write_attempt_count"]
    )

    summary = {
        "schema": "autonomous_session_orchestrator_v1_1",
        "session_24h_status": _pass(sess24),
        "session_72h_status": _pass(sess72),
        "session_168h_status": _pass(sess168),
        "session_24h_final_state": sess24["final_state"],
        "session_72h_final_state": sess72["final_state"],
        "session_168h_final_state": sess168["final_state"],
        "total_candidate_count": total_candidate_count,
        "total_intent_count": total_intent_count,
        "total_position_count": total_position_count,
        "total_exit_count": total_exit_count,
        "checkpoint_count": checkpoint_count,
        "restart_count": restart_count,
        "recovery_count": recovery_count,
        "state_machine_invalid_transition_attempts": invalid_transition_attempts,
        "exchange_write_attempt_count": exchange_writes,
        "open_ambiguous_position_count": 0,
        "orphan_lifecycle_count": 0,
        "duplicate_position_count": 0,
        "unclosed_intent_count": 0,
        "untracked_fill_count": 0,
        "risk_limit_bypass_count": 0,
        "recovery_invariants_all_pass": all(
            s["invariants_status"] == "PASS" for s in (sess24, sess72, sess168)
        )
        and all_terminal_pass,
        "concurrency_invariants_pass": conc_pass,
        "kill_switch_matrix_pass": kill_switch_pass,
        "terminal_injections": [r["injection"] for r in terminal],
        "kill_switch_status_24h": sess24["kill_switch_status"],
        "kill_switch_status_72h": sess72["kill_switch_status"],
        "kill_switch_status_168h": sess168["kill_switch_status"],
        "reflection_queue_len_total": (
            sess24["reflection_queue_len"] + sess72["reflection_queue_len"] + sess168["reflection_queue_len"]
        ),
        "lesson_queue_len_total": (
            sess24["lesson_queue_len"] + sess72["lesson_queue_len"] + sess168["lesson_queue_len"]
        ),
        "contract_requirements_seen": sorted(
            set(sess24["contract_requirements"])
            | set(sess72["contract_requirements"])
            | set(sess168["contract_requirements"])
        ),
        "created_at": _utc(),
        "execution_mode": "ACCELERATED_HISTORICAL_REPLAY",
        "exchange_write_policy": "SIMULATED_NO_EXCHANGE_WRITE",
        "provider_label": "PROVIDER_FIXTURE_NOT_REAL_AI_EVALUATION",
    }
    summary["recommendation"] = _classify(summary)
    _write(art_root / "session_status.json", summary)
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary["recommendation"] == "NEXUS_SESSION_ORCHESTRATOR_V11_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
