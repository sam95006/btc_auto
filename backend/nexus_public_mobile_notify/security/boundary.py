"""Public/private security boundary checks for PUB-K."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from backend.nexus_public_mobile_notify.constants import OWNED_PATHS, PRIVATE_FIELD_DENYLIST
from backend.nexus_public_mobile_notify.hard_bans import HardBanViolation

# Private-core module prefixes that must never be imported from PUB-K owned code.
PRIVATE_IMPORT_PREFIXES = (
    "backend.autonomy",
    "backend.trading",
    "backend.wallet",
    "backend.nexus_research",
    "backend.governance",
    "backend.fleets",
    "backend.learning",
    "backend.coordination",
)


def scan_private_imports(root: Path) -> dict[str, Any]:
    """AST-scan owned Python paths for private-core imports."""
    violations: list[dict[str, str]] = []
    py_root = root / "backend" / "nexus_public_mobile_notify"
    if not py_root.exists():
        return {
            "schema": "pub_k_private_import_scan",
            "public_private_import_violation_count": 0,
            "violations": [],
            "ok": True,
        }
    for path in py_root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(
                {
                    "path": str(path.relative_to(root)).replace("\\", "/"),
                    "detail": f"syntax_error:{exc}",
                }
            )
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(name == p or name.startswith(p + ".") for p in PRIVATE_IMPORT_PREFIXES):
                    violations.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "import": name,
                        }
                    )
    return {
        "schema": "pub_k_private_import_scan",
        "public_private_import_violation_count": len(violations),
        "violations": violations,
        "ok": len(violations) == 0,
        "owned_paths": list(OWNED_PATHS),
    }


def assert_boundary_clean(root: Path) -> None:
    result = scan_private_imports(root)
    if not result["ok"]:
        raise HardBanViolation(
            f"HARD BAN: private-core import detected: {result['violations']}"
        )


def private_field_denylist() -> frozenset[str]:
    return PRIVATE_FIELD_DENYLIST
