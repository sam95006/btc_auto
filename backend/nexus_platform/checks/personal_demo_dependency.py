"""Personal production demo-dependency audit (NEXUS-EXPERIENCE-1A).

Scans the Personal PRODUCTION frontend for imports of demo/fixture catalogs that
masquerade as live user-facing answers. Test/fixture/spec files are exempt. This
is an AUDIT tool for Workstream A (documents the baseline); Workstream B removes
the production dependency and this becomes a hard CI gate (zero allowed).
"""
from __future__ import annotations

import re
from pathlib import Path

# Demo/fixture catalogs that must not power live user-facing Personal answers.
DEMO_MODULES = ("demoCatalog", "fixtureCatalog")
EXEMPT = re.compile(r"(__tests__|\.test\.|\.spec\.|/fixtures?/|/mocks?/|/test/)", re.IGNORECASE)
# Match the `from "…"` / `import "…"` module specifier (handles multi-line
# import blocks where `} from "./demoCatalog"` is on its own line).
_IMPORT_RE = re.compile(r'(?:from|import)\s+["\']([^"\']+)["\']')


def scan_personal_demo_dependencies(repo_root: str | Path) -> list[dict]:
    root = Path(repo_root)
    member = root / "frontend" / "src" / "member"
    if not member.is_dir():
        return []
    hits: list[dict] = []
    for f in member.rglob("*.ts*"):
        rel = str(f.relative_to(root)).replace("\\", "/")
        if EXEMPT.search(rel):
            continue
        # the catalog files themselves are the demo source, not consumers
        if f.name in (m + ".ts" for m in DEMO_MODULES):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in _IMPORT_RE.finditer(text):
            spec = m.group(1)
            for demo in DEMO_MODULES:
                if demo in spec:
                    line = text[: m.start()].count("\n") + 1
                    hits.append({"file": rel, "line": line, "imports": spec, "demo_module": demo})
    return hits


if __name__ == "__main__":  # pragma: no cover
    hits = scan_personal_demo_dependencies(Path(__file__).resolve().parents[3])
    if hits:
        print(f"PERSONAL_DEMO_DEPENDENCY_FOUND ({len(hits)})")
        for h in hits:
            print(f"  {h['file']}:{h['line']} imports {h['imports']} ({h['demo_module']})")
    else:
        print("PERSONAL_DEMO_DEPENDENCY_NONE")
