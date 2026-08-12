#!/usr/bin/env python3
"""V30.1 unified deploy: classify /data cleanup (dry-run by default).

Does NOT delete open position lifecycle state.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


KEEP_GLOBS = [
    "campaigns/research_v18_2_30/autonomy/research_pnl_position.json",
    "campaigns/research_v18_2_30/autonomy/scheduler_state.json",
    "campaigns/research_v18_2_30/autonomy/service_heartbeat.json",
    "campaigns/research_v18_2_30/autonomy/ai_provider_health.json",
    "campaigns/research_v18_2_30/autonomy/founder_demo_monitor_live.json",
    "campaigns/research_v18_2_30/checkpoints/**",
    "evidence_coordinator/founder_demo_monitor_live.json",
    "evidence_coordinator/unified_runtime_health.json",
    "evidence_coordinator/v18_2_29_core.json",
    "evidence_coordinator/v18_2_30_core.json",
    "evidence_coordinator/v18_2_30_1_core.json",
]

RETIRE_NAME_HINTS = (
    "LOCAL_SIM",
    "dry_replay",
    "tmp_",
    ".write_probe",
    "obsolete",
    "legacy_execution",
    "shadow_tmp",
)


def classify(root: Path, *, position_open: bool) -> dict[str, Any]:
    kept: list[str] = []
    delete: list[str] = []
    if not root.exists():
        return {"kept": [], "deleted": [], "reason": "data_root_missing", "dry_run": True}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        if position_open and "research_pnl_position" in rel:
            kept.append(rel)
            continue
        if any(h.lower() in rel.lower() for h in RETIRE_NAME_HINTS):
            delete.append(rel)
            continue
        if "campaigns/research_v18_2_30" in rel or "evidence_coordinator" in rel:
            kept.append(rel)
        elif rel.endswith(".tmp") or "/tmp/" in rel or rel.startswith("tmp"):
            delete.append(rel)
        else:
            # unknown — keep by default (do not blindly delete accounting)
            kept.append(rel)
    return {
        "schema": "v18_2_30_1_data_cleanup_manifest_v1",
        "at": _utc(),
        "data_root": str(root),
        "position_open": position_open,
        "kept": kept[:200],
        "deleted": delete[:200],
        "reason": "retire_stale_temp_only; preserve V29/V30 accounting + open position",
        "dry_run": True,
        "applied": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=os.environ.get("NEXUS_DATA_ROOT", "/data"))
    ap.add_argument("--position-open", action="store_true")
    ap.add_argument("--apply", action="store_true", help="Actually delete classified retire files")
    args = ap.parse_args()
    root = Path(args.data_root)
    man = classify(root, position_open=bool(args.position_open))
    if args.apply and not args.position_open:
        deleted = []
        for rel in list(man["deleted"]):
            p = root / rel
            try:
                if p.is_file():
                    p.unlink()
                    deleted.append(rel)
            except OSError:
                pass
        man["deleted"] = deleted
        man["applied"] = True
        man["dry_run"] = False
    elif args.apply and args.position_open:
        man["applied"] = False
        man["reason"] = "refused_apply_while_position_open"
    print(json.dumps(man, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
