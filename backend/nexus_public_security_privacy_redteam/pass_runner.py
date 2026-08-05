"""Three-pass runner for PUB2-H public security & privacy red team."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_public_security_privacy_redteam.attacks import run_all_attacks
from backend.nexus_public_security_privacy_redteam.constants import (
    ATTACK_IDS,
    BASE_COMMIT,
    BRANCH,
    DISPOSITION_SURVIVOR,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    SCHEMA,
)
from backend.nexus_public_security_privacy_redteam.hard_bans import (
    assert_env_hard_bans,
    env_hard_ban_guard,
    scan_no_status_json,
    scan_owned_imports,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_disp: dict[str, list[str]] = {}
    for f in findings:
        by_disp.setdefault(f["disposition"], []).append(f["attack_id"])
    survivors = [f for f in findings if f["disposition"] == DISPOSITION_SURVIVOR]
    return {
        "finding_count": len(findings),
        "by_disposition": {k: sorted(v) for k, v in by_disp.items()},
        "survivors": [f["attack_id"] for f in survivors],
        "survivor_count": len(survivors),
        "all_resolved": len(survivors) == 0 and len(findings) == len(ATTACK_IDS),
    }


def run_pass(pass_id: int, root: Path | None = None) -> dict[str, Any]:
    """
    Pass 1 — implementation verification (attacks must resolve).
    Pass 2 — adversarial re-run after remediation assumptions.
    Pass 3 — independent break attempts (same probes, fail-closed).
    """
    if pass_id not in (1, 2, 3):
        raise ValueError("pass_id must be 1, 2, or 3")
    root = root or _repo_root()
    assert_env_hard_bans()
    env = env_hard_ban_guard()
    imports = scan_owned_imports(root)
    status_scan = scan_no_status_json(root)
    findings = run_all_attacks()
    summary = _summarize(findings)
    ok = (
        env["ok"]
        and imports["ok"]
        and status_scan["ok"]
        and summary["all_resolved"]
        and all(f["ok"] for f in findings)
    )
    return {
        "pass_id": pass_id,
        "ok": ok,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "schema": SCHEMA,
        "package": PACKAGE,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "hard_bans": sorted(HARD_BANS),
        "env": env,
        "imports": imports,
        "status_scan": status_scan,
        "findings": findings,
        "summary": summary,
        "blockers": summary["survivors"],
    }


def run_three_passes(root: Path | None = None) -> dict[str, Any]:
    root = root or _repo_root()
    passes = [run_pass(i, root) for i in (1, 2, 3)]
    ok = all(p["ok"] for p in passes)
    # Aggregate unique survivors across passes (should be empty).
    survivors: list[str] = []
    for p in passes:
        for sid in p["summary"]["survivors"]:
            if sid not in survivors:
                survivors.append(sid)
    findings_flat = passes[0]["findings"] if passes else []
    return {
        "ok": ok,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "package": PACKAGE,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "pass_count": 3,
        "passes": passes,
        "findings": findings_flat,
        "survivors": survivors,
        "blockers": survivors,
        "hard_bans": sorted(HARD_BANS),
        "attack_ids": list(ATTACK_IDS),
        "status": "PASS" if ok else "FAIL",
    }
