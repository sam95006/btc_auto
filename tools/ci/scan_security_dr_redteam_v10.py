#!/usr/bin/env python3
"""CI scanner: fail closed on V10 Security & DR Red Team violations + secret scan."""
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

OWNED_FILES = [
    "backend/nexus_autonomy/security_dr_redteam_v10.py",
    "backend/nexus_autonomy/security_dr_scenarios_v10.py",
    "tools/research/run_security_dr_redteam_v10.py",
    "tools/ci/scan_security_dr_redteam_v10.py",
    "tests/test_security_dr_redteam_v10.py",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)api[_-]?secret\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_(?:DEMO_)?API_(?:KEY|SECRET)\s*=\s*[^\s'\"]{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile("BEGIN" + " PRIVATE KEY"),
]


def scan_owned_secrets() -> list[str]:
    hits: list[str] = []
    for rel in OWNED_FILES:
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                hits.append(rel)
                break
    return hits


def main() -> int:
    from backend.nexus_autonomy.security_dr_redteam_v10 import (
        PASS_RECOMMENDATION,
        evaluate_security_dr_redteam,
        write_immutable_artifacts,
    )

    secret_hits = scan_owned_secrets()
    status = evaluate_security_dr_redteam(root=ROOT)
    write_immutable_artifacts(root=ROOT, status=status)

    report = {
        "recommendation": status.get("recommendation"),
        "passed": status.get("passed"),
        "scenario_pass_count": status.get("scenario_pass_count"),
        "scenario_total_count": status.get("scenario_total_count"),
        "exchange_write_attempt_count": status.get("exchange_write_attempt_count"),
        "secret_leak_count": len(secret_hits) + int(status.get("secret_leak_count") or 0),
        "mainnet_client_created_count": status.get("mainnet_client_created_count"),
        "owned_file_secret_hits": secret_hits,
        "critical_findings": status.get("critical_findings"),
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
    if status.get("recommendation") != PASS_RECOMMENDATION:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
