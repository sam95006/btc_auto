"""Static import-graph analysis for Private Core security boundary."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from backend.nexus_autonomy.security_constants_v1 import (
    EXECUTION_WRITE_MODULES,
    LESSON_PRIVATE_MODULES,
    PRIVATE_CORE_PREFIXES,
    PUBLIC_ROUTE_PREFIXES,
    SIMULATION_PREFIXES,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def module_name_from_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def classify_module(mod: str) -> str:
    if any(mod == p or mod.startswith(p + ".") for p in PUBLIC_ROUTE_PREFIXES):
        return "PUBLIC_ROUTE"
    if mod in EXECUTION_WRITE_MODULES or any(mod.startswith(m + ".") for m in EXECUTION_WRITE_MODULES):
        return "EXECUTION_WRITE"
    if any(mod == p or mod.startswith(p + ".") for p in SIMULATION_PREFIXES):
        return "SIMULATION"
    if any(mod == p or mod.startswith(p + ".") for p in LESSON_PRIVATE_MODULES):
        return "LESSON_PRIVATE"
    if any(mod == p or mod.startswith(p + ".") for p in PRIVATE_CORE_PREFIXES):
        return "PRIVATE_CORE"
    if "api_routes" in mod or mod.endswith(".api_routes"):
        if "demo" in mod or "founder" in mod or "shadow" in mod or "control_plane" in mod:
            return "PRIVATE_OR_DEMO_ROUTE"
        return "OTHER_ROUTE"
    if mod.startswith("tools.research") or mod.startswith("tools.ci"):
        return "RESEARCH_TOOL"
    return "OTHER"


@dataclass
class ImportEdge:
    source: str
    target: str
    lineno: int
    source_class: str
    target_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "lineno": self.lineno,
            "source_class": self.source_class,
            "target_class": self.target_class,
        }


@dataclass
class ImportGraphReport:
    nodes: set[str] = field(default_factory=set)
    edges: list[ImportEdge] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    scanned_files: int = 0

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def to_dict(self) -> dict[str, Any]:
        return {
            "import_graph_node_count": self.node_count,
            "import_graph_edge_count": self.edge_count,
            "scanned_files": self.scanned_files,
            "violation_count": len(self.violations),
            "violations": list(self.violations),
            "passed": len(self.violations) == 0,
        }


FORBIDDEN_EDGE_RULES: tuple[tuple[str, str, str], ...] = (
    ("PUBLIC_ROUTE", "EXECUTION_WRITE", "public_route_imports_execution_write"),
    ("PUBLIC_ROUTE", "LESSON_PRIVATE", "public_route_imports_private_lesson"),
    ("SIMULATION", "EXECUTION_WRITE", "simulation_imports_execution_write"),
)


def _iter_imports(tree: ast.AST) -> Iterable[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module, node.lineno
                for alias in node.names:
                    if alias.name != "*":
                        yield f"{node.module}.{alias.name}", node.lineno


def _is_forbidden(src_class: str, tgt_class: str) -> str | None:
    for s, t, code in FORBIDDEN_EDGE_RULES:
        if src_class == s and tgt_class == t:
            return code
    # PUBLIC must not import private autonomy internals that are not security itself
    if src_class == "PUBLIC_ROUTE" and tgt_class == "PRIVATE_CORE":
        return "public_route_imports_private_core"
    return None


def build_import_graph(
    *,
    root: Path | None = None,
    include_globs: tuple[str, ...] = (
        "backend/api/**/*.py",
        "backend/nexus_autonomy/**/*.py",
        "backend/nexus_learning/**/*.py",
        "backend/nexus_demo_execution/**/*.py",
        "backend/nexus_research/demo_autonomous/**/*.py",
        "tools/research/run_*private*.py",
        "tools/research/run_*harness*.py",
        "tools/research/run_*spine*.py",
    ),
) -> ImportGraphReport:
    base = root or _repo_root()
    report = ImportGraphReport()
    files: list[Path] = []
    for pattern in include_globs:
        files.extend(base.glob(pattern))
    # de-dupe
    seen: set[Path] = set()
    for path in sorted(files):
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        report.scanned_files += 1
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
        except (OSError, SyntaxError):
            continue
        try:
            src = module_name_from_path(path, base)
        except ValueError:
            continue
        src_class = classify_module(src)
        report.nodes.add(src)
        for target, lineno in _iter_imports(tree):
            # normalize relative-ish targets
            tgt = target
            tgt_class = classify_module(tgt)
            # Also classify by prefix match against known write modules
            for write_mod in EXECUTION_WRITE_MODULES:
                if tgt == write_mod or tgt.startswith(write_mod + ".") or write_mod.startswith(tgt + "."):
                    if "demo_write" in tgt or "write_adapter" in tgt or "write_transport" in tgt:
                        tgt_class = "EXECUTION_WRITE"
            report.nodes.add(tgt)
            edge = ImportEdge(
                source=src,
                target=tgt,
                lineno=lineno,
                source_class=src_class,
                target_class=tgt_class,
            )
            report.edges.append(edge)
            code = _is_forbidden(src_class, tgt_class)
            if code:
                # refine: only flag when target is truly a write client import
                if code == "public_route_imports_execution_write" or code == "simulation_imports_execution_write":
                    if not any(
                        w in tgt or tgt in w
                        for w in EXECUTION_WRITE_MODULES
                    ) and "demo_write_client" not in tgt and "write_adapter" not in tgt:
                        continue
                report.violations.append({severity: code, **edge.to_dict()})
    return report


def assert_import_graph_clean(root: Path | None = None) -> ImportGraphReport:
    report = build_import_graph(root=root)
    if report.violations:
        sample = report.violations[0]
        raise AssertionError(
            f"import_graph_violation:{sample.get('rule')}:{sample.get('source')}->{sample.get('target')}"
        )
    return report
