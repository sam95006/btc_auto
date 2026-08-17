#!/usr/bin/env python3
"""Emit a diagnostic-only allowlist from untrusted P1 migration stdout."""
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


def parse_migration_stdout(raw: str) -> dict[str, Any]:
    payload = _json_object(raw)
    if payload is None:
        match = _TRACEBACK_EXCEPTION.search(raw)
        diagnostic: dict[str, Any] = {"migration_runner_json_detected": False}
        if match:
            diagnostic["migration_exception_type"] = match.group(1)
        return diagnostic

    pre = payload.get("pre_migration") if isinstance(payload.get("pre_migration"), dict) else {}
    apply = payload.get("apply") if isinstance(payload.get("apply"), dict) else {}
    post = payload.get("post_migration") if isinstance(payload.get("post_migration"), dict) else {}
    error = str(payload.get("error") or "").replace("\n", " ")[:160]
    if any(token in error.lower() for token in ("postgres", "password", "secret", "token", "dsn")):
        error = "redacted"
    return {
        "migration_runner_json_detected": True,
        "migration_runner_verdict": bool(payload.get("P1_MIGRATION_0006_APPLIED_PASS")),
        "migration_runner_error": error or None,
        "migration_pre_applied_versions": pre.get("applied_versions"),
        "migration_pre_pending_versions": pre.get("pending_versions"),
        "migration_checksum_drift": pre.get("checksum_drift"),
        "migration_apply_exit_code": apply.get("exit_code"),
        "migration_apply_ok": apply.get("ok"),
        "migration_apply_versions": apply.get("applied"),
        "migration_post_applied_versions": post.get("applied_versions"),
        "migration_missing_columns": post.get("missing_columns"),
        "migration_parent_index_present": post.get("parent_index_present"),
    }


def main() -> int:
    diagnostic = parse_migration_stdout(sys.stdin.read())
    for key, value in diagnostic.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
