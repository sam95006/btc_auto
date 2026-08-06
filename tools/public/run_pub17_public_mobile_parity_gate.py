#!/usr/bin/env python3
"""CLI gate: public/mobile contract parity (V17 deep)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_pub17_public_mobile_parity.gate import run_parity_gate  # noqa: E402


def main() -> int:
    result = run_parity_gate(ROOT)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
