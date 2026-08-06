#!/usr/bin/env python3
"""Run PUB18-C Founder Live Operations gate. No report/archive rebuild."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_pub18_founder_live_ops.hard_bans import run_gate  # noqa: E402


def main() -> int:
    result = run_gate(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
