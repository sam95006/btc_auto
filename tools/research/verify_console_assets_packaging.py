#!/usr/bin/env python3
"""Verify console PNGs are not excluded by .zeaburignore / .dockerignore."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import pathspec
except ImportError:  # pragma: no cover
    print("pathspec required")
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = (
    "static/nexus/assets/nexus_overview.png",
    "static/nexus/assets/hq_roundtable.png",
)


def _spec(name: str):
    path = ROOT / name
    if not path.exists():
        return None
    lines = [
        ln for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def main() -> int:
    errors: list[str] = []
    for rel in REQUIRED:
        p = ROOT / rel
        if not p.is_file() or p.stat().st_size < 1000:
            errors.append(f"missing_or_tiny:{rel}")
        # PNG magic
        head = p.read_bytes()[:8] if p.is_file() else b""
        if head != b"\x89PNG\r\n\x1a\n":
            errors.append(f"not_png:{rel}")

    for ignore_name in (".zeaburignore", ".dockerignore"):
        spec = _spec(ignore_name)
        if spec is None:
            continue
        for rel in REQUIRED:
            if spec.match_file(rel):
                errors.append(f"{ignore_name}_excludes:{rel}")

    if errors:
        print("FAIL", errors)
        return 1
    print("PASS console assets present and not ignored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
