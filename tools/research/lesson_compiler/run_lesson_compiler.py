#!/usr/bin/env python3
"""Runner for V16-E Lesson Compiler.

Development fixtures only. No OOS, formal WF, Demo, ACTIVE lessons, or auto-integrate.
THREE PASSES required. Does NOT write *_status.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_lesson_compiler import (  # noqa: E402
    build_summary_payload,
    run_adversarial_review,
    run_compiler_campaign,
    write_immutable_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="V16-E Lesson Compiler")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    # THREE PASSES
    report_p1 = run_compiler_campaign(pass_id=1)
    adv_p1 = run_adversarial_review(report_p1, pass_name="pass_1")

    report_p2 = run_compiler_campaign(pass_id=2)
    adv_p2 = run_adversarial_review(report_p2, pass_name="pass_2")

    report_p3 = run_compiler_campaign(pass_id=3)
    adv_p3 = run_adversarial_review(report_p3, pass_name="pass_3")

    report = report_p3
    adversarial_passes = [adv_p1, adv_p2, adv_p3]
    summary = build_summary_payload(report, adversarial_passes, root=args.root)

    artifacts: dict[str, str] = {}
    if not args.no_write_artifacts:
        paths = write_immutable_artifacts(report, adversarial_passes, root=args.root)
        artifacts = {k: str(v) for k, v in paths.items()}
        status_candidates = [
            Path(r"D:\NEXUS_RUNTIME") / "v16_e_status.json",
            args.root / "v16_e_status.json",
        ]
        for p in status_candidates:
            if p.exists():
                raise RuntimeError(f"status_json_must_not_exist:{p}")

    out = {
        "schema": summary["schema"],
        "status": summary["status"],
        "pass": summary["pass"],
        "pass_1_ok": summary["pass_1_ok"],
        "pass_2_ok": summary["pass_2_ok"],
        "pass_3_ok": summary["pass_3_ok"],
        "lesson_count": summary["lesson_count"],
        "candidate_lesson_count": summary["candidate_lesson_count"],
        "active_lesson_count": 0,
        "qualification_ready_count": 0,
        "edge_claim_count": 0,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "auto_integrate": False,
        "production_risk_mutated": False,
        "production_leverage_mutated": False,
        "adversarial_remaining_count": summary["adversarial_remaining_count"],
        "critical_remaining": summary["critical_remaining"],
        "high_remaining": summary["high_remaining"],
        "campaign_digest": summary["campaign_digest"],
        "status_json_written": False,
        "artifacts": artifacts,
        "lane_head": summary["lane_head"],
        "blockers": summary["blockers"],
    }
    print(json.dumps(out, indent=2))
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
