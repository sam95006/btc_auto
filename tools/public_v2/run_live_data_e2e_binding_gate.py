#!/usr/bin/env python3
"""PUB2-B three-pass live data e2e binding gate. Prints JSON to stdout. No *_status.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_public_v2_live_binding.constants import (  # noqa: E402
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    PROGRAM_ID,
)
from backend.nexus_public_v2_live_binding.three_pass import (  # noqa: E402
    run_three_pass_verification,
)


def main() -> int:
    result = run_three_pass_verification(root=ROOT)
    observed = result["observed"]
    payload = {
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "hard_bans": list(HARD_BANS),
        "pass_count": result["pass_count"],
        "three_pass_status": result["three_pass_status"],
        "hardcoded_live_value_count": observed["hardcoded_live_value_count"],
        "fabricated_live_value_count": observed["fabricated_live_value_count"],
        "stale_without_indicator_count": observed["stale_without_indicator_count"],
        "unavailable_shown_as_zero_count": observed["unavailable_shown_as_zero_count"],
        "component_count": result.get("component_count"),
        "counters_match": result["counters_match"],
        "hard_bans_intact": result["hard_ban_passes"]["ok"],
        "status_json_written": False,
        "recommendation": result["recommendation"],
        "three_pass": {
            "pass_1_status": result["pass_1"]["status"],
            "pass_2_status": result["pass_2"]["status"],
            "pass_3_status": result["pass_3"]["status"],
        },
    }
    ok = (
        result["three_pass_status"] == "PASS"
        and payload["hardcoded_live_value_count"] == 0
        and payload["fabricated_live_value_count"] == 0
        and payload["stale_without_indicator_count"] == 0
        and payload["unavailable_shown_as_zero_count"] == 0
    )
    payload["gate_status"] = "PASS" if ok else "FAIL"
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
