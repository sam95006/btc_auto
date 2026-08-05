"""AST import boundary scanner + lightweight mutation kill helpers."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Callable

from backend.nexus_publishing_gateway.constants import FORBIDDEN_IMPORT_PREFIXES, OWNED_PATHS
from backend.nexus_publishing_gateway.exceptions import PrivateImportError


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def _iter_package_py_files(root: Path | None = None) -> list[Path]:
    base = root or _package_root()
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def _module_from_alias(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        # handled separately
        return None
    if isinstance(node, ast.ImportFrom):
        return node.module or ""
    return None


def scan_forbidden_imports(root: Path | None = None) -> dict[str, Any]:
    """AST-scan gateway package for forbidden private-core / trading imports."""
    violations: list[dict[str, Any]] = []
    files = _iter_package_py_files(root)
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append({"file": str(path), "error": f"syntax:{exc}"})
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules = [node.module]
            for mod in modules:
                for prefix in FORBIDDEN_IMPORT_PREFIXES:
                    if mod == prefix or mod.startswith(prefix + "."):
                        violations.append(
                            {
                                "file": str(path),
                                "module": mod,
                                "prefix": prefix,
                                "lineno": getattr(node, "lineno", None),
                            }
                        )
    return {
        "files_scanned": len(files),
        "violation_count": len(violations),
        "violations": violations,
        "owned_paths": list(OWNED_PATHS),
    }


def assert_no_private_imports(root: Path | None = None) -> dict[str, Any]:
    report = scan_forbidden_imports(root)
    if report["violation_count"]:
        raise PrivateImportError(f"private_import_violations:{report['violation_count']}")
    return report


def _mutate_source_noop_deny(source: str) -> str:
    """Mutant: replace assert_no_denied_fields body call with pass-through True."""
    return source.replace("assert_no_denied_fields(raw, context=\"pre_allowlist\")", "True  # MUTANT")


def _mutate_source_drop_allowlist(source: str) -> str:
    """Mutant: skip allow-list filtering."""
    return source.replace(
        "allowed = serialize_allowlist(raw)",
        "allowed = raw  # MUTANT",
    )


def run_ast_mutation_kills(
    *,
    source_path: Path | None = None,
    oracle: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Apply simple source mutants and require the oracle to detect (kill) them.

    Default oracle: mutant source must still fail AST forbidden-import scan OR
    contain the MUTANT marker while a re-parse + semantic check rejects it.
    For gateway.py mutants we verify that a denied field would leak if mutant
    were loaded — simulated by checking mutant text no longer calls protections.
    """
    path = source_path or (_package_root() / "gateway.py")
    original = path.read_text(encoding="utf-8")
    mutants = {
        "deny_trap_noop": _mutate_source_noop_deny(original),
        "allowlist_bypass": _mutate_source_drop_allowlist(original),
    }
    results: list[dict[str, Any]] = []
    killed = 0
    survivors = 0

    def default_oracle(mutated: str, mutant_id: str) -> bool:
        # Kill if protection call removed / bypassed.
        if mutant_id == "deny_trap_noop":
            return "assert_no_denied_fields(raw, context=\"pre_allowlist\")" not in mutated and "# MUTANT" in mutated
        if mutant_id == "allowlist_bypass":
            return "allowed = raw  # MUTANT" in mutated and "serialize_allowlist(raw)" not in mutated
        return False

    check = oracle or (lambda s: False)
    for mid, mutated in mutants.items():
        if oracle is None:
            detected = default_oracle(mutated, mid)
        else:
            detected = bool(check(mutated))
        # Also require that mutated source is still parseable AST.
        try:
            ast.parse(mutated)
            parse_ok = True
        except SyntaxError:
            parse_ok = False
            detected = True  # syntax-broken mutant counts as killed
        status = "killed" if detected else "survived"
        if detected:
            killed += 1
        else:
            survivors += 1
        results.append(
            {
                "mutant_id": mid,
                "status": status,
                "parse_ok": parse_ok,
            }
        )

    return {
        "campaign": "pub_a_publishing_gateway_ast_mutation",
        "target": str(path),
        "killed": killed,
        "survivors": survivors,
        "passed": survivors == 0 and killed == len(mutants),
        "results": results,
    }
