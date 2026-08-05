#!/usr/bin/env python3
"""Run V16-C Probabilistic Regime Engine V2 three-pass campaign (stdout only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_probabilistic_regime_v2.adversarial import (  # noqa: E402
    run_adversarial_review,
    run_independent_break_attempts,
)
from backend.nexus_probabilistic_regime_v2.engine import run_engine_campaign  # noqa: E402


def main() -> int:
    p1 = run_engine_campaign(pass_id=1)
    p2 = run_adversarial_review()
    p3 = run_independent_break_attempts()
    summary = {
        "lane": "V16-C",
        "pass_1_scenarios": p1["scenario_count"],
        "pass_1_hard_bans_refused": p1["hard_ban_matrix"]["all_refused"],
        "pass_2_all_pass": p2["all_pass"],
        "pass_2_passed": p2["passed_count"],
        "pass_3_all_pass": p3["all_pass"],
        "pass_3_passed": p3["passed_count"],
        "status_json_written": False,
        "ok": bool(
            p1["hard_ban_matrix"]["all_refused"] and p2["all_pass"] and p3["all_pass"]
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
