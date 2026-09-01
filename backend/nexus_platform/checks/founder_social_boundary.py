"""Founder ↔ Social HARD BAN checker (NEXUS-EXPERIENCE-1A).

Scans every Founder private-trading runtime package for imports of Personal
news/social/KOL/creator intelligence. The Founder trading runtime must NEVER
consume social sentiment, KOL scores, social hype, or creator track record.
Used by the CI test; returns a list of violations (empty = clean).
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.nexus_platform.domains import FOUNDER_RUNTIME_PACKAGES, SOCIAL_BANNED_IMPORT_TERMS

_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)


def scan_founder_social_violations(repo_root: str | Path) -> list[dict]:
    root = Path(repo_root)
    violations: list[dict] = []
    for pkg in FOUNDER_RUNTIME_PACKAGES:
        pkg_dir = root / "backend" / pkg
        if not pkg_dir.is_dir():
            continue
        for py in pkg_dir.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            text = py.read_text(encoding="utf-8", errors="ignore")
            for m in _IMPORT_RE.finditer(text):
                module = m.group(1).lower()
                for term in SOCIAL_BANNED_IMPORT_TERMS:
                    if term in module:
                        line = text[: m.start()].count("\n") + 1
                        violations.append({"package": pkg, "file": str(py.relative_to(root)),
                                           "line": line, "import": m.group(1), "banned_term": term})
    return violations


if __name__ == "__main__":  # pragma: no cover
    import sys
    v = scan_founder_social_violations(Path(__file__).resolve().parents[3])
    if v:
        print("FOUNDER_SOCIAL_HARDBAN_FAIL")
        for x in v:
            print(f"  {x['file']}:{x['line']} imports {x['import']} (banned: {x['banned_term']})")
        sys.exit(1)
    print("FOUNDER_SOCIAL_HARDBAN_PASS")
