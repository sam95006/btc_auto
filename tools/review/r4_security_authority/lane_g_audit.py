"""Audit Lane G mutation depth — wrapper-level vs production AST."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from tools.review.r4_security_authority.origin_loader import (
    load_lane_g_summary,
    read_origin_source,
)


WRAPPER_MARKERS = (
    "in-memory",
    "in_memory",
    "weakened subjects",
    "without editing foreign-owned",
    "Mutations never edit foreign-owned source files",
)


def audit_lane_g_mutation_depth(origin_g: Path) -> dict[str, Any]:
    summary = load_lane_g_summary(origin_g)
    mutations_src = read_origin_source(
        origin_g, "backend/nexus_autonomy/security_mutation_v11/mutations.py"
    ) or ""
    subjects_src = read_origin_source(
        origin_g, "backend/nexus_autonomy/security_mutation_v11/subjects.py"
    ) or ""
    residuals_src = read_origin_source(
        origin_g, "backend/nexus_autonomy/security_mutation_v11/residuals.py"
    ) or ""

    wrapper_signals = [
        m for m in WRAPPER_MARKERS if m.lower() in (mutations_src + subjects_src + residuals_src).lower()
        or m in (mutations_src + subjects_src + residuals_src)
    ]

    # Does G apply AST edits to production modules?
    uses_ast_unparse = "ast.unparse" in mutations_src or "ast.parse" in mutations_src
    writes_production = bool(
        re.search(
            r"write_text\(|open\([^)]*[\"']w",
            mutations_src,
        )
    )
    production_paths_mentioned = bool(
        re.search(
            r"security_persistence_v1|security_credential_boundary_v1|security_write_traps_v1",
            mutations_src,
        )
    )

    high = list(summary.get("high_findings") or [])
    self_acknowledged_wrapper = any(
        h.get("code") == "mutation_surface_is_in_memory_wrappers" for h in high
    )

    # Count mutant functions in mutations.py
    mutant_fn_count = 0
    if mutations_src:
        try:
            tree = ast.parse(mutations_src)
            mutant_fn_count = sum(
                1
                for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name.startswith("mutant_")
            )
        except SyntaxError:
            mutant_fn_count = len(re.findall(r"^def\s+mutant_", mutations_src, re.M))

    depth = "wrapper_in_memory"
    if uses_ast_unparse and writes_production:
        depth = "production_ast"
    elif uses_ast_unparse:
        depth = "ast_without_production_write"

    finding = None
    if depth == "wrapper_in_memory":
        finding = {
            "severity": "critical",
            "code": "G_MUTATION_DEPTH_WRAPPER_ONLY",
            "detail": (
                "Lane G kill-suite mutates in-memory subject wrappers only; it does not "
                "AST-mutate production Private Core security modules. A PASS with "
                f"mutation_survivor_count={summary.get('mutation_survivor_count')} does not "
                "prove production-module mutant detection. R4 runs independent production AST "
                "mutation to close this gap for review evidence."
            ),
            "self_acknowledged_as_high": self_acknowledged_wrapper,
            "wrapper_signals": wrapper_signals,
            "mutant_fn_count": mutant_fn_count,
            "fail_closed": True,
        }

    return {
        "schema": "v11_r4_lane_g_depth_audit_v1",
        "origin_present": bool(summary.get("findings_summary")),
        "lane_g_passed": summary.get("passed"),
        "lane_g_recommendation": summary.get("recommendation"),
        "mutation_killed_count": summary.get("mutation_killed_count"),
        "mutation_survivor_count": summary.get("mutation_survivor_count"),
        "mutation_depth": depth,
        "uses_ast_unparse": uses_ast_unparse,
        "writes_production_sources": writes_production,
        "production_paths_mentioned_in_mutations": production_paths_mentioned,
        "wrapper_signals": wrapper_signals,
        "self_acknowledged_wrapper_high": self_acknowledged_wrapper,
        "mutant_fn_count": mutant_fn_count,
        "lane_g_high_findings": high,
        "finding": finding,
    }
