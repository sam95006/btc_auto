"""Custom AST mutation operators for production Private Core security modules.

No mutmut / cosmic-ray dependency. Mutants are written only under a temp sandbox
owned by the R4 review lane — production sources are never edited in-place.
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from typing import Any, Callable, Iterator


@dataclass(frozen=True)
class MutantSpec:
    mutant_id: str
    target_rel: str
    description: str
    operator: str
    lineno: int | None = None


class _MutationTransformer(ast.NodeTransformer):
    """Apply a single targeted mutation selected by operator + optional lineno."""

    def __init__(self, operator: str, target_lineno: int | None = None) -> None:
        self.operator = operator
        self.target_lineno = target_lineno
        self.applied = False

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if self.applied:
            return node
        if self.operator == "compare_always_true":
            if self.target_lineno is None or getattr(node, "lineno", None) == self.target_lineno:
                self.applied = True
                return ast.copy_location(ast.Constant(value=True), node)
        if self.operator == "compare_always_false":
            if self.target_lineno is None or getattr(node, "lineno", None) == self.target_lineno:
                self.applied = True
                return ast.copy_location(ast.Constant(value=False), node)
        return node

    def visit_Raise(self, node: ast.Raise) -> ast.AST:
        self.generic_visit(node)
        if self.applied:
            return node
        if self.operator == "remove_raise":
            if self.target_lineno is None or getattr(node, "lineno", None) == self.target_lineno:
                self.applied = True
                # replace raise with pass
                return ast.copy_location(ast.Pass(), node)
        return node

    def visit_If(self, node: ast.If) -> ast.AST:
        self.generic_visit(node)
        if self.applied:
            return node
        if self.operator == "negate_if":
            if self.target_lineno is None or getattr(node, "lineno", None) == self.target_lineno:
                self.applied = True
                node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
                return node
        if self.operator == "if_body_pass":
            if self.target_lineno is None or getattr(node, "lineno", None) == self.target_lineno:
                self.applied = True
                node.body = [ast.Pass()]
                return node
        return node

    def visit_Return(self, node: ast.Return) -> ast.AST:
        self.generic_visit(node)
        if self.applied:
            return node
        if self.operator == "return_true":
            if self.target_lineno is None or getattr(node, "lineno", None) == self.target_lineno:
                self.applied = True
                node.value = ast.Constant(value=True)
                return node
        if self.operator == "return_false":
            if self.target_lineno is None or getattr(node, "lineno", None) == self.target_lineno:
                self.applied = True
                node.value = ast.Constant(value=False)
                return node
        if self.operator == "return_empty_list":
            if self.target_lineno is None or getattr(node, "lineno", None) == self.target_lineno:
                self.applied = True
                node.value = ast.List(elts=[], ctx=ast.Load())
                return node
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        self.generic_visit(node)
        if self.applied:
            return node
        if self.operator != "force_writes_enabled":
            return node
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "writes_enabled":
                if self.target_lineno is None or getattr(node, "lineno", None) == self.target_lineno:
                    self.applied = True
                    node.value = ast.Constant(value=True)
                    return node
        return node


def _func_named(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def apply_operator(source: str, operator: str, lineno: int | None = None) -> tuple[str, bool]:
    tree = ast.parse(source)
    tx = _MutationTransformer(operator, lineno)
    new_tree = tx.visit(tree)
    if not tx.applied:
        return source, False
    ast.fix_missing_locations(new_tree)
    return ast.unparse(new_tree), True


def mutate_remove_path_traversal_token_check(source: str) -> tuple[str, MutantSpec | None]:
    """Delete the `if \"..\" in posix.parts: raise` guard in assert_safe_relative_path."""
    tree = ast.parse(source)
    fn = _func_named(tree, "assert_safe_relative_path")
    if fn is None:
        return source, None
    new_body: list[ast.stmt] = []
    removed = False
    for stmt in fn.body:
        if (
            isinstance(stmt, ast.If)
            and isinstance(stmt.test, ast.Compare)
            and any(
                isinstance(c, ast.Constant) and c.value == ".."
                for c in ast.walk(stmt.test)
            )
        ):
            removed = True
            continue
        new_body.append(stmt)
    if not removed:
        return source, None
    fn.body = new_body
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), MutantSpec(
        mutant_id="persist_drop_dotdot_token_check",
        target_rel="backend/nexus_autonomy/security_persistence_v1.py",
        description="Remove PurePosixPath '..' token rejection in assert_safe_relative_path",
        operator="drop_dotdot_token_check",
        lineno=None,
    )


def mutate_scan_secrets_always_empty(source: str) -> tuple[str, MutantSpec | None]:
    tree = ast.parse(source)
    fn = _func_named(tree, "scan_secrets_in_evidence")
    if fn is None:
        return source, None
    # Replace body with `return []`
    fn.body = [ast.Return(value=ast.List(elts=[], ctx=ast.Load()))]
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), MutantSpec(
        mutant_id="persist_scan_secrets_noop",
        target_rel="backend/nexus_autonomy/security_persistence_v1.py",
        description="scan_secrets_in_evidence always returns []",
        operator="return_empty_list",
    )


def mutate_fail_closed_json_accept_scalars(source: str) -> tuple[str, MutantSpec | None]:
    tree = ast.parse(source)
    fn = _func_named(tree, "fail_closed_json_loads")
    if fn is None:
        return source, None
    # Remove scalar-root rejection If
    new_body: list[ast.stmt] = []
    removed = False
    for stmt in fn.body:
        if isinstance(stmt, ast.If):
            # heuristic: untrusted_scalar_root raise inside
            text = ast.unparse(stmt)
            if "untrusted_scalar_root" in text or "isinstance(data" in text:
                removed = True
                continue
        new_body.append(stmt)
    if not removed:
        return source, None
    fn.body = new_body
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), MutantSpec(
        mutant_id="persist_json_accept_scalars",
        target_rel="backend/nexus_autonomy/security_persistence_v1.py",
        description="fail_closed_json_loads accepts scalar roots",
        operator="drop_scalar_root_check",
    )


def mutate_credential_ignore_mainnet_fallback(source: str) -> tuple[str, MutantSpec | None]:
    tree = ast.parse(source)
    fn = _func_named(tree, "resolve_exchange_profile")
    if fn is None:
        return source, None
    # Force mainnet_fallback = False after detection assign
    inserted = False
    new_body: list[ast.stmt] = []
    for stmt in fn.body:
        new_body.append(stmt)
        if (
            not inserted
            and isinstance(stmt, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "mainnet_fallback" for t in stmt.targets)
        ):
            force = ast.Assign(
                targets=[ast.Name(id="mainnet_fallback", ctx=ast.Store())],
                value=ast.Constant(value=False),
            )
            new_body.append(force)
            inserted = True
    if not inserted:
        return source, None
    fn.body = new_body
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), MutantSpec(
        mutant_id="cred_ignore_mainnet_fallback",
        target_rel="backend/nexus_autonomy/security_credential_boundary_v1.py",
        description="Force mainnet_fallback=False after detection (hides demo→mainnet fallback)",
        operator="force_mainnet_fallback_false",
    )


def mutate_credential_force_writes(source: str) -> tuple[str, MutantSpec | None]:
    mutated, ok = apply_operator(source, "force_writes_enabled")
    if not ok:
        # Fallback: append writes_enabled=True before returns in resolve_exchange_profile
        tree = ast.parse(source)
        fn = _func_named(tree, "resolve_exchange_profile")
        if fn is None:
            return source, None
        # Find last assignment to writes_enabled and force True
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "writes_enabled":
                        node.value = ast.Constant(value=True)
        ast.fix_missing_locations(tree)
        mutated = ast.unparse(tree)
    return mutated, MutantSpec(
        mutant_id="cred_force_writes_enabled",
        target_rel="backend/nexus_autonomy/security_credential_boundary_v1.py",
        description="Force writes_enabled=True assignments",
        operator="force_writes_enabled",
    )


def mutate_public_schema_noop(source: str) -> tuple[str, MutantSpec | None]:
    tree = ast.parse(source)
    fn = _func_named(tree, "assert_public_schema")
    if fn is None:
        return source, None
    fn.body = [ast.Return(value=None)]
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), MutantSpec(
        mutant_id="public_assert_schema_noop",
        target_rel="backend/nexus_autonomy/security_public_private_v1.py",
        description="assert_public_schema becomes no-op",
        operator="noop_assert_public_schema",
    )


def mutate_redact_identity(source: str) -> tuple[str, MutantSpec | None]:
    tree = ast.parse(source)
    fn = _func_named(tree, "redact_account_identifiers")
    if fn is None:
        return source, None
    # return input unchanged: find first arg name
    arg = fn.args.args[0].arg if fn.args.args else "payload"
    fn.body = [ast.Return(value=ast.Name(id=arg, ctx=ast.Load()))]
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), MutantSpec(
        mutant_id="public_redact_identity",
        target_rel="backend/nexus_autonomy/security_public_private_v1.py",
        description="redact_account_identifiers returns payload unchanged",
        operator="redact_identity",
    )


def mutate_write_trap_install_noop(source: str) -> tuple[str, MutantSpec | None]:
    tree = ast.parse(source)
    # Prefer install / enable method on WriteTrapRegistry
    for name in ("install", "install_traps", "enable", "arm"):
        fn = _func_named(tree, name)
        if fn is not None:
            fn.body = [ast.Return(value=ast.Constant(value=True))]
            ast.fix_missing_locations(tree)
            return ast.unparse(tree), MutantSpec(
                mutant_id=f"write_trap_{name}_noop",
                target_rel="backend/nexus_autonomy/security_write_traps_v1.py",
                description=f"{name}() becomes no-op success",
                operator="write_trap_noop",
            )
    # Fallback: neutralize ExchangeWriteForbidden raises
    mutated, ok = apply_operator(source, "remove_raise")
    if not ok:
        return source, None
    return mutated, MutantSpec(
        mutant_id="write_trap_remove_raise",
        target_rel="backend/nexus_autonomy/security_write_traps_v1.py",
        description="Remove first raise (weakens write trap)",
        operator="remove_raise",
    )


MutatorFn = Callable[[str], tuple[str, MutantSpec | None]]

TARGET_MUTATORS: dict[str, list[MutatorFn]] = {
    "backend/nexus_autonomy/security_persistence_v1.py": [
        mutate_remove_path_traversal_token_check,
        mutate_scan_secrets_always_empty,
        mutate_fail_closed_json_accept_scalars,
    ],
    "backend/nexus_autonomy/security_credential_boundary_v1.py": [
        mutate_credential_ignore_mainnet_fallback,
        mutate_credential_force_writes,
    ],
    "backend/nexus_autonomy/security_public_private_v1.py": [
        mutate_public_schema_noop,
        mutate_redact_identity,
    ],
    "backend/nexus_autonomy/security_write_traps_v1.py": [
        mutate_write_trap_install_noop,
    ],
}


def iter_planned_mutants(target_rel: str, source: str) -> Iterator[tuple[MutantSpec, str]]:
    for mutator in TARGET_MUTATORS.get(target_rel, []):
        mutated, spec = mutator(source)
        if spec is not None and mutated != source:
            yield spec, mutated
