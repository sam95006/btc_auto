"""Pass-1 proof matrix for V15-J Continuous Autonomy Operations Control."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from backend.nexus_autonomy.continuous_ops_control_v15.constants import (
    HARD_BANS,
    PRESERVED_FACTS,
    PROOF_IDS_PASS1,
    READ_OPS,
    SCHEMA_PASS1,
)
from backend.nexus_autonomy.continuous_ops_control_v15.control_plane import (
    ContinuousAutonomyOpsControlV15,
)


def _ok(name: str, passed: bool, **detail: Any) -> dict[str, Any]:
    return {
        "proof_id": name,
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "detail": detail,
    }


def _mutate(
    ctrl: ContinuousAutonomyOpsControlV15,
    op: str,
    key: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proof = ctrl.issue_founder_proof(op=op, idempotency_key=key)
    return ctrl.mutate(op, idempotency_key=key, founder_proof=proof, payload=payload)


def proof_start_with_founder_auth(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "start")
    try:
        r = _mutate(ctrl, "start", "start-1", payload={"session_id": "sess-start-1"})
        passed = (
            r.get("status") == "PASS"
            and r.get("state_after") == "RUNNING"
            and r.get("founder_authorization_present") is True
            and r.get("ledger", {}).get("sequence_number") is not None
            and int(r.get("checkpoint", {}).get("count") or 0) >= 1
            and r.get("exchange_write") is False
        )
        return _ok("start_with_founder_auth", passed, result=r)
    finally:
        ctrl.close()


def proof_pause_resume_cycle(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "pause_resume")
    try:
        s = _mutate(ctrl, "start", "pr-start", payload={"session_id": "sess-pr"})
        p = _mutate(ctrl, "pause", "pr-pause", payload={"reason": "founder_pause"})
        r = _mutate(ctrl, "resume", "pr-resume", payload={"reason": "founder_resume"})
        passed = (
            s.get("status") == "PASS"
            and p.get("status") == "PASS"
            and p.get("state_after") == "PAUSED"
            and r.get("status") == "PASS"
            and r.get("state_after") == "RUNNING"
        )
        return _ok("pause_resume_cycle", passed, start=s, pause=p, resume=r)
    finally:
        ctrl.close()


def proof_safe_stop_and_recover(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "safe_stop")
    try:
        s = _mutate(ctrl, "start", "ss-start", payload={"session_id": "sess-ss"})
        stop = _mutate(ctrl, "safe_stop", "ss-stop", payload={"reason": "founder_safe_stop"})
        rec = _mutate(ctrl, "recover", "ss-recover", payload={"reason": "founder_recover"})
        passed = (
            s.get("status") == "PASS"
            and stop.get("status") == "PASS"
            and stop.get("state_after") == "STOPPED"
            and rec.get("status") == "PASS"
            and rec.get("state_after") == "RUNNING"
            and rec.get("silent_recovery_guess") is not True
        )
        return _ok("safe_stop_and_recover", passed, start=s, stop=stop, recover=rec)
    finally:
        ctrl.close()


def proof_kill_switch_terminal(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "kill")
    try:
        _mutate(ctrl, "start", "k-start", payload={"session_id": "sess-k"})
        k = _mutate(ctrl, "kill", "k-kill", payload={"reason": "founder_kill"})
        # resume must be denied after kill
        proof = ctrl.issue_founder_proof(op="resume", idempotency_key="k-resume")
        denied = ctrl.mutate(
            "resume", idempotency_key="k-resume", founder_proof=proof, payload={}
        )
        passed = (
            k.get("status") == "PASS"
            and k.get("state_after") == "KILLED"
            and k.get("kill_engaged") is True
            and denied.get("status") == "DENIED"
        )
        return _ok("kill_switch_terminal", passed, kill=k, resume_denied=denied)
    finally:
        ctrl.close()


def proof_health_storage_provider_capture_blocks(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "blocks_a")
    try:
        _mutate(ctrl, "start", "ba-start", payload={"session_id": "sess-ba"})
        reads = {
            name: ctrl.read(name)
            for name in ("health", "storage", "provider_capacity", "capture_health")
        }
        passed = all(
            reads[n].get("exchange_write") is False and reads[n].get("read_only") is True
            for n in reads
        ) and reads["health"].get("status") in {"HEALTHY", "IDLE", "DEGRADED"}
        return _ok("health_storage_provider_capture_blocks", passed, reads=reads)
    finally:
        ctrl.close()


def proof_decision_execution_reflection_lesson_blocks(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "blocks_b")
    try:
        _mutate(ctrl, "start", "bb-start", payload={"session_id": "sess-bb"})
        reads = {
            name: ctrl.read(name)
            for name in (
                "decision_lifecycle",
                "execution_lifecycle",
                "reflection_lifecycle",
                "lesson_gate",
            )
        }
        passed = (
            reads["execution_lifecycle"].get("mode") == "SIMULATED_ONLY"
            and reads["execution_lifecycle"].get("exchange_write") is False
            and reads["lesson_gate"].get("promotion_allowed") is False
            and reads["decision_lifecycle"].get("decorative_intent_ids") is False
            and reads["reflection_lifecycle"].get("fabricated_learning") is False
        )
        return _ok("decision_execution_reflection_lesson_blocks", passed, reads=reads)
    finally:
        ctrl.close()


def proof_qualification_blocks_remain_blocked(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "qual")
    try:
        _mutate(ctrl, "start", "q-start", payload={"session_id": "sess-q"})
        qb = ctrl.read("qualification_blocks")
        adv = ctrl.attempt_qualification_advance("walk_forward")
        passed = (
            qb.get("all_blocked") is True
            and qb.get("qualification_advanced") is False
            and adv.get("status") == "DENIED"
            and adv.get("executed") is False
        )
        return _ok("qualification_blocks_remain_blocked", passed, blocks=qb, advance=adv)
    finally:
        ctrl.close()


def proof_mutating_requires_auth_idempotency_ledger_checkpoint_gate(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "mutate_req")
    try:
        missing = ctrl.mutate(
            "start",
            idempotency_key="mr-missing",
            founder_proof=None,
            payload={"session_id": "sess-mr"},
        )
        ok = _mutate(ctrl, "start", "mr-ok", payload={"session_id": "sess-mr"})
        replay = ctrl.mutate(
            "start",
            idempotency_key="mr-ok",
            founder_proof=ctrl.issue_founder_proof(op="start", idempotency_key="mr-ok"),
            payload={"session_id": "sess-mr"},
        )
        passed = (
            missing.get("status") == "DENIED"
            and "founder_auth" in str(missing.get("reason") or "")
            and ok.get("status") == "PASS"
            and ok.get("ledger", {}).get("event_id")
            and ok.get("checkpoint", {}).get("status") == "SNAPSHOT_OK"
            and ok.get("gate", {}).get("allowed") is True
            and replay.get("status") == "DUPLICATE_IGNORED"
            and replay.get("duplicate") is True
        )
        return _ok(
            "mutating_requires_auth_idempotency_ledger_checkpoint_gate",
            passed,
            missing=missing,
            ok=ok,
            replay=replay,
        )
    finally:
        ctrl.close()


def proof_exchange_write_hard_banned(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "xwrite")
    try:
        denied = ctrl.attempt_exchange_write(exchange_write=True, place_order=True)
        passed = (
            denied.get("status") == "DENIED"
            and denied.get("executed") is False
            and int(denied.get("exchange_write_attempt_count") or 0) >= 1
            and denied.get("demo_order_count") == 0
            and HARD_BANS.get("exchange_write") is True
        )
        return _ok("exchange_write_hard_banned", passed, denied=denied)
    finally:
        ctrl.close()


PROOF_RUNNERS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "start_with_founder_auth": proof_start_with_founder_auth,
    "pause_resume_cycle": proof_pause_resume_cycle,
    "safe_stop_and_recover": proof_safe_stop_and_recover,
    "kill_switch_terminal": proof_kill_switch_terminal,
    "health_storage_provider_capture_blocks": proof_health_storage_provider_capture_blocks,
    "decision_execution_reflection_lesson_blocks": proof_decision_execution_reflection_lesson_blocks,
    "qualification_blocks_remain_blocked": proof_qualification_blocks_remain_blocked,
    "mutating_requires_auth_idempotency_ledger_checkpoint_gate": (
        proof_mutating_requires_auth_idempotency_ledger_checkpoint_gate
    ),
    "exchange_write_hard_banned": proof_exchange_write_hard_banned,
}


def run_pass1(work: Path) -> dict[str, Any]:
    proofs = []
    for pid in PROOF_IDS_PASS1:
        runner = PROOF_RUNNERS[pid]
        proofs.append(runner(work / pid))
    passed = sum(1 for p in proofs if p.get("passed"))
    failed = [p["proof_id"] for p in proofs if not p.get("passed")]
    return {
        "schema": SCHEMA_PASS1,
        "pass": 1,
        "overall_status": "PASS" if not failed else "FAIL",
        "proofs_passed": passed,
        "proofs_total": len(PROOF_IDS_PASS1),
        "failed": failed,
        "proofs": proofs,
        "read_ops_covered": list(READ_OPS),
        **PRESERVED_FACTS,
        "hard_bans": HARD_BANS,
    }
