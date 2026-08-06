#!/usr/bin/env python3
"""Run PUB17-A Global Market Source Contracts gate. No *_status.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_pub17_global_market_contracts.hard_bans import run_gate  # noqa: E402
from backend.nexus_pub17_global_market_contracts.registry import (  # noqa: E402
    write_catalog_artifact,
    write_schema_artifact,
)


def main() -> int:
    write_schema_artifact(ROOT)
    write_catalog_artifact(ROOT, retrieved_at="2026-08-06T00:00:00Z")
    result = run_gate(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
