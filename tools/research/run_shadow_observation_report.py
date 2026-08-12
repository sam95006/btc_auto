#!/usr/bin/env python3
"""Read-only shadow observation aggregate CLI.

Does NOT change scoring, ranking, STOP/TARGET/TRAIL, anti-churn, or Demo write.
Writes autonomy/shadow_observation/observation_latest.json under campaign root.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root
from backend.nexus_research_ai_autonomy.shadow_observation_v1 import build_observation_report


def main() -> int:
    ap = argparse.ArgumentParser(description="NEXUS shadow observation report (read-only)")
    ap.add_argument("--campaign-root", type=Path, default=None)
    ap.add_argument("--commit", default=os.environ.get("NEXUS_RUNTIME_COMMIT") or os.environ.get("GIT_COMMIT"))
    args = ap.parse_args()
    croot = args.campaign_root or campaign_root()
    report = build_observation_report(campaign_root=croot, runtime_commit=args.commit)
    # Compact checkpoint for Founder stdout
    print(
        json.dumps(
            {
                "schema": report.get("schema"),
                "signals_created": report.get("signals_created"),
                "signals_matured": report.get("signals_matured"),
                "matured_by_horizon": report.get("matured_by_horizon"),
                "next_checkpoint": report.get("next_checkpoint"),
                "score_calibration": report.get("score_calibration"),
                "edge_calibration": report.get("edge_calibration"),
                "files": report.get("files"),
                "ready_for_demo_reenable": False,
                "path": str(croot / "autonomy" / "shadow_observation" / "observation_latest.json"),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
