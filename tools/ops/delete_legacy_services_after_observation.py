#!/usr/bin/env python3
"""Delete legacy Zeabur services only after observation PASS ??default dry_run=true.

Never prints secrets. Never deletes Validation keep-service.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KEEP_DEFAULT = "6a82a79aa21454a2cf6b0015"
STAGE3_DEFAULT = "6a3b81652fdef84a45a2a553"
CP_DEFAULT = "6a6bf638ffb4fc697c8a7b1f"


def load_report(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def _int_field(report: dict[str, Any], key: str, default: int = -1) -> int:
    if key not in report or report.get(key) is None:
        return default
    return int(report[key])


def gates_pass(report: dict[str, Any], *, strict: bool) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if report.get("operational_observation_pass") is not True:
        problems.append("operational_observation_pass!=true")
    if _int_field(report, "hidden_dependency_count") != 0:
        problems.append("hidden_dependency_count!=0")
    if _int_field(report, "active_running_service_count") != 1:
        problems.append("active_running_service_count!=1")
    if _int_field(report, "exchange_write_call_count") != 0:
        problems.append("exchange_write_call_count!=0")
    if strict and report.get("mainnet") is True:
        problems.append("mainnet")
    if strict and report.get("real_money") is True:
        problems.append("real_money")
    return len(problems) == 0, problems


def backup_metadata(*, stage3: str, control_plane: str, keep: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "retired_at_planned": now,
        "services": [
            {
                "service_name": "nexus-stage3-bybit-demo-learning",
                "service_id": stage3,
                "domain": "https://nexus-stage3-bybit-demo-learning.zeabur.app",
                "service_role": "legacy_market_ui",
                "retirement_reason": "single_service_consolidation",
                "replacement_service": "nexus-bybit-demo-learning-validation",
            },
            {
                "service_name": "nexus-unified-control-plane",
                "service_id": control_plane,
                "domain": "https://nexus-unified-control-plane.zeabur.app",
                "service_role": "temporary_federation_ui",
                "retirement_reason": "control_plane_internalized",
                "replacement_service": "nexus-bybit-demo-learning-validation",
            },
        ],
        "keep_service_id": keep,
        "keep_service_name": "nexus-bybit-demo-learning-validation",
        "secrets_backed_up": False,
        "note": "Non-secret metadata only; no API keys/tokens/signatures",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--observation-report", required=True)
    p.add_argument("--stage3-service-id", default=STAGE3_DEFAULT)
    p.add_argument("--control-plane-service-id", default=CP_DEFAULT)
    p.add_argument("--keep-service-id", default=KEEP_DEFAULT)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--execute", action="store_true", help="Requires FOUNDER_DELETE_APPROVAL_TOKEN")
    p.add_argument("--out", default="artifacts/legacy_delete_dry_run.json")
    args = p.parse_args()

    if args.keep_service_id in {args.stage3_service_id, args.control_plane_service_id}:
        print("refusing: keep service id collides with delete targets", file=sys.stderr)
        return 2

    report = load_report(args.observation_report)
    ok, problems = gates_pass(report, strict=args.strict)
    backup = backup_metadata(
        stage3=args.stage3_service_id,
        control_plane=args.control_plane_service_id,
        keep=args.keep_service_id,
    )
    result = {
        "dry_run": not args.execute,
        "gates_pass": ok,
        "problems": problems,
        "backup": backup,
        "deleted": [],
        "execute_attempted": False,
    }

    if args.execute:
        token = (os.environ.get("FOUNDER_DELETE_APPROVAL_TOKEN") or "").strip()
        if not token:
            result["problems"].append("missing_FOUNDER_DELETE_APPROVAL_TOKEN")
            ok = False
        if not ok:
            result["dry_run"] = True
        else:
            # Intentionally not calling Zeabur delete in readiness until observation PASS.
            result["execute_attempted"] = True
            result["note"] = "Execute path reserved; use only after observation PASS + Founder token"
            result["deleted"] = []

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"gates_pass": result["gates_pass"], "dry_run": result["dry_run"], "problems": result["problems"], "out": args.out}, ensure_ascii=True, indent=2))
    return 0 if result["dry_run"] else (0 if result.get("deleted") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
