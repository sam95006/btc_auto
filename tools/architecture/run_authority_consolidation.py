#!/usr/bin/env python3
"""Run full Lane H authority consolidation pipeline (two-pass capable)."""
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

from tools.architecture import artifact_dir, write_json  # noqa: E402
from tools.architecture.build_authority_graph import build_graph, main as build_main  # noqa: E402
from tools.architecture.check_contract_drift import run_drift_checks  # noqa: E402
from tools.architecture.ci_gate_duplicate_authorities import (  # noqa: E402
    build_baseline,
    evaluate_gate,
)
from tools.architecture.recommend_removals import build_recommendations  # noqa: E402
from backend.nexus_contracts.authority_registry import build_canonical_registry  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_pass(root: Path, out: Path, pass_id: str) -> dict[str, Any]:
    registry = build_canonical_registry()
    write_json(out / "canonical_authority_registry.json", registry)

    graph = build_graph(root, include_extended=True)
    write_json(out / "authority_graph.json", graph)

    drift = run_drift_checks(root)
    write_json(out / "contract_drift_report.json", drift)

    baseline = build_baseline()
    write_json(out / "duplicate_authority_baseline.json", baseline)
    gate = evaluate_gate(root, baseline=baseline)
    write_json(out / "duplicate_authority_ci_gate.json", gate)

    removals = build_recommendations()
    write_json(out / "removal_recommendations.json", removals)

    blockers = list(drift.get("blockers") or [])
    for v in gate.get("violations") or []:
        blockers.append({"source": "ci_gate", **v})

    # Contested domains without a scoped adapter are consolidation blockers.
    # Checkpoint resolved in V11.1 C4 via canonical envelope + adapters
    # (status active_compat_present) — only emit MULTI_SCOPE_AUTHORITY when still contested.
    for domain in registry["summary"]["contested_domains"]:
        if domain == "lifecycle":
            blockers.append(
                {
                    "source": "scope_contention",
                    "domain": domain,
                    "severity": "critical",
                    "code": "MULTI_SCOPE_AUTHORITY",
                    "message": (
                        f"Domain {domain} has multiple legitimate scoped authorities; "
                        "requires explicit adapter contracts before deletion waves."
                    ),
                }
            )
        elif domain == "checkpoint":
            blockers.append(
                {
                    "source": "scope_contention",
                    "domain": domain,
                    "severity": "critical",
                    "code": "MULTI_SCOPE_AUTHORITY_CHECKPOINT",
                    "message": (
                        "Domain checkpoint remains contested; canonical envelope + "
                        "adapters required before deletion waves."
                    ),
                }
            )

    ckpt = (registry.get("by_domain") or {}).get("checkpoint") or {}
    if ckpt.get("status") == "active_compat_present" and ckpt.get("canonical_module", "").endswith(
        "nexus_checkpoint.store"
    ):
        # Explicit resolution evidence for Lane H / C4.
        pass

    summary = {
        "schema": "nexus_authority_consolidation_pass_v1",
        "pass_id": pass_id,
        "generated_at": _utc(),
        "lane": "V11_H_AUTHORITY_CONSOLIDATION",
        "graph_summary": graph["summary"],
        "drift_severity_counts": drift.get("severity_counts"),
        "ci_gate_passed": gate.get("passed"),
        "ci_gate_violations": gate.get("violations"),
        "critical_findings": graph.get("critical_findings"),
        "removal_queues": {
            k: len(v) for k, v in removals.get("queues", {}).items()
        },
        "blockers": blockers,
        "blocker_count": len(blockers),
    }
    write_json(out / f"{pass_id}_audit.json", summary)
    return summary


def write_human_summary(out: Path, pass1: dict[str, Any], pass2: dict[str, Any]) -> None:
    lines = [
        "# Authority Consolidation V1 — Lane H Summary",
        "",
        f"Generated: {_utc()}",
        "",
        "## Graph summary",
        "",
        f"- Domains with duplicates: `{pass2['graph_summary']['domains_with_duplicates']}`",
        f"- Authority claims: {pass2['graph_summary']['claim_count']}",
        f"- Circular SCC count: {pass2['graph_summary']['circular_scc_count']}",
        f"- Critical graph findings: {pass2['graph_summary']['critical_finding_count']}",
        "",
        "## Critical findings",
        "",
    ]
    for f in pass2.get("critical_findings") or []:
        lines.append(f"- **{f.get('kind')}**: {json.dumps(f, ensure_ascii=False)[:300]}")
    lines.extend(
        [
            "",
            "## Blockers",
            "",
        ]
    )
    for b in pass2.get("blockers") or []:
        lines.append(
            f"- [{b.get('severity', '?')}] `{b.get('code')}` "
            f"domain={b.get('domain')} — {b.get('message') or b.get('recommendation') or b}"
        )
    lines.extend(
        [
            "",
            "## Pass delta",
            "",
            f"- Pass1 blockers: {pass1.get('blocker_count')}",
            f"- Pass2 blockers: {pass2.get('blocker_count')}",
            f"- CI gate passed: {pass2.get('ci_gate_passed')}",
            "",
            "## Policy",
            "",
            "- No mass-delete of compatibility modules.",
            "- No merge/deploy from this lane.",
            "- Removals are recommendations only.",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(
        out / "BLOCKERS.json",
        {
            "generated_at": _utc(),
            "blocker_count": pass2.get("blocker_count"),
            "blockers": pass2.get("blockers"),
            "ci_gate_passed": pass2.get("ci_gate_passed"),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Authority consolidation two-pass runner")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out_dir or artifact_dir(root)
    out.mkdir(parents=True, exist_ok=True)

    pass1 = run_pass(root, out, "pass1")
    pass2 = pass1
    if args.passes >= 2:
        # Pass 2: re-scan after registry/artifacts materialized; refine blockers list uniqueness
        pass2 = run_pass(root, out, "pass2")
        # Deduplicate blockers by code+domain+module
        seen: set[tuple[Any, ...]] = set()
        uniq = []
        for b in pass2.get("blockers") or []:
            key = (b.get("code"), b.get("domain"), b.get("module"), b.get("source"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(b)
        pass2["blockers"] = uniq
        pass2["blocker_count"] = len(uniq)
        write_json(out / "pass2_audit.json", pass2)

    write_human_summary(out, pass1, pass2)
    print(
        json.dumps(
            {
                "out_dir": str(out),
                "pass1_blockers": pass1.get("blocker_count"),
                "pass2_blockers": pass2.get("blocker_count"),
                "ci_gate_passed": pass2.get("ci_gate_passed"),
                "domains_with_duplicates": pass2["graph_summary"]["domains_with_duplicates"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
