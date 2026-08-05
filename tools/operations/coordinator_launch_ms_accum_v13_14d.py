#!/usr/bin/env python3
"""LOCAL COORDINATOR ONLY — launch ms_accum_v13_integrity_14d (public readonly).

Hard bans: no trading credentials, no exchange writes, no Event Study, no PR27 merge.
Requires: V13 ops preflight PASS, D free >= 100 GiB, hard campaign cap <= 40 GiB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(r"D:\NEXUS_RUNTIME")
CAMPAIGN_ID = "ms_accum_v13_integrity_14d"
GIB = 1024**3
FLOOR = 100 * GIB
HARD_CAP = 40 * GIB
SOFT_CAP = int(HARD_CAP * 0.8)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorize", action="store_true", help="Coordinator authorization flag")
    parser.add_argument("--segment-hours", type=float, default=24.0)
    parser.add_argument("--symbol-count", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    os.environ["NEXUS_MS_CAMPAIGN_ID"] = CAMPAIGN_ID
    sys.path.insert(0, str(ROOT))

    if not args.authorize:
        print(json.dumps({"error": "missing_--authorize", "live_capture_started": False}))
        return 2

    from backend.nexus_microstructure.ops_v13.campaign_design import build_campaign_design
    from backend.nexus_microstructure.ops_v13.controller import MicrostructureOperationsControllerV13
    from backend.nexus_microstructure.ops_v13.synthetic_harness import run_all_preflight_scenarios

    work = ROOT / ".nexus_runtime" / "microstructure" / "ops_v13_coord_launch"
    ctrl = MicrostructureOperationsControllerV13(ROOT, work_root=work, disk_root="D:\\")
    ops = ctrl.run_both_passes()
    design = build_campaign_design()
    free = shutil.disk_usage("D:/").free
    floor_ok = free >= FLOOR
    synth = run_all_preflight_scenarios(ROOT / ".nexus_runtime" / "microstructure" / "preflight_v13")
    synth_ok = bool(synth.get("all_passed"))
    ops_ok = bool(ops.get("all_passed"))

    gate = {
        "ops_both_passes_ok": ops_ok,
        "synthetic_preflight_ok": synth_ok,
        "free_gib": round(free / GIB, 2),
        "floor_ok": floor_ok,
        "hard_cap_gib": HARD_CAP // GIB,
        "symbol_count": args.symbol_count,
        "design_symbol_count": design["symbol_count"],
        "exchange_write_attempt_count": 0,
    }
    if not (ops_ok and synth_ok and floor_ok and int(design["symbol_count"]) >= 25):
        print(json.dumps({"error": "preflight_or_disk_failed", "gate": gate, "synth": synth}, indent=2))
        return 3

    if args.dry_run:
        print(json.dumps({"dry_run": True, "gate": gate, "would_start": True}, indent=2))
        return 0

    from backend.nexus_microstructure.accumulation_campaign_v1 import AccumulationCampaignRegistry

    reg_path = ROOT / ".nexus_runtime/microstructure/campaigns/registry.json"
    reg = AccumulationCampaignRegistry(reg_path)
    if CAMPAIGN_ID not in (reg.data.get("campaigns") or {}):
        reg.start_campaign(
            CAMPAIGN_ID,
            symbol_count=max(25, int(args.symbol_count)),
            hard_storage_cap_bytes=HARD_CAP,
            soft_storage_cap_bytes=SOFT_CAP,
            duration_hours=24,
            families=["AGGRESSIVE_TRADE_FLOW", "LIQUIDATION_EVENTS"],
            target_calendar_days=14,
            writer_note="collector_v12_streaming_with_v13_ops_gates",
        )
    else:
        camp = reg.data["campaigns"][CAMPAIGN_ID]
        camp["config"] = {
            **(camp.get("config") or {}),
            "symbol_count": max(25, int(args.symbol_count)),
            "hard_storage_cap_bytes": HARD_CAP,
            "soft_storage_cap_bytes": SOFT_CAP,
        }
        reg.save()

    start_utc = _utc()
    cmd = [
        sys.executable,
        str(ROOT / "tools/research/run_microstructure_accumulation_campaign_v1.py"),
    ]
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "EXCHANGE_WRITE": "false",
            "MAINNET": "false",
            "REAL_MONEY": "false",
            "NEXUS_MS_CAMPAIGN_ID": CAMPAIGN_ID,
            "NEXUS_MS_SEGMENT_HOURS": str(args.segment_hours),
            "NEXUS_MS_START_24H_ACCUMULATION": "1",
        }
    )

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]

    out_log = RUNTIME / "ms_accum_v13_integrity_14d_stdout.log"
    err_log = RUNTIME / "ms_accum_v13_integrity_14d_stderr.log"
    fout = open(out_log, "a", encoding="utf-8")
    ferr = open(err_log, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=fout,
        stderr=ferr,
        creationflags=creationflags,
        close_fds=True,
    )
    time.sleep(3.0)
    alive = proc.poll() is None
    universe_checksum = hashlib.sha256(
        json.dumps(design.get("symbols") or [], separators=(",", ":")).encode()
    ).hexdigest()

    payload = {
        "schema": "coordinator_ms_accum_v13_integrity_14d_launch",
        "campaign_id": CAMPAIGN_ID,
        "live_capture_started": bool(alive),
        "capture_start_UTC": start_utc,
        "capture_start_local": datetime.now().astimezone().isoformat(),
        "capture_PID": proc.pid,
        "parent_PID": os.getpid(),
        "symbol_count": max(25, int(args.symbol_count)),
        "universe_checksum": universe_checksum,
        "free_space_at_start_gib": round(free / GIB, 2),
        "storage_cap_gib": HARD_CAP // GIB,
        "free_space_floor_gib": FLOOR // GIB,
        "event_study_readiness": "NOT_READY",
        "exchange_write_attempt_count": 0,
        "trading_credentials_loaded": False,
        "gate": gate,
        "stdout_log": str(out_log),
        "stderr_log": str(err_log),
        "worktree": str(ROOT),
        "V13_INTEGRATED_HEAD": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "note": "Public-readonly Bybit WS via collector_v12 segment runner; Coordinator-authorized.",
    }
    log_path = RUNTIME / "ms_accum_v13_integrity_14d_launch.json"
    log_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    RUNTIME.joinpath("v13_a_microstructure_14d_status.json").write_text(
        json.dumps(
            {
                **payload,
                "lane": "V13-A",
                "coordinator_launch": True,
                "updated_at": _utc(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0 if alive else 4


if __name__ == "__main__":
    raise SystemExit(main())
