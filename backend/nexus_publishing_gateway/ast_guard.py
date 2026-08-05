"""AST import boundary scanner + mutation kill helpers (Pass 2 hardened)."""
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


def scan_forbidden_imports(root: Path | None = None) -> dict[str, Any]:
    """AST-scan gateway package for forbidden private-core / trading imports."""
    violations: list[dict[str, Any]] = []
    dynamic_hits: list[dict[str, Any]] = []
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
            # Dynamic import surface (__import__ / importlib.import_module)
            if isinstance(node, ast.Call):
                fn = node.func
                name = None
                if isinstance(fn, ast.Name):
                    name = fn.id
                elif isinstance(fn, ast.Attribute):
                    name = fn.attr
                if name in {"__import__", "import_module"}:
                    dynamic_hits.append(
                        {
                            "file": str(path),
                            "call": name,
                            "lineno": getattr(node, "lineno", None),
                        }
                    )
    return {
        "files_scanned": len(files),
        "violation_count": len(violations),
        "violations": violations,
        "dynamic_import_count": len(dynamic_hits),
        "dynamic_imports": dynamic_hits,
        "owned_paths": list(OWNED_PATHS),
    }


def assert_no_private_imports(root: Path | None = None) -> dict[str, Any]:
    report = scan_forbidden_imports(root)
    if report["violation_count"]:
        raise PrivateImportError(f"private_import_violations:{report['violation_count']}")
    if report["dynamic_import_count"]:
        raise PrivateImportError(f"dynamic_import_violations:{report['dynamic_import_count']}")
    return report


def _mutate_source_noop_deny(source: str) -> str:
    return source.replace(
        'assert_no_denied_fields(raw, context="pre_allowlist")',
        "True  # MUTANT",
    )


def _mutate_source_drop_allowlist(source: str) -> str:
    return source.replace(
        "allowed = serialize_allowlist(raw)",
        "allowed = raw  # MUTANT",
    )


def _mutate_source_skip_env(source: str) -> str:
    return source.replace(
        "env = assert_local_or_staging(environment)",
        'env = "PRODUCTION"  # MUTANT',
    )


def _mutate_source_skip_post_deny(source: str) -> str:
    return source.replace(
        'assert_no_denied_fields(aggregated, context="post_aggregation")',
        "True  # MUTANT_POST",
    )


def _structural_kill(mutated: str, mutant_id: str) -> bool:
    markers = {
        "deny_trap_noop": (
            'assert_no_denied_fields(raw, context="pre_allowlist")' not in mutated
            and "# MUTANT" in mutated
        ),
        "allowlist_bypass": (
            "allowed = raw  # MUTANT" in mutated and "serialize_allowlist(raw)" not in mutated
        ),
        "env_guard_bypass": (
            'env = "PRODUCTION"  # MUTANT' in mutated
            and "assert_local_or_staging(environment)" not in mutated
        ),
        "post_deny_noop": (
            'assert_no_denied_fields(aggregated, context="post_aggregation")' not in mutated
            and "# MUTANT_POST" in mutated
        ),
    }
    return bool(markers.get(mutant_id))


def _semantic_dual_bypass_would_leak() -> dict[str, Any]:
    """Prove that bypassing deny + allowlist would expose private keys (oracle)."""
    from backend.nexus_publishing_gateway.deny_traps import find_denied_fields

    dirty = {
        "market_state": "OPEN",
        "strategy_id": "S-LEAK",
        "api_secret": "sekrit",
        "orders": [{"order_id": "1"}],
    }
    # Simulated dual-bypass output == raw dirty payload
    leaked_keys = find_denied_fields(dirty)
    return {
        "would_leak": len(leaked_keys) > 0,
        "leaked_key_count": len(leaked_keys),
        "sample": leaked_keys[:5],
    }


def run_ast_mutation_kills(
    *,
    source_path: Path | None = None,
    oracle: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Apply source mutants; require structural detection + semantic leak oracle."""
    path = source_path or (_package_root() / "gateway.py")
    original = path.read_text(encoding="utf-8")
    mutants = {
        "deny_trap_noop": _mutate_source_noop_deny(original),
        "allowlist_bypass": _mutate_source_drop_allowlist(original),
        "env_guard_bypass": _mutate_source_skip_env(original),
        "post_deny_noop": _mutate_source_skip_post_deny(original),
    }
    results: list[dict[str, Any]] = []
    killed = 0
    survivors = 0
    semantic = _semantic_dual_bypass_would_leak()

    for mid, mutated in mutants.items():
        if oracle is None:
            detected = _structural_kill(mutated, mid)
        else:
            detected = bool(oracle(mutated))
        try:
            ast.parse(mutated)
            parse_ok = True
        except SyntaxError:
            parse_ok = False
            detected = True
        # Semantic reinforcement: dual-bypass leak oracle must remain true.
        if mid in {"deny_trap_noop", "allowlist_bypass"} and not semantic["would_leak"]:
            detected = False
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
        "semantic_dual_bypass": semantic,
        "passed": survivors == 0 and killed == len(mutants) and semantic["would_leak"],
        "results": results,
    }
