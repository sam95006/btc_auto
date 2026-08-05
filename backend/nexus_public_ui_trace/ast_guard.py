"""AST guard — forbid private-core / exchange imports inside PUB-G package."""
from __future__ import annotations

import ast
from pathlib import Path

from backend.nexus_public_ui_trace.constants import FORBIDDEN_IMPORT_PREFIXES, OWNED_PATHS


def _iter_py_files(root: Path) -> list[Path]:
    owned = []
    for rel in OWNED_PATHS:
        p = root / rel
        if p.is_file() and p.suffix == ".py":
            owned.append(p)
        elif p.is_dir():
            owned.extend(sorted(p.rglob("*.py")))
    return owned


def _module_from_import(node: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            names.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            names.append(node.module)
    return names


def scan_forbidden_imports(root: Path | None = None) -> list[str]:
    root = root or Path(__file__).resolve().parents[2]
    violations: list[str] = []
    for path in _iter_py_files(root):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path}: syntax_error:{exc}")
            continue
        for node in ast.walk(tree):
            for mod in _module_from_import(node):
                for prefix in FORBIDDEN_IMPORT_PREFIXES:
                    if mod == prefix or mod.startswith(prefix + "."):
                        violations.append(f"{path.relative_to(root)}:{mod}")
    return violations
