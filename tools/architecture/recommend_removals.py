#!/usr/bin/env python3
"""Emit future-removal recommendations without deleting any modules."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_contracts.authority_registry import (  # noqa: E402
    build_canonical_registry,
    list_authorities,
)
from backend.nexus_contracts.authority_signatures import REMOVAL_SCHEMA  # noqa: E402
from tools.architecture import artifact_dir, write_json  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


PRIORITY = {
    "future_remove": 1,
    "migrate_callers": 2,
    "quarantine": 3,
    "retain_compat": 4,
}


def build_recommendations() -> dict[str, Any]:
    registry = build_canonical_registry()
    items: list[dict[str, Any]] = []
    for rec in list_authorities():
        for c in rec.competitors:
            items.append(
                {
                    "domain": rec.domain,
                    "authority_id": rec.authority_id,
                    "module": c.module,
                    "symbol": c.symbol,
                    "role": c.role,
                    "severity": c.severity,
                    "recommended_action": c.recommended_action,
                    "delete_now": False,  # hard ban
                    "notes": c.notes,
                    "preconditions": _preconditions(c.recommended_action, rec.domain),
                }
            )
    items.sort(
        key=lambda x: (
            PRIORITY.get(x["recommended_action"], 99),
            {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}.get(
                x["severity"], 9
            ),
            x["domain"],
            x["module"],
        )
    )
    return {
        "schema": REMOVAL_SCHEMA,
        "generated_at": _utc(),
        "lane": "V11_H_AUTHORITY_CONSOLIDATION",
        "registry_version": registry["registry_version"],
        "policy": {
            "mass_delete_compatibility_modules": "BANNED",
            "delete_now_allowed": False,
            "phase": "recommend_only",
        },
        "recommendation_count": len(items),
        "recommendations": items,
        "queues": {
            "future_remove": [i for i in items if i["recommended_action"] == "future_remove"],
            "migrate_callers": [i for i in items if i["recommended_action"] == "migrate_callers"],
            "quarantine": [i for i in items if i["recommended_action"] == "quarantine"],
            "retain_compat": [i for i in items if i["recommended_action"] == "retain_compat"],
        },
    }


def _preconditions(action: str, domain: str) -> list[str]:
    if action == "future_remove":
        return [
            f"All Private Core callers for domain={domain} route through canonical authority",
            "CI gate remains green after caller migration",
            "Readiness artifacts regenerated without referencing removed module",
            "Founder approval for deletion wave",
        ]
    if action == "migrate_callers":
        return [
            f"Inventory imports of competitor for domain={domain}",
            "Replace with canonical module imports",
            "Keep competitor as thin re-export shim until delete wave",
        ]
    if action == "quarantine":
        return [
            "Document lane boundary in AGENTS / ownership contract",
            "Ensure CI import-graph forbids Session traffic into quarantined module",
        ]
    return ["No deletion; periodic re-audit only"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend future authority removals")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    out = args.out_dir or artifact_dir(ROOT)
    report = build_recommendations()
    write_json(out / "removal_recommendations.json", report)
    print(
        json.dumps(
            {
                "recommendation_count": report["recommendation_count"],
                "future_remove": len(report["queues"]["future_remove"]),
                "migrate_callers": len(report["queues"]["migrate_callers"]),
                "quarantine": len(report["queues"]["quarantine"]),
                "retain_compat": len(report["queues"]["retain_compat"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
