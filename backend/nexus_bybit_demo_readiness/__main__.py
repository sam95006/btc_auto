"""CLI: python -m backend.nexus_bybit_demo_readiness

Founder-only Demo readiness evaluation. NEVER executes orders.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.nexus_bybit_demo_readiness.gate_v1 import evaluate_demo_readiness, write_evidence


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="nexus_bybit_demo_readiness")
    p.add_argument("--shadow-24h-complete", action="store_true", default=False)
    p.add_argument("--shadow-lifecycle-complete", action="store_true", default=False)
    p.add_argument("--founder-approval", action="store_true", default=False)
    p.add_argument(
        "--evidence-out",
        type=Path,
        default=None,
        help="Optional evidence JSON path",
    )
    # Explicit hard deny of arming
    p.add_argument("--arm-demo-orders", action="store_true", default=False, help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    if args.arm_demo_orders:
        print(
            json.dumps(
                {
                    "error": "demo_order_arming_forbidden_this_round",
                    "demo_order_armed": False,
                    "autonomous_demo_order_allowed": False,
                },
                indent=2,
            )
        )
        return 3

    out = evaluate_demo_readiness(
        shadow_24h_complete=bool(args.shadow_24h_complete),
        shadow_lifecycle_complete=bool(args.shadow_lifecycle_complete),
        founder_approval=bool(args.founder_approval),
    )
    # Force safety zeros regardless of flags.
    out["demo_order_armed"] = False
    out["autonomous_demo_order_allowed"] = False
    out["autonomous_demo_ready"] = False
    if out.get("status") == "DEMO_AUTONOMOUS_STRATEGY_READY":
        out["status"] = "DEMO_NOT_READY"

    if args.evidence_out:
        write_evidence(out, Path(args.evidence_out))

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
