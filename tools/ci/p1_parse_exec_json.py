#!/usr/bin/env python3
"""Parse sanitized P1 qualification JSON from service-exec output. Never prints secrets."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SECRET_MARKERS = ("api_key", "api_secret", "password", "token", "postgres", "dsn", "DATABASE_URL")


def _load(text: str) -> dict | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS" in payload:
            return payload
    match = re.search(r"\{(?:[^{}]|\{[^{}]*\})*BYBIT_DEMO_SINGLE_TRADE_E2E_PASS(?:[^{}]|\{[^{}]*\})*\}", text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def main() -> int:
    raw = sys.stdin.read()
    for key in ("BYBIT_DEMO_API_KEY", "BYBIT_DEMO_API_SECRET", "NEXUS_STAGING_POSTGRES_URL", "NEXUS_POSTGRES_URL", "DATABASE_URL"):
        value = os.environ.get(key) or ""
        if value:
            raw = raw.replace(value, "[REDACTED]")
    payload = _load(raw)
    if payload is None:
        print("p1_exec_json=unparseable")
        return 2
    text = json.dumps(payload, default=str)
    lowered = text.lower()
    if any(marker in lowered and "pass" not in marker for marker in ("postgresql://", "postgres://")):
        print("p1_exec_json=secret_leak_blocked")
        return 3
    out = Path("artifacts/bybit_demo_p1")
    out.mkdir(parents=True, exist_ok=True)
    (out / "p1_qualification_evidence.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"BYBIT_DEMO_SINGLE_TRADE_E2E_PASS={payload.get('BYBIT_DEMO_SINGLE_TRADE_E2E_PASS')}")
    print(f"AUTONOMOUS_BYBIT_DEMO_ARM_READY={payload.get('AUTONOMOUS_BYBIT_DEMO_ARM_READY')}")
    print(f"P1_PREFLIGHT_PASS={payload.get('P1_PREFLIGHT_PASS')}")
    print(f"P1_ENTRY_RECONCILIATION_PASS={payload.get('P1_ENTRY_RECONCILIATION_PASS')}")
    print(f"P1_CLOSE_RECONCILIATION_PASS={payload.get('P1_CLOSE_RECONCILIATION_PASS')}")
    print(f"P1_EXCHANGE_REALIZED_PNL_PASS={payload.get('P1_EXCHANGE_REALIZED_PNL_PASS')}")
    print(f"P1_DURABLE_LEDGER_LIFECYCLE_PASS={payload.get('P1_DURABLE_LEDGER_LIFECYCLE_PASS')}")
    print(f"create_order_calls={payload.get('create_order_calls')}")
    print(f"symbol={payload.get('symbol')}")
    print(f"side={payload.get('side')}")
    print(f"ledger_final_state={payload.get('ledger_final_state')}")
    print(f"orderLinkId_prefix={payload.get('orderLinkId_prefix')}")
    print(f"orderId_prefix={payload.get('orderId_prefix')}")
    return 0 if payload.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
