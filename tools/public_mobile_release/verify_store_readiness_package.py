#!/usr/bin/env python3
"""Verify PUB-L non-submission store readiness package (two passes)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.public_mobile_release.two_pass import run_two_passes  # noqa: E402


def main() -> int:
    results = run_two_passes(ROOT)
    failed = False
    print("PUB_L_STORE_READINESS_VERIFY")
    print(f"root={ROOT}")
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"{result.name}={status} findings={len(result.findings)}")
        for f in result.findings:
            print(f"  FAIL {f.code} @ {f.path} :: {f.detail}")
            failed = True
    if failed:
        print("OVERALL=FAIL")
        return 1
    print("OVERALL=PASS")
    print("submission_authorized=false")
    print("legal_approval_claimed=false")
    print("store_submission_attempt_count=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
