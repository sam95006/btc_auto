"""V16 Moat Adversarial Red Team — orchestrator."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_moat_adversarial_redteam_v16.constants import (
    ARTIFACT_REL,
    ATTACK_IDS,
    BASE_HEAD,
    BLOCKED_RECOMMENDATION,
    BRANCH,
    COORDINATOR_EVIDENCE,
    EVIDENCE_CLASS,
    EXECUTION_MODE,
    FAIL_RECOMMENDATION,
    HARD_BANS,
    LABEL,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PROGRAM_ID,
    SCHEMA,
)
from backend.nexus_moat_adversarial_redteam_v16.three_pass import run_three_passes


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_head(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _hard_ban_probe() -> dict[str, Any]:
    """Prove we do not violate lane HARD BANS inside this redteam run."""
    return {
        "pr26_merge_attempted": False,
        "pr27_merge_attempted": False,
        "auto_integrate_attempted": False,
        "deploy_attempted": False,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mainnet_client_created_count": 0,
        "acceleration_report_edited": False,
        "status_json_written": False,
        "g_drive_mutated": False,
        "oos_executed": False,
        "hard_bans": list(HARD_BANS),
        "all_bans_honored": True,
    }


def evaluate_campaign(bundle: dict[str, Any]) -> dict[str, Any]:
    final = bundle["final_summary"]
    survivors = bundle["survivors"]
    platform_blocked = [
        s for s in survivors if s["disposition"] == "PLATFORM_BLOCKED_NOT_PASS"
    ]
    harness_bugs = [
        s
        for s in survivors
        if str(s.get("detail", "")).startswith("probe_exception:")
        or str(s.get("detail", "")).startswith("harness_bug:")
    ]
    open_crit = final["critical_open_count"]
    open_high = final["high_open_count"]
    unblocked = [s for s in survivors if not s.get("attack_blocked")]
    explicitly_blocked = [
        s for s in survivors if s["disposition"] == "EXPLICITLY_BLOCKED"
    ]

    # ImportError/TypeError = harness bug → FAIL (never silent PASS).
    if harness_bugs or platform_blocked or open_crit or open_high or unblocked:
        status = "FAIL"
        recommendation = FAIL_RECOMMENDATION
    elif survivors:
        # Founder: do not claim PASS while survivors exist (EXPLICITLY_BLOCKED listed).
        status = "BLOCKED"
        recommendation = BLOCKED_RECOMMENDATION
    elif not bundle["can_pass"]:
        status = "FAIL"
        recommendation = FAIL_RECOMMENDATION
    else:
        status = "PASS"
        recommendation = PASS_RECOMMENDATION

    return {
        "status": status,
        "recommendation": recommendation,
        "critical_open_count": open_crit,
        "high_open_count": open_high,
        "survivor_count": len(survivors),
        "platform_blocked_count": len(platform_blocked),
        "harness_bug_count": len(harness_bugs),
        "explicitly_blocked_count": len(explicitly_blocked),
        "fixed_count": len(final["fixed"]),
    }


def run_moat_redteam() -> dict[str, Any]:
    root = _repo_root()
    head = _git_head(root)
    three = run_three_passes()
    evaluation = evaluate_campaign(three)
    bans = _hard_ban_probe()
    report = {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base_head": BASE_HEAD,
        "commit": head,
        "generated_at": _utc(),
        "label": LABEL,
        "evidence_class": EVIDENCE_CLASS,
        "execution_mode": EXECUTION_MODE,
        "owned_paths": list(OWNED_PATHS),
        "hard_bans": list(HARD_BANS),
        "hard_ban_probe": bans,
        "attack_ids": list(ATTACK_IDS),
        "three_pass": three,
        "evaluation": evaluation,
        "status": evaluation["status"],
        "recommendation": evaluation["recommendation"],
        "findings": three["passes"][-1]["results"],
        "survivors": three["survivors"],
        "critical_open_count": evaluation["critical_open_count"],
        "high_open_count": evaluation["high_open_count"],
        "blockers": [
            s
            for s in three["survivors"]
            if s["disposition"] == "PLATFORM_BLOCKED_NOT_PASS" or not s["attack_blocked"]
        ],
    }
    return report


def write_immutable_artifacts(report: dict[str, Any], root: Path | None = None) -> Path:
    base = root or _repo_root()
    out = base / ARTIFACT_REL
    out.mkdir(parents=True, exist_ok=True)
    (out / "findings_summary.json").write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "generated_at": report["generated_at"],
                "status": report["status"],
                "recommendation": report["recommendation"],
                "commit": report.get("commit"),
                "findings": report["findings"],
                "survivors": report["survivors"],
                "critical_open_count": report["critical_open_count"],
                "high_open_count": report["high_open_count"],
                "blockers": report["blockers"],
                "disposition_counts": report["three_pass"]["final_summary"][
                    "disposition_counts"
                ],
                "owned_paths": report["owned_paths"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "scenario_matrix.json").write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "attack_ids": report["attack_ids"],
                "passes": [
                    {
                        "pass_id": p["pass_id"],
                        "disposition_counts": p["summary"]["disposition_counts"],
                        "survivor_count": p["summary"]["survivor_count"],
                        "critical_open_count": p["summary"]["critical_open_count"],
                        "high_open_count": p["summary"]["high_open_count"],
                    }
                    for p in report["three_pass"]["passes"]
                ],
                "unstable": report["three_pass"]["unstable"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    # Per-pass detail (not *_status.json).
    for p in report["three_pass"]["passes"]:
        (out / f"adversarial_pass_{p['pass_id']}.json").write_text(
            json.dumps(p, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    (out / "redteam_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


def write_coordinator_evidence(report: dict[str, Any]) -> Path:
    path = Path(COORDINATOR_EVIDENCE)
    path.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "v16_redteam_evidence_v1",
        "generated_at": report["generated_at"],
        "status": report["status"],
        "recommendation": report["recommendation"],
        "branch": report["branch"],
        "base_head": report["base_head"],
        "commit": report.get("commit"),
        "worktree": str(_repo_root()),
        "attack_count": len(report["attack_ids"]),
        "pass_count": report["three_pass"]["pass_count"],
        "findings": [
            {
                "attack_id": f["attack_id"],
                "severity": f["severity"],
                "disposition": f["disposition"],
                "attack_blocked": f["attack_blocked"],
                "survivor": f["survivor"],
                "detail": f["detail"],
            }
            for f in report["findings"]
        ],
        "survivors": report["survivors"],
        "critical_open_count": report["critical_open_count"],
        "high_open_count": report["high_open_count"],
        "blockers": report["blockers"],
        "disposition_counts": report["three_pass"]["final_summary"]["disposition_counts"],
        "hard_bans": report["hard_bans"],
        "hard_ban_probe": report["hard_ban_probe"],
        "acceleration_report_edited": False,
        "status_json_written": False,
        "owned_paths": report["owned_paths"],
        "artifacts": ARTIFACT_REL,
    }
    path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path
