"""Source scanners for hardcoded / fabricated LIVE values in Member UI."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_v2_live_binding.constants import (
    FORBIDDEN_IMPORT_PREFIXES,
    OWNED_PATHS,
)

# Hardcoded LIVE anti-patterns in Member pages (must use BoundLiveValue / live client).
HARDCODED_LIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Explicit fake live numbers presented without lineage plumbing
    re.compile(r"(?i)live[_ ]?price\s*[:=]\s*['\"]?\d"),
    re.compile(r"(?i)hardcoded[_ ]?live\s*[:=]"),
    re.compile(r"(?i)\bfabricate_live\b"),
    re.compile(r"(?i)\bfabricated_live_value\b"),
    # Member pages must not assert LIVE while importing demoCatalog for metric values
    re.compile(r"(?i)mode\s*[:=]\s*['\"]LIVE['\"].*demoCatalog", re.DOTALL),
)

# Allow demoCatalog imports only when accompanied by DEMO / fixture markers nearby —
# the LIVE binding module must not import demoCatalog at all.
DEMO_IMPORT_IN_LIVE_MODULE = re.compile(
    r"from\s+['\"]?\.\.?/?.*demoCatalog|from\s+['\"].*member/demoCatalog"
)


def _iter_owned_py(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_file() and target.suffix == ".py":
            files.append(target)
        elif target.is_dir():
            files.extend(p for p in target.rglob("*.py") if p.is_file())
    return sorted(set(files))


def _iter_frontend_ts(root: Path) -> list[Path]:
    roots = [
        root / "frontend" / "src" / "public_v2_live_binding",
        root / "frontend" / "src" / "pages" / "member",
        root / "frontend" / "src" / "member",
    ]
    files: list[Path] = []
    for base in roots:
        if not base.exists():
            continue
        files.extend(base.rglob("*.ts"))
        files.extend(base.rglob("*.tsx"))
    return sorted(set(files))


def scan_hardcoded_live_in_frontend(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    live_mod = root / "frontend" / "src" / "public_v2_live_binding"
    for path in _iter_frontend_ts(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        for pat in HARDCODED_LIVE_PATTERNS:
            for m in pat.finditer(text):
                # Allow ban / honesty prose that forbids fabrication (not an assignment).
                window = text[max(0, m.start() - 40) : m.end() + 40].lower()
                if any(
                    tok in window
                    for tok in (
                        "no fabricated",
                        "never fabricat",
                        "refuse",
                        "hard ban",
                        "must not",
                        "forbidden",
                    )
                ):
                    continue
                hits.append({"file": rel, "match": m.group(0)[:80], "kind": "hardcoded_pattern"})
        # LIVE binding package must never import demoCatalog
        if live_mod in path.parents or path.parent == live_mod:
            if "demoCatalog" in text or "MEMBER_DEMO" in text:
                hits.append({"file": rel, "match": "demoCatalog_in_live_module", "kind": "demo_merge"})
        # Member pages under LIVE path: forbid magic price literals labeled as LIVE
        if re.search(r"(?i)['\"]LIVE['\"].{0,40}(95000|100000|42000|price\s*=\s*\d)", text):
            hits.append({"file": rel, "match": "live_with_magic_price", "kind": "hardcoded_price"})
    return {"ok": len(hits) == 0, "hits": hits, "count": len(hits)}


def scan_forbidden_imports(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _iter_owned_py(root):
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for mod in modules:
                for prefix in FORBIDDEN_IMPORT_PREFIXES:
                    if mod == prefix or mod.startswith(prefix + "."):
                        hits.append(
                            {
                                "file": str(path.relative_to(root)).replace("\\", "/"),
                                "module": mod,
                            }
                        )
    return {"ok": len(hits) == 0, "hits": hits, "count": len(hits)}


def scan_status_json_writes(root: Path) -> dict[str, Any]:
    """Refuse creating *_status.json artifacts in owned paths."""
    hits: list[dict[str, str]] = []
    for path in _iter_owned_py(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if re.search(r"_status\.json", text) and re.search(
            r"(write_text|open\([^)]*['\"]w|json\.dump)", text
        ):
            # Allow comments that ban status json
            if "no_status_json" in text or "No *_status.json" in text or "status_json_written" in text:
                continue
            hits.append(
                {
                    "file": str(path.relative_to(root)).replace("\\", "/"),
                    "match": "_status.json write",
                }
            )
    return {"ok": len(hits) == 0, "hits": hits}
