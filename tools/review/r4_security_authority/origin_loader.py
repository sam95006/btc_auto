"""Load Lane G/H origin artifacts and source without mutating those trees."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.review.r4_security_authority.constants import (
    DEFAULT_ORIGIN_G,
    DEFAULT_ORIGIN_H,
    ORIGIN_G_BRANCH,
    ORIGIN_H_BRANCH,
)


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def resolve_origin_roots(
    origin_g: str | Path | None = None,
    origin_h: str | Path | None = None,
) -> dict[str, Path]:
    g = Path(origin_g or DEFAULT_ORIGIN_G)
    h = Path(origin_h or DEFAULT_ORIGIN_H)
    return {"g": g, "h": h}


def load_lane_g_summary(origin_g: Path) -> dict[str, Any]:
    base = origin_g / "artifacts/readiness/immutable/v11_security_mutation_redteam"
    findings = _load_json(base / "findings_summary.json") or {}
    status = _load_json(base / "security_mutation_redteam_status.json") or {}
    matrix = _load_json(base / "mutation_matrix.json") or {}
    return {
        "origin_root": str(origin_g),
        "branch": ORIGIN_G_BRANCH,
        "findings_summary": findings,
        "status_present": bool(status),
        "mutation_matrix_present": bool(matrix),
        "passed": bool(findings.get("passed")),
        "recommendation": findings.get("recommendation"),
        "mutation_killed_count": findings.get("mutation_killed_count"),
        "mutation_survivor_count": findings.get("mutation_survivor_count"),
        "high_findings": list(findings.get("high_findings") or []),
        "critical_findings": list(findings.get("critical_findings") or []),
        "owned_paths": list(findings.get("owned_paths") or []),
    }


def load_lane_h_summary(origin_h: Path) -> dict[str, Any]:
    base = origin_h / "artifacts/readiness/immutable/authority_consolidation_v1"
    blockers = _load_json(base / "BLOCKERS.json") or {}
    gate = _load_json(base / "duplicate_authority_ci_gate.json") or {}
    registry = _load_json(base / "canonical_authority_registry.json") or {}
    graph = _load_json(base / "authority_graph.json") or {}
    pass2 = _load_json(base / "pass2_audit.json") or {}
    summary_md = ""
    sm = base / "SUMMARY.md"
    if sm.is_file():
        try:
            summary_md = sm.read_text(encoding="utf-8")[:4000]
        except OSError:
            summary_md = ""
    sccs = list(graph.get("circular_import_sccs") or [])
    return {
        "origin_root": str(origin_h),
        "branch": ORIGIN_H_BRANCH,
        "blockers": blockers,
        "ci_gate_passed": bool(gate.get("passed", blockers.get("ci_gate_passed"))),
        "blocker_count": int(blockers.get("blocker_count") or len(blockers.get("blockers") or [])),
        "critical_blockers": [
            b for b in (blockers.get("blockers") or []) if str(b.get("severity")).lower() == "critical"
        ],
        "circular_scc_count": int(
            (graph.get("summary") or {}).get("circular_scc_count")
            or (pass2.get("graph_summary") or {}).get("circular_scc_count")
            or len(sccs)
        ),
        "circular_import_sccs": sccs,
        "registry_version": registry.get("registry_version"),
        "domains": list((registry.get("domains") or registry.get("authorities") or [])),
        "graph_summary": graph.get("summary") or pass2.get("graph_summary") or {},
        "summary_excerpt": summary_md,
        "artifacts_present": all(
            (base / name).is_file()
            for name in (
                "BLOCKERS.json",
                "duplicate_authority_ci_gate.json",
                "canonical_authority_registry.json",
                "authority_graph.json",
            )
        ),
    }


def read_origin_source(origin_root: Path, rel: str) -> str | None:
    path = origin_root / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None
