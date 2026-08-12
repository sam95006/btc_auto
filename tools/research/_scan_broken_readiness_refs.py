#!/usr/bin/env python3
"""Scan for broken references to deleted readiness/artifact paths."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ["tests", ".github", "backend", "tools", "config", "docs"]
PAT = re.compile(r"(?:docs/04_readiness/[A-Za-z0-9_./-]+|artifacts/[A-Za-z0-9_./-]+)")
# Paths that are intentionally write destinations (created at runtime)
ALLOW_MISSING_PREFIXES = (
    "artifacts/demo_validation_6h_v2/",
    "artifacts/demo_validation_6h_v2_unattended/",
    "artifacts/demo_validation_12h_v3/",
    "artifacts/demo_validation_502/",
    "artifacts/demo_validation_edge_research_",
    "artifacts/demo_validation_cohort_edge/",
    "artifacts/demo_validation_geometry_market_oos/",
    "artifacts/same_router_probe_wave/",
    "artifacts/single_service_observation/",
    "artifacts/geometry_qualification/",
    "artifacts/wave4/",
    "docs/04_readiness/NEXUS_12H_V3_",
    "docs/04_readiness/NEXUS_6H_V2_",
)


def main() -> int:
    broken = []
    for root_name in SCAN_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in {".py", ".yml", ".yaml", ".md", ".json", ".toml"}:
                continue
            # skip inventory of deleted files
            if "deleted_files_manifest" in f.name or "cleanup_inventory" in f.name:
                continue
            if f.name.startswith("_build_oos_preflight") or f.name.startswith("_cleanup_unknown"):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in PAT.findall(text):
                path = m.rstrip(".,);:]'\"")
                if any(path.startswith(p) for p in ALLOW_MISSING_PREFIXES):
                    # runtime write destination — only flag if suffix looks like a specific committed file under deleted canonical tree without readiness
                    if path.startswith("artifacts/readiness/"):
                        pass
                    else:
                        continue
                if path.endswith("/") or "*" in path:
                    continue
                # skip globs embedded
                if path.endswith("*.md") or path.endswith("*.json"):
                    continue
                target = ROOT / path
                if not target.exists():
                    # allow references inside immutable supersedes lists etc.
                    if "immutable" in path or path.endswith("NEXUS_READINESS_SOT.md"):
                        broken.append({"file": f.relative_to(ROOT).as_posix(), "path": path})
                    elif path.startswith("docs/04_readiness/") or path.startswith("artifacts/readiness/"):
                        broken.append({"file": f.relative_to(ROOT).as_posix(), "path": path})
    out = ROOT / "artifacts" / "readiness" / "broken_reference_scan.json"
    out.write_text(json.dumps({"broken_reference_count": len(broken), "broken": broken}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"broken_reference_count": len(broken), "sample": broken[:20]}, indent=2))
    return 0 if not broken else 1


if __name__ == "__main__":
    raise SystemExit(main())
