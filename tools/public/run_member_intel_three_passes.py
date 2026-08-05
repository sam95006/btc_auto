#!/usr/bin/env python3
"""Run UX-B Member Web Intelligence Experience three passes. No *_status.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_public_member_intel.hard_bans import run_three_passes  # noqa: E402


def main() -> int:
    result = run_three_passes(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
