"""V15-I Reflection and Lesson Replay Lab harness — immutable artifacts only.

HARD BAN: no *_status.json (lane or runtime human-facing status files).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_lesson_replay_v15.checkpoint import load_checkpoint_readonly
from backend.nexus_lesson_replay_v15.constants import (
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PACKAGE,
    PROHIBITED_PATHS_UNTOUCHED,
    SCHEMA,
)
from backend.nexus_lesson_replay_v15.fixtures import fixture_controls_manifest
from backend.nexus_lesson_replay_v15.gate import evaluate_real_lesson_gate
from backend.nexus_lesson_replay_v15.hard_bans import assert_no_status_json_filenames, hard_ban_inventory
from backend.nexus_lesson_replay_v15.replay_lab import run_replay_lab
from backend.nexus_lesson_replay_v15.secret_scan import scan_payload
from backend.nexus_lesson_replay_v15.simulated_trades import simulated_trades_manifest
from backend.nexus_lesson_replay_v15.two_pass import run_two_pass


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
    if path.name.lower().endswith("_status.json") or path.name.lower() == "status.json":
        raise RuntimeError(f"HARD_BAN no_status_json_lane_artifact: refused write {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def evaluate_lesson_replay_lab(
    *,
    root: Path | None = None,
    checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run replay lab + blocked real gate + two-pass review."""
    base = root or _repo_root()
    checkpoint = load_checkpoint_readonly(checkpoint_path)
    lab = run_replay_lab()
    gate = evaluate_real_lesson_gate(
        v23_terminal_status=checkpoint.get("V2_3_terminal_status"),
        v23_complete=bool(checkpoint.get("V2_3_complete")),
        quality_gates_passed=False,
        has_real_bad_process_source=False,
        lesson_retrieved=False,
        measurable_process_change=False,
        repeat_error_prevention=False,
    )

    pre_bundle = {
        "real_gate": gate,
        "replay_lab": lab,
        "checkpoint": checkpoint,
        "hard_bans": list(HARD_BANS),
        "secret_leak_count": 0,
        "auto_integrate": False,
        "pr27_merged": False,
        "wrote_status_json": False,
    }
    scan1 = scan_payload(
        {
            "replay_lab": lab,
            "gate": gate,
            "checkpoint_meta": {
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
            },
        }
    )
    pre_bundle["secret_leak_count"] = scan1["secret_leak_count"]

    two_pass = run_two_pass(pre_bundle)

    result = {
        "schema": SCHEMA,
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
        "hard_ban_inventory": hard_ban_inventory(),
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
        "REAL_LESSON_PREVENTION_STATUS": gate.get("REAL_LESSON_PREVENTION_STATUS"),
        "replay_lab_status": lab.get("replay_lab_status"),
        "new_policy_effect_lesson_count": int(gate.get("new_policy_effect_lesson_count") or 0),
        "fixture_misrepresented_as_real": False,
        "misrepresented_as_real_learning": False,
        "loss_is_not_automatic_bad_process": bool(
            ((lab.get("classification_matrix") or {}).get("combined") or {}).get(
                "loss_is_not_automatic_bad_process"
            )
        ),
        "classification_class_counts": ((lab.get("classification_matrix") or {}).get("combined") or {}).get(
            "class_counts"
        ),
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "mainnet": False,
        "real_money": False,
        "profitability_claimed": False,
        "pr27_merged": False,
        "auto_integrate": False,
        "wrote_status_json": False,
        "secret_leak_count": scan1["secret_leak_count"],
        "secret_scan": scan1,
        "two_pass": two_pass,
        "two_pass_adversarial_review": True,
        "replay_lab": lab,
        "real_gate": gate,
        "pass": bool(
            lab.get("replay_lab_status") == "PASS"
            and gate.get("REAL_LESSON_PREVENTION_STATUS") == "BLOCKED"
            and two_pass.get("two_pass_ok")
            and scan1["secret_leak_count"] == 0
            and not checkpoint.get("V2_3_complete")
        ),
    }
    # Lane PASS means: replay lab proven + real correctly BLOCKED + two-pass clean.
    # It does NOT mean V2.3 complete or real lesson prevention executed.
    result["status"] = (
        "NEXUS_V15_I_LESSON_REPLAY_LAB_PASS_REAL_BLOCKED"
        if result["pass"]
        else "NEXUS_V15_I_LESSON_REPLAY_LAB_FAIL"
    )
    result["digest"] = _digest(
        {
            "lab": lab.get("proof_digest"),
            "real_status": gate.get("REAL_LESSON_PREVENTION_STATUS"),
            "two_pass": two_pass.get("digests"),
            "secret_leak_count": scan1["secret_leak_count"],
        }
    )
    return result


