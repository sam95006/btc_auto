#!/usr/bin/env python3
"""Run #8 specific stdout parser. Never reuse Run #2 recovery stdout parser."""
from __future__ import annotations

import json
import sys


SAFE_KEYS = (
    "runner_json_detected",
    "recovery_stage",
    "exception_type",
    "candidate_count",
    "entry_read_pass",
    "close_read_pass",
    "position_flat",
    "execution_identity_pass",
    "closed_pnl_exact_match",
    "ledger_finalization_pass",
    "create_order_calls",
    "exchange_write_call_count",
)


def parse_run8_stdout(raw: str) -> dict:
    decoder = json.JSONDecoder()
    payload: dict | None = None
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and (
            "recovery_stage" in candidate or "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS" in candidate
        ):
            payload = candidate
    if payload is None:
        return {"runner_json_detected": False}
    out = {"runner_json_detected": True}
    for key in SAFE_KEYS[1:]:
        out[key] = payload.get(key)
    return out


def main() -> int:
    parsed = parse_run8_stdout(sys.stdin.read())
    for key, value in parsed.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
