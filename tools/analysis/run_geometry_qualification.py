#!/usr/bin/env python3
"""Offline Structural Geometry qualification runner (diagnostic / WF / OOS framework)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.nexus_demo_execution.geometry_qualification_pipeline import (  # noqa: E402
    run_qualification_pipeline,
)
from backend.nexus_demo_execution.structural_geometry_qualify import (  # noqa: E402
    synthesize_structure_candidates,
)

OUT = Path("artifacts/geometry_qualification")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = run_qualification_pipeline(synthesize_structure_candidates(2407))
    (OUT / "qualification_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    ab = report.get("diagnostic_ab") or {}
    stages = report.get("stages") or {}
    md = [
        "# Structural Geometry Qualification",
        "",
        f"- recommendation: `{report.get('recommendation')}`",
        f"- qualification_complete: `{report.get('qualification_complete')}`",
        f"- fixed_geometry_pass_rate: `{ab.get('fixed_geometry_pass_rate')}`",
        f"- structural_geometry_pass_rate: `{ab.get('structural_geometry_pass_rate')}`",
        f"- REPLAY: `{stages.get('REPLAY_VALIDATED', {}).get('status')}`",
        f"- WALK_FORWARD: `{stages.get('WALK_FORWARD_VALIDATED', {}).get('status')}`",
        f"- OOS: `{stages.get('OOS_VALIDATED', {}).get('status')}`",
        f"- RISK: `{stages.get('RISK_REVIEWED', {}).get('status')}`",
        f"- SHADOW: `{stages.get('SHADOW_APPLIED', {}).get('status')}`",
        "",
        "Diagnostic only for the 2407 A/B replay. OOS success is not claimed from the same sample.",
        "Active execution policy remains unchanged until Founder arms a canary.",
        "",
    ]
    (OUT / "qualification_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("recommendation", "qualification_complete")}, indent=2))
    print(json.dumps({k: ab.get(k) for k in ("fixed_geometry_pass_rate", "structural_geometry_pass_rate")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
