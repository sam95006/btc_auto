"""CLI entry: python -m backend.nexus_live_shadow_runtime"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from backend.nexus_live_shadow_runtime.conductor import ConductorConfig, LiveShadowRuntimeConductor
from backend.nexus_live_shadow_runtime.constants import (
    DEFAULT_MAX_CYCLES,
    DEFAULT_MAX_SECONDS,
    DEFAULT_RUNTIME_ROOT,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nexus_live_shadow_runtime",
        description="Bounded Live Shadow Runtime Conductor (read-only; no exchange writes)",
    )
    p.add_argument(
        "--runtime-root",
        type=Path,
        default=Path(os.environ.get("NEXUS_LIVE_SHADOW_RUNTIME_ROOT") or DEFAULT_RUNTIME_ROOT),
    )
    p.add_argument("--max-cycles", type=int, default=DEFAULT_MAX_CYCLES)
    p.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS)
    p.add_argument("--cycle-sleep-sec", type=float, default=1.0)
    p.add_argument("--live", action="store_true", default=True)
    p.add_argument("--no-live", action="store_true", help="Force fixtures-only adapters (tests)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Ensure backend imports resolve when launched as OS process.
    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    live = not bool(args.no_live)
    cfg = ConductorConfig(
        runtime_root=Path(args.runtime_root),
        max_cycles=int(args.max_cycles),
        max_seconds=float(args.max_seconds),
        cycle_sleep_sec=float(args.cycle_sleep_sec),
        live=live,
    )
    if not live:
        os.environ["NEXUS_ALLOW_NON_RUNTIME_ROOT"] = os.environ.get(
            "NEXUS_ALLOW_NON_RUNTIME_ROOT", "1"
        )
    snap = LiveShadowRuntimeConductor(cfg).run()
    print(json.dumps(snap, indent=2, ensure_ascii=False, default=str))
    state = str(snap.get("runtime_state") or "")
    if state == "FAILED_SAFE" and int((snap.get("metrics") or {}).get("runtime_cycles_completed") or 0) == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
