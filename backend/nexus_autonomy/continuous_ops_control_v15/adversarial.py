"""Pass-2 adversarial self-review for V15-J continuous autonomy ops."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from backend.nexus_autonomy.continuous_ops_control_v15.constants import (
    HARD_BANS,
    OWNED_PATHS,
    PRESERVED_FACTS,
    PROOF_IDS_PASS2,
    SCHEMA_PASS2,
)
from backend.nexus_autonomy.continuous_ops_control_v15.control_plane import (
    ContinuousAutonomyOpsControlV15,
)
from backend.nexus_autonomy.continuous_ops_control_v15.proofs import _mutate


def _ok(name: str, passed: bool, **detail: Any) -> dict[str, Any]:
    return {
        "proof_id": name,
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "detail": detail,
    }


def neg_missing_founder_auth(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "neg_missing_auth")
    try:
        r = ctrl.mutate(
            "start",
            idempotency_key="neg-missing",
            founder_proof=None,
            payload={"session_id": "sess-neg"},
        )
        passed = r.get("status") == "DENIED" and r.get("founder_authorization_present") is not True
        return _ok("neg_missing_founder_auth", passed, result=r)
    finally:
        ctrl.close()


def neg_spoofed_founder_auth(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "neg_spoof")
    try:
        spoof = {
            "proof_version": "v15j_founder_auth_proof_v1",
            "proof_id": "spoofed-proof-id",
            "realm": "NEXUS_FOUNDER_PRIVATE",
            "op": "start",
            "idempotency_key": "neg-spoof",
            "session_id": ctrl._session_id,
            "mac": "0" * 64,
            "nonce": "spoof",
            "founder_authorization_present": True,
        }
        r = ctrl.mutate(
            "start",
            idempotency_key="neg-spoof",
            founder_proof=spoof,
            payload={"session_id": "sess-spoof"},
        )
        passed = r.get("status") == "DENIED" and "founder_auth" in str(r.get("reason") or "")
        return _ok("neg_spoofed_founder_auth", passed, result=r)
    finally:
        ctrl.close()


def neg_idempotency_replay(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "neg_idem")
    try:
        first = _mutate(ctrl, "start", "idem-1", payload={"session_id": "sess-idem"})
        # Second call with same key must not re-apply transition / must be duplicate
        second = ctrl.mutate(
            "start",
            idempotency_key="idem-1",
            founder_proof=None,  # even without proof, idempotency short-circuits
            payload={"session_id": "sess-idem"},
        )
        passed = (
            first.get("status") == "PASS"
            and second.get("status") == "DUPLICATE_IGNORED"
            and second.get("duplicate") is True
            and ctrl.status().get("checkpoint_count") == first.get("checkpoint", {}).get("count")
        )
        return _ok("neg_idempotency_replay", passed, first=first, second=second)
    finally:
        ctrl.close()


def neg_exchange_write_trap(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "neg_xwrite")
    try:
        r = ctrl.attempt_exchange_write(exchange_write=True, demo_order=True, mainnet=True)
        passed = (
            r.get("status") == "DENIED"
            and r.get("executed") is False
            and int(r.get("exchange_write_attempt_count") or 0) >= 1
            and r.get("demo_order_count") == 0
            and HARD_BANS["exchange_write"] is True
        )
        return _ok("neg_exchange_write_trap", passed, result=r)
    finally:
        ctrl.close()


def neg_qualification_advance_refused(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "neg_qual")
    try:
        _mutate(ctrl, "start", "nq-start", payload={"session_id": "sess-nq"})
        r = ctrl.attempt_qualification_advance("oos_reservation")
        qb = ctrl.read("qualification_blocks")
        passed = (
            r.get("status") == "DENIED"
            and r.get("executed") is False
            and qb.get("all_blocked") is True
            and qb.get("stages", {}).get("oos_reservation") == "BLOCKED"
        )
        return _ok("neg_qualification_advance_refused", passed, result=r, blocks=qb)
    finally:
        ctrl.close()


def neg_kill_blocks_resume(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "neg_kill")
    try:
        _mutate(ctrl, "start", "nk-start", payload={"session_id": "sess-nk"})
        _mutate(ctrl, "kill", "nk-kill", payload={"reason": "adversarial_kill"})
        proof = ctrl.issue_founder_proof(op="resume", idempotency_key="nk-resume")
        r = ctrl.mutate(
            "resume", idempotency_key="nk-resume", founder_proof=proof, payload={}
        )
        passed = r.get("status") == "DENIED" and ctrl.status().get("state") == "KILLED"
        return _ok("neg_kill_blocks_resume", passed, result=r)
    finally:
        ctrl.close()


def neg_unsafe_transition_refused(work: Path) -> dict[str, Any]:
    ctrl = ContinuousAutonomyOpsControlV15(work / "neg_unsafe")
    try:
        # pause from COLD must fail gate (even with valid proof)
        proof = ctrl.issue_founder_proof(op="pause", idempotency_key="nu-pause")
        r = ctrl.mutate(
            "pause", idempotency_key="nu-pause", founder_proof=proof, payload={}
        )
        passed = (
            r.get("status") == "DENIED"
            and r.get("reason") == "unsafe_transition"
            and ctrl.status().get("state") == "COLD"
        )
        return _ok("neg_unsafe_transition_refused", passed, result=r)
    finally:
        ctrl.close()


def neg_no_status_json_artifact(artifact_dir: Path) -> dict[str, Any]:
    """Pass-2: lane must not emit *_status.json under owned artifact path."""
    banned = []
    if artifact_dir.exists():
        for p in artifact_dir.rglob("*_status.json"):
            banned.append(str(p))
    # Also ensure owned path list does not advertise a status.json
    owned_mentions = [p for p in OWNED_PATHS if p.endswith("_status.json")]
    passed = len(banned) == 0 and len(owned_mentions) == 0
    return _ok(
        "neg_no_status_json_artifact",
        passed,
        banned_files=banned,
        owned_mentions=owned_mentions,
        artifact_dir=str(artifact_dir),
    )


PASS2_RUNNERS: dict[str, Callable[..., dict[str, Any]]] = {
    "neg_missing_founder_auth": neg_missing_founder_auth,
    "neg_spoofed_founder_auth": neg_spoofed_founder_auth,
    "neg_idempotency_replay": neg_idempotency_replay,
    "neg_exchange_write_trap": neg_exchange_write_trap,
    "neg_qualification_advance_refused": neg_qualification_advance_refused,
    "neg_kill_blocks_resume": neg_kill_blocks_resume,
    "neg_unsafe_transition_refused": neg_unsafe_transition_refused,
    "neg_no_status_json_artifact": neg_no_status_json_artifact,
}


def run_pass2(work: Path, *, artifact_dir: Path) -> dict[str, Any]:
    proofs = []
    for pid in PROOF_IDS_PASS2:
        runner = PASS2_RUNNERS[pid]
        if pid == "neg_no_status_json_artifact":
            proofs.append(runner(artifact_dir))
        else:
            proofs.append(runner(work / pid))
    passed = sum(1 for p in proofs if p.get("passed"))
    failed = [p["proof_id"] for p in proofs if not p.get("passed")]
    return {
        "schema": SCHEMA_PASS2,
        "pass": 2,
        "overall_status": "PASS" if not failed else "FAIL",
        "proofs_passed": passed,
        "proofs_total": len(PROOF_IDS_PASS2),
        "failed": failed,
        "proofs": proofs,
        **PRESERVED_FACTS,
        "hard_bans": HARD_BANS,
        "owned_paths": list(OWNED_PATHS),
    }