def write_immutable_artifacts(
    result: dict[str, Any],
    *,
    root: Path | None = None,
    commit: str | None = None,
) -> Path:
    base = root or _repo_root()
    art = base / ARTIFACT_REL
    art.mkdir(parents=True, exist_ok=True)
    head = commit or result.get("head_commit") or _git_head(base)
    stamped = dict(result)
    stamped["head_commit"] = head
    stamped["lane_head"] = head
    stamped["feature_commit"] = head
    stamped["artifact_dir"] = str(art.resolve())

    lab = stamped.get("replay_lab") or {}
    gate = stamped.get("real_gate") or {}
    two_pass = stamped.get("two_pass") or {}

    files: dict[str, Any] = {
        "summary.json": {
            "lane": LANE,
            "lane_name": LANE_NAME,
            "status": stamped.get("status"),
            "pass": stamped.get("pass"),
            "REAL_LESSON_PREVENTION_STATUS": stamped.get("REAL_LESSON_PREVENTION_STATUS"),
            "replay_lab_status": stamped.get("replay_lab_status"),
            "V2_3_complete": stamped.get("V2_3_complete"),
            "V2_3_terminal_status": stamped.get("V2_3_terminal_status"),
            "new_policy_effect_lesson_count": stamped.get("new_policy_effect_lesson_count"),
            "loss_is_not_automatic_bad_process": stamped.get("loss_is_not_automatic_bad_process"),
            "classification_class_counts": stamped.get("classification_class_counts"),
            "digest": stamped.get("digest"),
            "head_commit": head,
            "base_commit": BASE_COMMIT,
            "branch": BRANCH,
            "auto_integrate": False,
            "pr27_merged": False,
            "wrote_status_json": False,
            "two_pass_ok": two_pass.get("two_pass_ok"),
        },
        "hard_bans.json": hard_ban_inventory(),
        "secret_scan.json": stamped.get("secret_scan") or {},
        "two_pass_report.json": two_pass,
        "pass1_summary.json": two_pass.get("pass1") or {},
        "pass2_adversarial.json": two_pass.get("pass2") or {},
        "classification_matrix.json": {
            "class_counts": stamped.get("classification_class_counts"),
            "loss_is_not_automatic_bad_process": stamped.get("loss_is_not_automatic_bad_process"),
            "matrix": lab.get("classification_matrix"),
        },
        "replay_lab_report.json": lab,
        "simulated_trades.json": simulated_trades_manifest(),
        "fixture_controls.json": fixture_controls_manifest(),
        "real_lesson_prevention_gate.json": gate,
        "incomplete_sot.json": stamped.get("incomplete_sot") or {},
    }

    written_names = list(files.keys()) + ["SUMMARY.md"]
    assert_no_status_json_filenames(written_names)

    for name, obj in files.items():
        _write_json(art / name, obj)

    summary_md = "\n".join(
        [
            f"# {LANE} — {LANE_NAME}",
            "",
            f"- status: `{stamped.get('status')}`",
            f"- pass: `{stamped.get('pass')}`",
            f"- REAL_LESSON_PREVENTION_STATUS: `{stamped.get('REAL_LESSON_PREVENTION_STATUS')}`",
            f"- replay_lab_status: `{stamped.get('replay_lab_status')}`",
            f"- V2_3_complete: `{stamped.get('V2_3_complete')}`",
            f"- two_pass_ok: `{two_pass.get('two_pass_ok')}`",
            f"- head_commit: `{head}`",
            f"- wrote_status_json: `false`",
            "",
            "Lane PASS means replay classification lab proven and Real Lesson Prevention correctly BLOCKED.",
            "It does not mean V2.3 VERIFIED or real policy-effect lessons executed.",
            "",
        ]
    )
    (art / "SUMMARY.md").write_text(summary_md, encoding="utf-8")
    return art


def run_lesson_replay_lab(
    *,
    root: Path | None = None,
    write_artifact: bool = True,
    commit: str | None = None,
    pytest_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = root or _repo_root()
    head = commit or _git_head(base)
    result = evaluate_lesson_replay_lab(root=base)
    result["head_commit"] = head
    result["lane_head"] = head
    result["pytest"] = pytest_info or {}
    result["pytest_passed"] = bool((pytest_info or {}).get("passed"))
    if write_artifact:
        art = write_immutable_artifacts(result, root=base, commit=head)
        result["artifact_dir"] = str(art.resolve())
    return result
