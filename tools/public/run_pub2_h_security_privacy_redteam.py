#!/usr/bin/env python
"""Run PUB2-H three-pass public security & privacy red team (no *_status.json)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_public_security_privacy_redteam import run_three_passes  # noqa: E402


def main() -> int:
    result = run_three_passes(ROOT)
    # stdout only — never write *_status.json / report artifacts.
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
