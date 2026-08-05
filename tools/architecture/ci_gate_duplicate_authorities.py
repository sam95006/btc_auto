#!/usr/bin/env python3
"""CI gate: fail when newly introduced duplicate authorities appear.

Baseline = known competing claimants recorded in the canonical registry +
optional frozen baseline JSON. Any *unregistered* authority claimant discovered
by the graph builder fails the gate.

Known/accepted competitors do NOT fail (Lane H recommends removal; does not delete).
"""
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
    iter_baseline_claimants,
)
from backend.nexus_contracts.authority_signatures import BASELINE_SCHEMA  # noqa: E402
from tools.architecture import artifact_dir, load_json, write_json  # noqa: E402
from tools.architecture.build_authority_graph import build_graph  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_baseline() -> dict[str, Any]:
    claimants = list(iter_baseline_claimants())
    keys = sorted({f"{c['domain']}::{c['module']}" for c in claimants})
    return {
        "schema": BASELINE_SCHEMA,
        "generated_at": _utc(),
        "lane": "V11_H_AUTHORITY_CONSOLIDATION",
        "registry": build_canonical_registry()["registry_version"],
        "allowed_claimant_keys": keys,
        "claimants": claimants,
        "policy": {
            "new_unregistered_claimant": "FAIL",
            "known_competitor": "ALLOW_WITH_RECOMMENDATION",
            "mass_delete": "BANNED",
        },
    }


def evaluate_gate(root: Path, baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    base = baseline or build_baseline()
    allowed = set(base["allowed_claimant_keys"])
    graph = build_graph(root, include_extended=True)

    violations: list[dict[str, Any]] = []
    allowed_hits: list[dict[str, Any]] = []

    for domain, info in graph["competing_authorities"].items():
        canon = info.get("canonical_module")
        if canon:
            key = f"{domain}::{canon}"
            if key not in allowed:
                # Canonical missing from baseline is itself a registry bug
                violations.append(
                    {
                        "code": "CANONICAL_NOT_IN_BASELINE",
                        "domain": domain,
                        "module": canon,
                        "severity": "critical",
                    }
                )
        for item in info.get("non_canonical_claimants", []):
            mod = item["module"]
            key = f"{domain}::{mod}"
            entry = {
                "domain": domain,
                "module": mod,
                "classification": item.get("classification"),
                "key": key,
            }
            if key in allowed:
                allowed_hits.append(entry)
            else:
                # Also allow canonical satellites already filtered; unregistered fails
                if item.get("classification") == "unregistered_competitor":
                    violations.append(
                        {
                            "code": "NEW_DUPLICATE_AUTHORITY",
                            "domain": domain,
                            "module": mod,
                            "classification": item.get("classification"),
                            "severity": "critical",
                            "message": (
                                f"Unregistered authority claimant for domain={domain}: {mod}. "
                                "Add to registry as competitor (with recommendation) or remove claim."
                            ),
                        }
                    )
                elif item.get("classification") not in {
                    "compatibility_shim",
                    "parallel_lane",
                    "legacy_product",
                    "fixture_tool",
                    "obsolete_entry",
                    "canonical",
                    "canonical_satellite",
                }:
                    violations.append(
                        {
                            "code": "UNKNOWN_CLASSIFICATION_CLAIMANT",
                            "domain": domain,
                            "module": mod,
                            "classification": item.get("classification"),
                            "severity": "high",
                        }
                    )

    report = {
        "schema": "nexus_duplicate_authority_ci_gate_v1",
        "generated_at": _utc(),
        "lane": "V11_H_AUTHORITY_CONSOLIDATION",
        "passed": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
        "allowed_competitor_hit_count": len(allowed_hits),
        "allowed_competitor_hits": allowed_hits[:100],
        "graph_summary": graph["summary"],
        "baseline_claimant_count": len(allowed),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="CI gate for duplicate authorities")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--baseline", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out_dir or artifact_dir(root)
    out.mkdir(parents=True, exist_ok=True)

    baseline_path = args.baseline or (out / "duplicate_authority_baseline.json")
    if args.write_baseline or not baseline_path.exists():
        baseline = build_baseline()
        write_json(baseline_path, baseline)
    else:
        baseline = load_json(baseline_path)

    report = evaluate_gate(root, baseline=baseline)
    write_json(out / "duplicate_authority_ci_gate.json", report)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "violation_count": report["violation_count"],
                "violations": report["violations"],
                "domains_with_duplicates": report["graph_summary"]["domains_with_duplicates"],
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
