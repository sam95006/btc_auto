#!/usr/bin/env python3
"""PUB18 Alert Engine read-only contract gate — three passes + safety counts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_pub18_alert_engine.constants import (  # noqa: E402
    BASE_COMMIT,
    BRANCH,
    FAIL_RECOMMENDATION,
    PASS_RECOMMENDATION,
)
from backend.nexus_pub18_alert_engine.hard_bans import run_three_passes  # noqa: E402


def main() -> int:
    result = run_three_passes(ROOT)
    payload = {
        "lane": "PUB18-ALERT",
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "ok": result["ok"],
        "recommendation": PASS_RECOMMENDATION if result["ok"] else FAIL_RECOMMENDATION,
        "private_field_leak_count": result.get("private_field_leak_count", 1),
        "private_core_import_count": result.get("private_core_import_count", 1),
        "exchange_controls": result.get("exchange_controls", 1),
        "fabricated_live_values": result.get("fabricated_live_values", 1),
        "unavailable_as_zero": result.get("unavailable_as_zero", 1),
        "stale_without_indicator": result.get("stale_without_indicator", 1),
        "member_execution_control_count": result.get("member_execution_control_count", 1),
        "passes": result.get("passes"),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
