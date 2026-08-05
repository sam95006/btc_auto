#!/usr/bin/env python3
"""Run PUB-B Decision Cloud hard-ban passes (two passes). No *_status.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_public_decision_cloud.hard_bans import run_two_passes  # noqa: E402


def main() -> int:
    result = run_two_passes(ROOT)
    # stdout only — Founder directive: no *_status.json
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
