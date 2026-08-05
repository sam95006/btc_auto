#!/usr/bin/env python3
"""Founder V15-E Candidate Dossier Builder harness.

Builds development candidate dossiers with full lineage/checksums/versions/
failed siblings/regime/symbol/cost breakdowns. TWO PASSES. Writes immutable
artifacts only — never *_status.json lane reports.

Hard bans: no formal WF/OOS, no select/promote, no QUALIFIED/PROMOTED/DEMO_READY,
no demo/shadow/exchange writes, no auto-integrate, no PR27 merge.
Status ceiling: DEVELOPMENT_REVIEW | DEVELOPMENT_PROMISING_NOT_QUALIFIED.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_candidate_dossier.constants import (  # noqa: E402
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    FORMAL_STATUS_BLOCKED,
    HARD_BANS,
    INFRA_STATUS_BLOCKED_READY,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    SCHEMA_ID,
)
from backend.nexus_candidate_dossier.controller import (  # noqa: E402
    run_two_pass_dossier,
    write_immutable_artifacts,
)

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)gsk_[A-Za-z0-9]{20,}"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def scan_secrets() -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_PATHS:
        target = ROOT / rel
        files: list[Path]
        if target.is_dir():
            files = [
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in {".py", ".json", ".md"}
            ]
        elif target.is_file():
            files = [target]
        else:
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v15_e_candidate_dossier_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": list(OWNED_PATHS),
    }


def run_pytest() -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/candidate_dossier",
        "-q",
        "--tb=line",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return {
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
    }


def assert_no_status_json(artifact_dir: Path) -> None:
    banned = list(artifact_dir.glob("*status*.json"))
    if banned:
        raise RuntimeError(
            "LANE_STATUS_JSON_BANNED:" + ",".join(p.name for p in banned)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="V15-E Candidate Dossier Builder")
    parser.add_argument("--as-of-ms", type=int, default=1_700_000_000_000)
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()

    two_pass = run_two_pass_dossier(as_of_ms=args.as_of_ms)
    artifact_paths = write_immutable_artifacts(two_pass, root=ROOT)
    assert_no_status_json(ROOT / ARTIFACT_REL)

    secrets = scan_secrets()
    secrets_path = ROOT / ARTIFACT_REL / "secret_scan.json"
    secrets_path.write_text(
        json.dumps(secrets, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    pytest_result: dict[str, Any] | None = None
    if not args.skip_pytest:
        pytest_result = run_pytest()

    ok = bool(
        two_pass.get("both_passes_ok")
        and secrets["secret_leak_count"] == 0
        and two_pass.get("lane_status_json_written") is False
        and two_pass.get("qualification_status") == FORMAL_STATUS_BLOCKED
        and two_pass.get("infrastructure_status") == INFRA_STATUS_BLOCKED_READY
        and (pytest_result is None or pytest_result.get("passed"))
    )

    result = {
        "lane": LANE,
        "lane_name": LANE_NAME,
        "schema": SCHEMA_ID,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "head": _git_head(),
        "created_at": _utc(),
        "both_passes_ok": two_pass.get("both_passes_ok"),
        "qualification_status": two_pass.get("qualification_status"),
        "infrastructure_status": two_pass.get("infrastructure_status"),
        "dossier_builder_status": two_pass.get("dossier_builder_status"),
        "qualification_ready_count": 0,
        "lane_status_json_written": False,
        "dossier_count": two_pass["pass1"]["dossiers"]["dossier_count"],
        "status_histogram": two_pass["pass1"]["dossiers"]["status_histogram"],
        "bundle_digest": two_pass["pass1"]["dossiers"]["bundle_digest"],
        "hard_bans": list(HARD_BANS),
        "artifact_paths": {
            k: str(v.relative_to(ROOT)).replace("\\", "/")
            for k, v in artifact_paths.items()
        },
        "secret_leak_count": secrets["secret_leak_count"],
        "pytest": pytest_result,
        "ok": ok,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
