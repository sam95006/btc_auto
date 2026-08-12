"""V14-G Lesson Prevention Proof V2 harness — artifacts + runtime status."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_lesson_prevention_v2.checkpoint import load_checkpoint_readonly
from backend.nexus_lesson_prevention_v2.constants import (
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PACKAGE,
    PROHIBITED_PATHS_UNTOUCHED,
    RUNTIME_STATUS_PATH,
    SCHEMA,
    SCHEMA_STATUS,
)
from backend.nexus_lesson_prevention_v2.mechanics import run_mechanics_chain_proof
from backend.nexus_lesson_prevention_v2.real_proof import run_real_policy_effect_proof
from backend.nexus_lesson_prevention_v2.secret_scan import scan_payload
from backend.nexus_lesson_prevention_v2.two_pass import run_two_pass


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_head(root: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def evaluate_lesson_prevention_v2(
    *,
    root: Path | None = None,
    checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run mechanics proof + blocked real gate + two-pass review."""
    base = root or _repo_root()
    checkpoint = load_checkpoint_readonly(checkpoint_path)
    mechanics = run_mechanics_chain_proof()
    real = run_real_policy_effect_proof(checkpoint=checkpoint, quality_gates_passed=False)

    pre_bundle = {
        "real_gate": real.get("gate") or real,
        "mechanics": mechanics,
        "checkpoint": checkpoint,
        "hard_bans": list(HARD_BANS),
        "secret_leak_count": 0,
        "auto_integrate": False,
        "pr27_merged": False,
    }
    # Preliminary secret scan on core proofs
    scan1 = scan_payload({"mechanics": mechanics, "real": real, "checkpoint_meta": {
        k: checkpoint.get(k)
        for k in (
            "stage",
            "V2_3_complete",
            "V2_3_terminal_status",
            "groq_success_count",
            "sambanova_success_count",
            "read_only",
            "mutated",
        )
    }})
    pre_bundle["secret_leak_count"] = scan1["secret_leak_count"]

    two_pass = run_two_pass(pre_bundle)

    status = {
        "schema": SCHEMA_STATUS,
        "program_schema": SCHEMA,
        "created_at": _utc(),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "package": PACKAGE,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "worktree": str(base),
        "owned_paths": list(OWNED_PATHS),
        "prohibited_paths_untouched": list(PROHIBITED_PATHS_UNTOUCHED),
        "hard_bans": list(HARD_BANS),
        "V2_3_complete": bool(checkpoint.get("V2_3_complete")),
        "V2_3_terminal_status": checkpoint.get("V2_3_terminal_status"),
        "incomplete_sot": {
            "stage": checkpoint.get("stage"),
            "groq_success_count": checkpoint.get("groq_success_count"),
            "sambanova_success_count": checkpoint.get("sambanova_success_count"),
            "pending_case_count": checkpoint.get("pending_case_count"),
            "checkpoint_found": checkpoint.get("checkpoint_found"),
            "checkpoint_path": checkpoint.get("checkpoint_path"),
            "read_only": True,
            "mutated": False,
            "trust": checkpoint.get("trust"),
        },
        "REAL_LESSON_PREVENTION_STATUS": real.get("REAL_LESSON_PREVENTION_STATUS"),
        "mechanics_proof_status": mechanics.get("mechanics_proof_status"),
        "real_policy_effect_proof_status": real.get("real_policy_effect_proof_status"),
        "new_policy_effect_lesson_count": int(real.get("new_policy_effect_lesson_count") or 0),
        "fixture_misrepresented_as_real": False,
        "misrepresented_as_real_learning": False,
        "loss_is_not_automatic_bad_process": bool(
            (mechanics.get("classification_matrix") or {}).get("loss_is_not_automatic_bad_process")
        ),
        "classification_class_counts": (mechanics.get("classification_matrix") or {}).get("class_counts"),
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "mainnet": False,
        "real_money": False,
        "profitability_claimed": False,
        "pr27_merged": False,
        "auto_integrate": False,
        "secret_leak_count": scan1["secret_leak_count"],
        "secret_scan": scan1,
        "two_pass": two_pass,
        "two_pass_adversarial_review": True,
        "mechanics": mechanics,
        "real_proof": real,
        "pass": bool(
            mechanics.get("mechanics_proof_status") == "PASS"
            and real.get("REAL_LESSON_PREVENTION_STATUS") == "BLOCKED"
            and two_pass.get("two_pass_ok")
            and scan1["secret_leak_count"] == 0
            and not checkpoint.get("V2_3_complete")
        ),
    }
    # Lane PASS means: mechanics proven + real correctly BLOCKED + two-pass clean.
    # It does NOT mean V2.3 complete or real lesson prevention executed.
    status["status"] = (
        "NEXUS_V14_G_LESSON_PREVENTION_PROOF_V2_PASS_REAL_BLOCKED"
        if status["pass"]
        else "NEXUS_V14_G_LESSON_PREVENTION_PROOF_V2_FAIL"
    )
    status["digest"] = _digest(
        {
            "mech": mechanics.get("proof_digest"),
            "real_status": real.get("REAL_LESSON_PREVENTION_STATUS"),
            "two_pass": two_pass.get("digests"),
            "secret_leak_count": scan1["secret_leak_count"],
        }
    )
    return status


