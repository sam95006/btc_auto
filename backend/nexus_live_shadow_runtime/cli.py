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
        description="Live Shadow Runtime Conductor (+ V18.2 24h qualification campaign)",
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

    # V18.2 Phase C — 24h qualification campaign
    p.add_argument(
        "--campaign",
        choices=["24h"],
        default=None,
        help="Enable NEXUS_SHADOW_24H_QUALIFICATION_CAMPAIGN mode",
    )
    p.add_argument(
        "--mode",
        choices=["preflight", "run", "launch", "resume-review"],
        default="launch",
        help="Campaign mode (default launch=preflight+detached daemon)",
    )
    p.add_argument("--campaign-id", type=str, default=None)
    p.add_argument(
        "--campaigns-root",
        type=Path,
        default=Path(os.environ.get("NEXUS_CAMPAIGNS_ROOT") or r"D:\NEXUS_RUNTIME\campaigns"),
    )
    p.add_argument("--target-duration-hours", type=float, default=24.0)
    p.add_argument("--checkpoint-interval-sec", type=float, default=3600.0)
    return p


def _campaign_main(args: argparse.Namespace) -> int:
    from backend.nexus_live_shadow_runtime.campaign import (
        CampaignConfig,
        Shadow24hQualificationCampaign,
        launch_detached,
        make_campaign_id,
    )

    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    cid = args.campaign_id or os.environ.get("NEXUS_SHADOW_CAMPAIGN_ID") or make_campaign_id()
    live = not bool(args.no_live)
    cfg = CampaignConfig(
        campaign_id=cid,
        campaigns_root=Path(args.campaigns_root),
        target_duration_hours=float(args.target_duration_hours),
        checkpoint_interval_sec=float(args.checkpoint_interval_sec),
        cycle_sleep_sec=float(args.cycle_sleep_sec if args.cycle_sleep_sec != 1.0 else 60.0),
        live=live,
    )
    if not live:
        os.environ["NEXUS_ALLOW_NON_RUNTIME_ROOT"] = os.environ.get(
            "NEXUS_ALLOW_NON_RUNTIME_ROOT", "1"
        )

    mode = str(args.mode or "launch")
    if mode == "preflight":
        out = Shadow24hQualificationCampaign(cfg).preflight()
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return 0 if out.get("passed") else 2
    if mode == "run":
        out = Shadow24hQualificationCampaign(cfg).run()
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return 0 if out.get("campaign_state") not in {"FAILED_SAFE"} else 2
    if mode == "resume-review":
        out = Shadow24hQualificationCampaign(cfg).resume_review()
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return 0
    # launch (default): preflight + detached Start-Process
    out = launch_detached(repo_root=repo, config=cfg)
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out.get("live_started") else 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Ensure backend imports resolve when launched as OS process.
    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    if args.campaign == "24h":
        return _campaign_main(args)

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
