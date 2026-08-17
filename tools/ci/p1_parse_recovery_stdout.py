#!/usr/bin/env python3
"""Emit a diagnostic-only allowlist from untrusted recovery command stdout."""
from __future__ import annotations

import sys

from p1_zeabur_transport import parse_runner_stdout_diagnostic


def main() -> int:
    diagnostic = parse_runner_stdout_diagnostic(sys.stdin.read())
    for key in (
        "runner_json_detected",
        "runner_verdict",
        "runner_error",
        "runner_run2_order_count_found",
        "runner_run2_position_count_found",
        "runner_unresolved_ledger_count",
    ):
        if key in diagnostic:
            print(f"{key}={diagnostic[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
