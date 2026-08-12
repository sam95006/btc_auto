#!/usr/bin/env python3
"""Deep consolidation inventory + frozen H3 closure (no OOS download)."""
from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "readiness"
PY_PKG = "backend.nexus_demo_execution"

# Seeds for frozen OOS policy runtime
FROZEN_SEEDS = [
    "backend/nexus_demo_execution/h3_oos_policy_freeze.py",
    "backend/nexus_demo_execution/edge_research_v3.py",
    "backend/nexus_demo_execution/edge_research_v3_hypotheses.py",
    "backend/nexus_demo_execution/market_event_sim.py",
    "backend/nexus_demo_execution/risk_sizing.py",
    "backend/nexus_demo_execution/historical_market_data.py",
    "backend/nexus_demo_execution/microstructure_history.py",
    "backend/nexus_demo_execution/session_limits.py",
    "backend/nexus_demo_execution/cost_entry_gate.py",
    "backend/nexus_demo_execution/trade_geometry.py",
    "artifacts/readiness/policies/H3E_OOS_POLICY_V1_FROZEN.json",
    "artifacts/readiness/policies/H3D_OOS_POLICY_V1_FROZEN.json",
    "artifacts/readiness/OOS_H3_UNTOUCHED_V1_RESERVATION.json",
    "tests/test_edge_research_v3.py",
    "tests/test_oos_preflight_cleanup.py",
]


def module_path_from_import(mod: str) -> Path | None:
    if not mod.startswith("backend."):
        return None
    parts = mod.split(".")
    p = ROOT.joinpath(*parts)
    if (p.with_suffix(".py")).is_file():
        return p.with_suffix(".py")
    if (p / "__init__.py").is_file():
        return p / "__init__.py"
    return None


def parse_imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return set()
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def expand_closure(seeds: list[str]) -> set[str]:
    closure: set[str] = set()
    queue = [ROOT / s for s in seeds]
    seen: set[Path] = set()
    while queue:
        p = queue.pop()
        if p in seen or not p.exists():
            continue
        seen.add(p)
        rel = p.relative_to(ROOT).as_posix()
        closure.add(rel)
        if p.suffix != ".py":
            continue
        for mod in parse_imports(p):
            mp = module_path_from_import(mod)
            if mp and mp not in seen:
                queue.append(mp)
            # relative imports within package
            if mod.startswith("backend.nexus_demo_execution"):
                continue
    # also add session_limits / cost gate files referenced by name in seeds already
    return closure


def count_refs(needle: str, roots: list[str]) -> int:
    n = 0
    pat = re.compile(re.escape(needle))
    for r in roots:
        base = ROOT / r
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in {".py", ".yml", ".yaml", ".md", ".json", ".toml", ".ts", ".tsx", ".js"}:
                continue
            try:
                t = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if pat.search(t):
                n += 1
    return n


def main() -> None:
    closure = expand_closure(FROZEN_SEEDS)
    # Explicitly include cost-related modules if imported by name strings
    extra = [
        "backend/nexus_demo_execution/cost_entry_gate.py",
        "backend/nexus_demo_execution/v2_policy.py",
        "backend/nexus_demo_execution/instrument_qty_classify.py",
    ]
    for e in extra:
        if (ROOT / e).exists():
            closure |= expand_closure([e])

    (OUT / "FROZEN_OOS_POLICY_CLOSURE.json").write_text(
        json.dumps(
            {
                "classification": "FROZEN_OOS_POLICY_CLOSURE",
                "seed_count": len(FROZEN_SEEDS),
                "closure_count": len(closure),
                "paths": sorted(closure),
                "mutation_forbidden": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"closure_count": len(closure), "sample": sorted(closure)[:40]}, indent=2))


if __name__ == "__main__":
    main()
