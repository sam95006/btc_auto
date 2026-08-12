#!/usr/bin/env python3
"""Run NEXUS Private Core Security Boundary V1 audit and write immutable status."""
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
    from backend.nexus_autonomy.security_boundary_v1 import run_boundary

    status = run_boundary(write_artifact=True, root=ROOT)
    print(json.dumps(
        {
            "recommendation": status.get("recommendation"),
            "exchange_write_attempt_count": status.get("exchange_write_attempt_count"),
            "secret_leak_count": status.get("secret_leak_count"),
            "unresolved_critical_count": (status.get("findings") or {}).get("unresolved_critical_count"),
            "audit": status.get("audit"),
            "violations": status.get("violations"),
        },
        indent=2,
        ensure_ascii=False,
    ))
    rec = status.get("recommendation")
    return 0 if rec == "NEXUS_PRIVATE_SECURITY_BOUNDARY_V1_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
