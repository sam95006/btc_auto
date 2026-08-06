#!/usr/bin/env python3
"""Runner for V17-H Training Dataset Compiler.

Compiler / schema / deterministic split / contamination guard /
sample fixture / offline benchmark interface only.

MUST NOT run: formal WF, untouched OOS, real promotion, real Lesson activation,
mainnet, real-money. Does NOT write *_status.json. Does NOT edit Founder reports.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_training_dataset_compiler import (  # noqa: E402
    build_summary_payload,
    compile_campaign,
    run_contamination_redteam,
    write_immutable_artifacts,
)


def _git_head(root: Path) -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                stderr=subprocess.DEVNULL,
            )
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return "UNKNOWN"


def main() -> int:
    parser = argparse.ArgumentParser(description="V17-H Training Dataset Compiler")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-write-artifacts", action="store_true")
    args = parser.parse_args()

    # THREE PASSES (deterministic campaign digests must match)
    c1 = compile_campaign(pass_id=1)
    c2 = compile_campaign(pass_id=2)
    c3 = compile_campaign(pass_id=3)
    if not (c1["campaign_digest"] == c2["campaign_digest"] == c3["campaign_digest"]):
        # pass_id is inside digest — compare sample digests instead
        d1 = [s["compile_digest"] for s in c1["samples"]]
        d2 = [s["compile_digest"] for s in c2["samples"]]
        d3 = [s["compile_digest"] for s in c3["samples"]]
        if not (d1 == d2 == d3):
            print(json.dumps({"status": "FAIL", "reason": "non_deterministic_compile"}, indent=2))
            return 2

    redteam = run_contamination_redteam()
    head = _git_head(args.root)
    summary = build_summary_payload(c3, redteam, root=args.root, head=head)

    artifacts: dict[str, str] = {}
    if not args.no_write_artifacts:
        paths = write_immutable_artifacts(c3, redteam, root=args.root, head=head)
        artifacts = {k: str(v) for k, v in paths.items()}
        for p in (
            Path(r"D:\NEXUS_RUNTIME") / "v17_h_status.json",
            args.root / "v17_h_status.json",
        ):
            if p.exists():
                raise RuntimeError(f"status_json_must_not_exist:{p}")

    out = {
        "schema": summary["schema"],
        "status": summary["status"],
        "head": head,
        "sample_count": summary["sample_count"],
        "trainable_count": summary["trainable_count"],
        "reserved_count": summary["reserved_count"],
        "contamination_survivors": redteam["survivor_count"],
        "redteam_status": redteam["status"],
        "attack_count": redteam["attack_count"],
        "formal_walk_forward_executed": False,
        "untouched_oos_executed": False,
        "real_promotion_executed": False,
        "real_lesson_activated": False,
        "mainnet_touched": False,
        "real_money_touched": False,
        "llm_sole_tick_consumer": False,
        "report_updated": False,
        "pr26_merge_attempted": False,
        "pr27_merge_attempted": False,
        "artifacts": artifacts,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" and redteam["survivor_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
