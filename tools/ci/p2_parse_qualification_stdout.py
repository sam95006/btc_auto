#!/usr/bin/env python3
"""Allowlisted diagnostic from untrusted P2.1 qualification stdout."""
from __future__ import annotations

import json
import re
import sys
from typing import Any


_TRACEBACK_EXCEPTION = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Exit))(?::|$)", re.MULTILINE)


def _json_object(raw: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    parsed: dict[str, Any] | None = None
    for index, character in enumerate(raw):
        if character != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and parsed is None:
            parsed = candidate
    return parsed


def parse_qualification_stdout(raw: str) -> dict[str, Any]:
    payload = _json_object(raw)
    if payload is None:
        match = _TRACEBACK_EXCEPTION.search(raw)
        diagnostic: dict[str, Any] = {"qualification_json_detected": False}
        if match:
            diagnostic["qualification_exception_type"] = match.group(1)
        return diagnostic
    error = str(payload.get("error") or "").replace("\n", " ")[:160]
    if any(token in error.lower() for token in ("postgres", "password", "secret", "token", "dsn")):
        error = "redacted"
    return {
        "qualification_json_detected": True,
        "P2_1_POSTGRES_QUALIFICATION_PASS": bool(payload.get("P2_1_POSTGRES_QUALIFICATION_PASS")),
        "POSTGRES_LESSON_PERSISTED": payload.get("POSTGRES_LESSON_PERSISTED"),
        "POSTGRES_MEMORY_SURVIVES_NEW_PROCESS": payload.get("POSTGRES_MEMORY_SURVIVES_NEW_PROCESS"),
        "DUPLICATE_LESSON_COUNT": payload.get("DUPLICATE_LESSON_COUNT"),
        "POLICY_TRUTH": payload.get("POLICY_TRUTH"),
        "PROCESS_VALIDATION_STATUS": payload.get("PROCESS_VALIDATION_STATUS"),
        "create_order_calls": payload.get("create_order_calls"),
        "exchange_write_call_count": payload.get("exchange_write_call_count"),
        "error": error or None,
        "source_evidence_hash": payload.get("source_evidence_hash"),
        "trade_id_prefix": payload.get("trade_id_prefix"),
    }


def main() -> int:
    diagnostic = parse_qualification_stdout(sys.stdin.read())
    for key, value in diagnostic.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
