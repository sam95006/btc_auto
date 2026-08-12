#!/usr/bin/env python3
"""CI fail-closed scanner for production AST mutation depth (R4 remediation).

Exit non-zero when production_ast_survivor_count != 0 or required detect-kills miss.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")


def main() -> int:
    from backend.nexus_autonomy.security_mutation_v11.constants import (
        PRODUCTION_AST_REQUIRED_DETECT_KILLS,
        WRAPPER_ONLY_PASS_FORBIDDEN,
    )
    from backend.nexus_autonomy.security_mutation_v11.production_ast import (
        run_production_ast_mutation,
    )

    report = run_production_ast_mutation(root=ROOT)
    out = {
        "mutation_kind": report.get("mutation_kind"),
        "wrapper_only_pass_forbidden": WRAPPER_ONLY_PASS_FORBIDDEN,
        "production_ast_survivor_count": report.get("production_ast_survivor_count"),
        "production_ast_killed_count": report.get("killed_count"),
        "equivalent_count": report.get("equivalent_count"),
        "error_count": report.get("error_count"),
        "mutant_total": report.get("mutant_total"),
        "required_detect_kills": list(PRODUCTION_AST_REQUIRED_DETECT_KILLS),
        "required_detect_kills_missing": report.get("required_detect_kills_missing"),
        "required_detect_kills_ok": report.get("required_detect_kills_ok"),
        "survivor_ids": report.get("survivor_ids"),
        "kill_table": [
            {
                "mutant_id": r.get("mutant_id"),
                "status": r.get("status"),
                "detail": (r.get("oracle") or {}).get("detail"),
            }
            for r in (report.get("results") or [])
        ],
        "exchange_write_attempt_count": report.get("exchange_write_attempt_count"),
        "mainnet_client_created_count": report.get("mainnet_client_created_count"),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

    if int(report.get("exchange_write_attempt_count") or 0) != 0:
        return 3
    if int(report.get("mainnet_client_created_count") or 0) != 0:
        return 5
    if int(report.get("error_count") or 0) != 0:
        return 2
    survivor_count = report.get("production_ast_survivor_count")
    if survivor_count is None or int(survivor_count) != 0:
        return 6
    if not report.get("required_detect_kills_ok"):
        return 7
    if int(report.get("mutant_total") or 0) <= 0:
        return 8
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