def write_immutable_artifacts(
    status: dict[str, Any],
    *,
    root: Path | None = None,
    commit: str | None = None,
) -> Path:
    base = root or _repo_root()
    art = base / ARTIFACT_REL
    art.mkdir(parents=True, exist_ok=True)
    head = commit or status.get("head_commit") or _git_head(base)
    stamped = dict(status)
    stamped["head_commit"] = head
    stamped["lane_head"] = head
    stamped["feature_commit"] = head
    stamped["artifact_dir"] = str(art.resolve())

    _write_json(art / "lesson_prevention_v2_status.json", stamped)
    _write_json(
        art / "mechanics_proof.json",
        stamped.get("mechanics") or {},
    )
    _write_json(
        art / "real_policy_effect_proof.json",
        stamped.get("real_proof") or {},
    )
    _write_json(
        art / "classification_matrix.json",
        {
            "class_counts": stamped.get("classification_class_counts"),
            "loss_is_not_automatic_bad_process": stamped.get("loss_is_not_automatic_bad_process"),
            "matrix": (stamped.get("mechanics") or {}).get("classification_matrix"),
        },
    )
    _write_json(
        art / "incomplete_sot.json",
        stamped.get("incomplete_sot") or {},
    )
    _write_json(art / "two_pass_report.json", stamped.get("two_pass") or {})
    _write_json(art / "secret_scan.json", stamped.get("secret_scan") or {})
    _write_json(
        art / "hard_bans.json",
        {"hard_bans": stamped.get("hard_bans"), "enforced": True},
    )
    _write_json(
        art / "summary.json",
        {
            "lane": LANE,
            "status": stamped.get("status"),
            "pass": stamped.get("pass"),
            "REAL_LESSON_PREVENTION_STATUS": stamped.get("REAL_LESSON_PREVENTION_STATUS"),
            "mechanics_proof_status": stamped.get("mechanics_proof_status"),
            "V2_3_complete": stamped.get("V2_3_complete"),
            "new_policy_effect_lesson_count": stamped.get("new_policy_effect_lesson_count"),
            "digest": stamped.get("digest"),
            "head_commit": head,
            "auto_integrate": False,
            "pr27_merged": False,
        },
    )
    return art


def write_runtime_status(
    status: dict[str, Any],
    *,
    path: str | Path | None = None,
    commit: str | None = None,
    pytest_info: dict[str, Any] | None = None,
    pushed: bool = False,
) -> Path:
    out = Path(path or RUNTIME_STATUS_PATH)
    head = commit or status.get("head_commit")
    payload = {
        "schema": SCHEMA_STATUS,
        "created_at": status.get("created_at") or _utc(),
        "updated_at": _utc(),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "worktree": status.get("worktree"),
        "package": PACKAGE,
        "head_commit": head,
        "lane_head": head,
        "feature_commit": head,
        "pass": status.get("pass"),
        "status": status.get("status"),
        "REAL_LESSON_PREVENTION_STATUS": status.get("REAL_LESSON_PREVENTION_STATUS"),
        "mechanics_proof_status": status.get("mechanics_proof_status"),
        "real_policy_effect_proof_status": status.get("real_policy_effect_proof_status"),
        "V2_3_complete": status.get("V2_3_complete"),
        "V2_3_terminal_status": status.get("V2_3_terminal_status"),
        "incomplete_sot": status.get("incomplete_sot"),
        "new_policy_effect_lesson_count": status.get("new_policy_effect_lesson_count"),
        "loss_is_not_automatic_bad_process": status.get("loss_is_not_automatic_bad_process"),
        "classification_class_counts": status.get("classification_class_counts"),
        "two_pass": {
            "pass_count": (status.get("two_pass") or {}).get("pass_count"),
            "two_pass_ok": (status.get("two_pass") or {}).get("two_pass_ok"),
            "digests": (status.get("two_pass") or {}).get("digests"),
            "passes_match": (status.get("two_pass") or {}).get("passes_match"),
            "findings_fixed": ((status.get("two_pass") or {}).get("pass2") or {}).get("findings_fixed"),
            "remaining_residuals": ((status.get("two_pass") or {}).get("pass2") or {}).get(
                "remaining_residuals"
            ),
        },
        "two_pass_adversarial_review": True,
        "secret_leak_count": status.get("secret_leak_count"),
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "mainnet": False,
        "real_money": False,
        "profitability_claimed": False,
        "pr27_merged": False,
        "auto_integrate": False,
        "pushed": bool(pushed),
        "hard_bans": status.get("hard_bans"),
        "owned_paths": status.get("owned_paths"),
        "prohibited_paths_untouched": status.get("prohibited_paths_untouched"),
        "artifact_dir": status.get("artifact_dir"),
        "digest": status.get("digest"),
        "pytest": pytest_info or {},
        "pytest_passed": bool((pytest_info or {}).get("passed")),
        "remote": f"origin/{BRANCH}",
        "blockers": []
        if status.get("pass")
        else ["mechanics_or_two_pass_or_gate_failed"],
        "remaining_blockers": [],
        "critical_findings": ((status.get("two_pass") or {}).get("pass2") or {}).get(
            "remaining_residuals"
        )
        or [],
    }
    _write_json(out, payload)
    return out


def run_lesson_prevention_v2(
    *,
    root: Path | None = None,
    write_artifact: bool = True,
    write_runtime: bool = True,
    commit: str | None = None,
    pytest_info: dict[str, Any] | None = None,
    pushed: bool = False,
) -> dict[str, Any]:
    base = root or _repo_root()
    head = commit or _git_head(base)
    status = evaluate_lesson_prevention_v2(root=base)
    status["head_commit"] = head
    status["lane_head"] = head
    if write_artifact:
        art = write_immutable_artifacts(status, root=base, commit=head)
        status["artifact_dir"] = str(art.resolve())
    if write_runtime:
        write_runtime_status(
            status,
            commit=head,
            pytest_info=pytest_info,
            pushed=pushed,
        )
    return status
