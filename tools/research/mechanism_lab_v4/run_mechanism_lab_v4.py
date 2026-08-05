#!/usr/bin/env python3
"""Runner for V14-C Strategy Mechanism Lab V4.

Synthetic development fixtures only. No OOS, formal WF, Demo, qualification, or auto-integrate.
TWO PASSES required.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_mechanism_lab_v4 import (  # noqa: E402
    build_status_payload,
    run_adversarial_review,
    run_mechanism_lab,
    write_immutable_artifacts,
    write_runtime_status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="V14-C Strategy Mechanism Lab V4")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runtime-root", type=Path, default=Path(r"D:\NEXUS_RUNTIME"))
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    # TWO PASSES
    report_p1 = run_mechanism_lab(pass_id=1)
    adv_p1 = run_adversarial_review(report_p1, pass_name="pass_1")

    report_p2 = run_mechanism_lab(pass_id=2)
    adv_p2 = run_adversarial_review(report_p2, pass_name="pass_2")

    # Prefer pass-2 report for immutable artifacts (final).
    report = report_p2
    adversarial_passes = [adv_p1, adv_p2]
    summary = build_status_payload(report, adversarial_passes, root=args.root)

    artifacts: dict[str, str] = {}
    if not args.no_write_artifacts:
        paths = write_immutable_artifacts(report, adversarial_passes, root=args.root)
        artifacts = {k: str(v) for k, v in paths.items()}
        runtime_path = write_runtime_status(summary, runtime_root=args.runtime_root)
        artifacts["runtime_status"] = str(runtime_path)

    out = {
        "schema": summary["schema"],
        "status": summary["status"],
        "pass": summary["pass"],
        "pass_1_ok": summary["pass_1_ok"],
        "pass_2_ok": summary["pass_2_ok"],
        "mechanism_count": summary["mechanism_count"],
        "mechanism_family_count": summary["mechanism_family_count"],
        "qualification_ready_count": summary["qualification_ready_count"],
        "edge_claim_count": summary["edge_claim_count"],
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "auto_integrate": False,
        "adversarial_remaining_count": summary["adversarial_remaining_count"],
        "artifacts": artifacts,
        "lane_head": summary["lane_head"],
    }
    print(json.dumps(out, indent=2))
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
