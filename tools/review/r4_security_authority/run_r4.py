#!/usr/bin/env python3
"""CLI: run FOUNDER R4 Security + Authority review (two passes)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.review.r4_security_authority.campaign import run_r4_campaign  # noqa: E402
from tools.review.r4_security_authority.constants import (  # noqa: E402
    DEFAULT_ORIGIN_G,
    DEFAULT_ORIGIN_H,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="R4 Security + Authority review")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--origin-g", type=Path, default=Path(DEFAULT_ORIGIN_G))
    parser.add_argument("--origin-h", type=Path, default=Path(DEFAULT_ORIGIN_H))
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()
    status = run_r4_campaign(
        root=args.root.resolve(),
        origin_g=args.origin_g,
        origin_h=args.origin_h,
        passes=args.passes,
    )
    print(
        json.dumps(
            {
                "recommendation": status["recommendation"],
                "integration_recommendation": status["integration_recommendation"],
                "critical_count": len(status["critical_findings"]),
                "high_count": len(status["high_findings"]),
                "false_PASS_count": status["false_PASS_count"],
                "circular_scc_count": status["circular_scc_count"],
                "production_ast": status["production_ast_mutation_summary"],
                "lane_g_mutation_depth": status["lane_g_mutation_depth"],
            },
            indent=2,
        )
    )
    # Review lane exits 0 even when findings exist (artifacts are the deliverable).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
