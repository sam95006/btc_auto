#!/usr/bin/env python3
"""Parse sanitized Run #8 accounting-recovery JSON. Never uses the Run #2 schema."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from p1_zeabur_transport import parse_run8_accounting_recovery_evidence, parse_run8_bootstrap_failure_evidence


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    bootstrap = "--bootstrap" in args
    raw = sys.stdin.read()
    try:
        payload = (
            parse_run8_bootstrap_failure_evidence(raw)
            if bootstrap
            else parse_run8_accounting_recovery_evidence(raw)
        )
    except ValueError as exc:
        print("recovery_json_detected=false")
        print(f"recovery_evidence_error={exc}")
        return 2
    forbidden = ("postgres://", "postgresql://", "BYBIT_DEMO_API_KEY", "BYBIT_DEMO_API_SECRET")
    text = json.dumps(payload, default=str)
    if any(marker in text for marker in forbidden):
        print("recovery_json_detected=false")
        print("recovery_json_secret_leak_blocked=true")
        return 2
    root = Path("artifacts/bybit_demo_p1")
    root.mkdir(parents=True, exist_ok=True)
    name = "p1_run8_bootstrap_failure.json" if bootstrap else "p1_run8_accounting_recovery_evidence.json"
    (root / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for key in (
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS",
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY",
        "recovery_stage",
        "exception_type",
        "candidate_count",
        "create_order_calls",
        "exchange_write_call_count",
        "error",
    ):
        if key in payload:
            print(f"{key}={payload.get(key)}")
    print("recovery_json_detected=true")
    if bootstrap:
        return 1
    return 0 if payload.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
