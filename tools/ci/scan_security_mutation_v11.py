#!/usr/bin/env python3
"""CI scanner: fail closed on V11 Security Mutation Red Team violations + secret scan.

Requires production AST mutation depth (wrapper-only PASS forbidden).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

OWNED_GLOBS = [
    "backend/nexus_autonomy/security_mutation_v11",
    "tools/research/run_security_mutation_redteam_v11.py",
    "tools/ci/scan_security_mutation_v11.py",
    "tools/ci/scan_production_ast_mutation_v11.py",
    "tests/test_security_mutation_redteam_v11.py",
    "tests/test_production_ast_mutation_v11.py",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)api[_-]?secret\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r'(?i)"api[_-]?key"\s*:\s*"[A-Za-z0-9_\-]{20,}"'),
    re.compile(r"(?i)BYBIT_(?:DEMO_)?API_(?:KEY|SECRET)\s*=\s*[^\s'\"]{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile("BEGIN" + " PRIVATE KEY"),
]


def _iter_owned_files() -> list[Path]:
    files: list[Path] = []
    for rel in OWNED_GLOBS:
        path = ROOT / rel
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return files


def scan_owned_secrets() -> list[str]:
    hits: list[str] = []
    for path in _iter_owned_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                hits.append(str(path.relative_to(ROOT)).replace("\\", "/"))
                break
    return hits


def main() -> int:
    from backend.nexus_autonomy.security_mutation_v11.constants import PASS_RECOMMENDATION
    from backend.nexus_autonomy.security_mutation_v11.redteam import (
        evaluate_security_mutation_redteam,
        write_immutable_artifacts,
        write_remediation_artifacts,
    )

    secret_hits = scan_owned_secrets()
    # TWO-PASS
    pass1 = evaluate_security_mutation_redteam(root=ROOT)
    pass2 = evaluate_security_mutation_redteam(root=ROOT)
    status = pass2
    write_immutable_artifacts(root=ROOT, status=status)
    write_remediation_artifacts(root=ROOT, status=status, pass1=pass1, pass2=pass2)

    report = {
        "recommendation": status.get("recommendation"),
        "passed": status.get("passed"),
        "mutation_killed_count": status.get("mutation_killed_count"),
        "mutation_survivor_count": status.get("mutation_survivor_count"),
        "mutation_unresolved_blocker_count": status.get("mutation_unresolved_blocker_count"),
        "scenario_pass_count": status.get("scenario_pass_count"),
        "scenario_total_count": status.get("scenario_total_count"),
        "production_ast_survivor_count": status.get("production_ast_survivor_count"),
        "production_ast_killed_count": status.get("production_ast_killed_count"),
        "wrapper_only_pass_forbidden": status.get("wrapper_only_pass_forbidden"),
        "h_gate_pass_is_not_authority_remediation": status.get(
            "h_gate_pass_is_not_authority_remediation"
        ),
        "two_pass_deterministic": (
            pass1.get("recommendation") == pass2.get("recommendation")
            and pass1.get("production_ast_survivor_count")
            == pass2.get("production_ast_survivor_count")
        ),
        "exchange_write_attempt_count": status.get("exchange_write_attempt_count"),
        "secret_leak_count": len(secret_hits) + int(status.get("secret_leak_count") or 0),
        "mainnet_client_created_count": status.get("mainnet_client_created_count"),
        "owned_file_secret_hits": secret_hits,
        "critical_findings": status.get("critical_findings"),
        "high_findings": status.get("high_findings"),
        "unresolved_blockers": status.get("unresolved_blockers"),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if secret_hits:
        return 4
    if int(status.get("secret_leak_count") or 0) != 0:
        return 4
    if int(status.get("exchange_write_attempt_count") or 0) != 0:
        return 3
    if int(status.get("mainnet_client_created_count") or 0) != 0:
        return 5
    survivor_count = status.get("production_ast_survivor_count")
    if survivor_count is None or int(survivor_count) != 0:
        return 6
    if not status.get("wrapper_only_pass_forbidden"):
        return 7
    if not report["two_pass_deterministic"]:
        return 8
    if status.get("recommendation") != PASS_RECOMMENDATION:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
