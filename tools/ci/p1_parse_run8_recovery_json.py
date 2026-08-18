#!/usr/bin/env python3
"""Extract sanitized Run #8 accounting-recovery JSON from the remote file channel."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from p1_zeabur_transport import parse_recovery_evidence


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = parse_recovery_evidence(raw)
    except ValueError as exc:
        print("recovery_json_detected=false")
        print(f"recovery_evidence_error={exc}")
        return 2
    forbidden = ("postgres://", "postgresql://", "BYBIT_DEMO_API_KEY", "BYBIT_DEMO_API_SECRET")
    text = json.dumps(payload, default=str)
    if any(marker in text for marker in forbidden):
        print("recovery_json_detected=false")
        print("recovery_json_secret_leak_blocked=true")
        return 3
    root = Path("artifacts/bybit_demo_p1")
    root.mkdir(parents=True, exist_ok=True)
    (root / "p1_run8_accounting_recovery_evidence.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    for key in (
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS",
        "P1_EXCHANGE_REALIZED_PNL_PASS",
        "P1_DURABLE_LEDGER_LIFECYCLE_PASS",
        "P1_RUN8_EXACT_CLOSED_PNL_MATCH",
        "P1_RUN8_LEDGER_FINALIZED",
        "P1_RUN8_POSITION_FLAT",
        "recovery_stage",
        "exception_type",
        "candidate_count",
        "entry_read_pass",
        "close_read_pass",
        "position_flat",
        "execution_identity_pass",
        "closed_pnl_exact_match",
        "ledger_finalization_pass",
        "ledger_final_state",
        "create_order_calls",
        "exchange_write_call_count",
        "error",
    ):
        print(f"{key}={payload.get(key)}")
    print("recovery_json_detected=true")
    return 0 if payload.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
