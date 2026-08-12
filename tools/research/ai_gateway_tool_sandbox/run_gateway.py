#!/usr/bin/env python3
"""Run V18-E AI Gateway fixture campaign and emit evidence JSON."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.nexus_ai_gateway_tool_sandbox.constants import (  # noqa: E402
    ALLOWED_TOOLS,
    BANNED_TOOLS,
    BASE_COMMIT,
    BRANCH,
    CAMPAIGN_ID,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PROVIDER_IDS,
    SCHEMA,
)
from backend.nexus_ai_gateway_tool_sandbox.fixtures import (  # noqa: E402
    fixture_catalog,
    run_fixture,
)
from backend.nexus_ai_gateway_tool_sandbox.hard_bans import (  # noqa: E402
    hard_ban_probe_matrix,
)


def _git_head() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
        return out
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_campaign() -> dict[str, Any]:
    results = {}
    busy_loop_total = 0
    provider_statuses: dict[str, Any] = {}
    all_ok = True
    for name in fixture_catalog():
        out = run_fixture(name)
        results[name] = out
        busy_loop_total += int(out.get("busy_loop_count") or 0)
        provider_statuses = out.get("provider_statuses") or provider_statuses
        first = out["first"]
        spec = out["spec"]
        if "expect_status" in spec and first["result_status"] != spec["expect_status"]:
            all_ok = False
            results[name]["pass"] = False
        elif "expect_provider" in spec and first["provider_id"] != spec["expect_provider"]:
            all_ok = False
            results[name]["pass"] = False
        elif "expect_pipeline" in spec and first["pipeline"] != spec["expect_pipeline"]:
            all_ok = False
            results[name]["pass"] = False
        elif "expect_decision" in spec and first["decision"] != spec["expect_decision"]:
            all_ok = False
            results[name]["pass"] = False
        elif spec.get("expect_second_cache_hit") and not (
            out.get("second") or {}
        ).get("cache_hit"):
            all_ok = False
            results[name]["pass"] = False
        else:
            results[name]["pass"] = True

    bans = hard_ban_probe_matrix()
    if not bans.get("all_banned_denied"):
        all_ok = False

    return {
        "schema": SCHEMA,
        "generated_at": _utc_now(),
        "status": "PASS" if all_ok and busy_loop_total == 0 else "FAIL",
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base": BASE_COMMIT,
        "commit": _git_head(),
        "worktree": str(REPO_ROOT),
        "campaign_id": CAMPAIGN_ID,
        "providers": list(PROVIDER_IDS),
        "provider_statuses": provider_statuses,
        "allowed_tools": sorted(ALLOWED_TOOLS),
        "banned_tools": sorted(BANNED_TOOLS),
        "busy_loop_count": busy_loop_total,
        "fixtures": results,
        "hard_bans": bans,
        "hard_ban_flags": sorted(HARD_BANS),
        "owned_paths": list(OWNED_PATHS),
        "deliverables": [
            "typed_gateway",
            "adapter_abstraction",
            "fallback",
            "timeout",
            "budget_policy",
            "request_dedupe",
            "cache",
            "audit",
            "tool_allow_list",
            "deterministic_fixtures",
        ],
        "capacity_contract": {
            "status": "PROVIDER_CAPACITY_BLOCKED",
            "pipeline": "CONTINUE_WITHOUT_AI",
            "decision": ["WAIT", "ABSTAIN"],
        },
        "report_edited": False,
        "exchange_write": False,
        "mainnet": False,
        "on_demand_usd": 0,
        "pr26": False,
        "pr27": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V18-E AI Gateway campaign")
    parser.add_argument(
        "--evidence",
        default="",
        help="Optional path to write evidence JSON",
    )
    args = parser.parse_args()
    evidence = run_campaign()
    text = json.dumps(evidence, indent=2, sort_keys=True)
    print(text)
    if args.evidence:
        path = Path(args.evidence)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
