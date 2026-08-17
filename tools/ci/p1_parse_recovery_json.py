#!/usr/bin/env python3
"""Extract only sanitized P1 recovery JSON from an explicit remote file channel."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    raw = sys.stdin.read()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        print("recovery_json_detected=false")
        return 2
    try:
        payload = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        print("recovery_json_detected=false")
        return 2
    if not isinstance(payload, dict) or "P1_RUN2_RECOVERY_CLEAR" not in payload:
        print("recovery_json_detected=false")
        return 2
    forbidden = ("postgres://", "postgresql://", "BYBIT_DEMO_API_KEY", "BYBIT_DEMO_API_SECRET")
    text = json.dumps(payload, default=str)
    if any(marker in text for marker in forbidden):
        print("recovery_json_detected=false")
        print("recovery_json_secret_leak_blocked=true")
        return 3
    root = Path("artifacts/bybit_demo_p1")
    root.mkdir(parents=True, exist_ok=True)
    (root / "p1_run2_recovery_evidence.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for key in (
        "P1_RUN2_RECOVERY_CLEAR",
        "run2_order_count_found",
        "run2_position_count_found",
        "p1_unresolved_ledger_count",
        "migration_0005_present",
        "migration_0006_present",
        "error",
    ):
        print(f"{key}={payload.get(key)}")
    print("recovery_json_detected=true")
    return 0 if payload.get("P1_RUN2_RECOVERY_CLEAR") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
