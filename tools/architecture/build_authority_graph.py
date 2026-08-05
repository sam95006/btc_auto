#!/usr/bin/env python3
"""Build machine-readable Private Core authority graph (V11 Lane H).

Scans Private Core (+ extended) packages for domain authority signatures,
import edges, circular import cycles, stale env-fallback markers, and
compatibility/shim markers. Writes artifacts under
artifacts/readiness/immutable/authority_consolidation_v1/.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_contracts.authority_registry import (  # noqa: E402
    build_canonical_registry,
    list_authorities,
)
from backend.nexus_contracts.authority_signatures import (  # noqa: E402
    DOMAIN_SIGNATURES,
    EXTENDED_SCAN_ROOTS,
    GRAPH_SCHEMA,
    PRIVATE_CORE_SCAN_ROOTS,
    STALE_ENV_FALLBACK_MARKERS,
)
from tools.architecture import artifact_dir, module_from_path, write_json  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iter_py_files(root: Path, rel_roots: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    for rel in rel_roots:
        base = root / rel
        if not base.exists():
            continue
        out.extend(sorted(base.rglob("*.py")))
    return out


def _match_sig(node: ast.AST, sig: dict[str, Any]) -> str | None:
    kind = sig.get("kind")
    if kind == "class" and isinstance(node, ast.ClassDef):
        name_re = sig.get("name_re")
        name = sig.get("name")
        if name and node.name == name:
            return node.name
        if name_re and re.search(name_re, node.name):
            return node.name
    if kind == "func" and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        name_re = sig.get("name_re")
        name = sig.get("name")
        if name and node.name == name:
            return node.name
        if name_re and re.search(name_re, node.name):
            return node.name
    if kind == "assign" and isinstance(node, ast.Assign):
        target_name = sig.get("name")
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == target_name:
                return t.id
    if kind == "assign" and isinstance(node, ast.AnnAssign):
        target_name = sig.get("name")
        if isinstance(node.target, ast.Name) and node.target.id == target_name:
            return node.target.id
    return None


def scan_file_claims(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        return [
            {
                "module": module_from_path(path, root),
                "domain": "_parse_error",
                "symbol": None,
                "lineno": getattr(exc, "lineno", None),
                "error": str(exc),
            }
        ]
    mod = module_from_path(path, root)
    claims: list[dict[str, Any]] = []
    for domain, sigs in DOMAIN_SIGNATURES.items():
        for node in ast.walk(tree):
            for sig in sigs:
                hit = _match_sig(node, sig)
                if hit:
                    claims.append(
                        {
                            "module": mod,
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "domain": domain,
                            "symbol": hit,
                            "lineno": getattr(node, "lineno", None),
                            "signature_kind": sig.get("kind"),
                        }
                    )
    # Deduplicate identical claims
    seen: set[tuple[Any, ...]] = set()
    uniq: list[dict[str, Any]] = []
    for c in claims:
        key = (c["module"], c["domain"], c["symbol"], c["lineno"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


def extract_imports(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
    except (OSError, SyntaxError):
        return []
    mod = module_from_path(path, root)
    # TYPE_CHECKING-only imports are typing contracts, not runtime edges.
    typecheck_ids = _type_checking_subtree_ids(tree)
    edges: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if id(node) in typecheck_ids:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(
                    {
                        "source": mod,
                        "target": alias.name,
                        "lineno": node.lineno,
                        "kind": "import",
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            # Absolute imports only for graph edges
            if node.level and node.level > 0:
                continue
            edges.append(
                {
                    "source": mod,
                    "target": node.module,
                    "lineno": node.lineno,
                    "kind": "from",
                }
            )
    return edges


def _is_type_checking_test(test: ast.AST) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False


def _type_checking_subtree_ids(tree: ast.AST) -> set[int]:
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            for child in ast.walk(node):
                skip.add(id(child))
    return skip


def find_cycles(edges: list[dict[str, Any]], keep_prefix: str = "backend.") -> list[list[str]]:
    """Detect simple cycles among backend.* modules (Tarjan SCC size>1 or self-loop)."""
    graph: dict[str, set[str]] = defaultdict(set)
    nodes: set[str] = set()
    for e in edges:
        s, t = e["source"], e["target"]
        if not s.startswith(keep_prefix) or not t.startswith(keep_prefix):
            continue
        # normalize target to package/module root used as node
        nodes.add(s)
        nodes.add(t)
        graph[s].add(t)

    index = 0
    stack: list[str] = []
    onstack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        onstack.add(v)
        for w in graph.get(v, ()):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in onstack:
                lowlink[v] = min(lowlink[v], indices[w])
        if lowlink[v] == indices[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                onstack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or (len(comp) == 1 and comp[0] in graph.get(comp[0], ())):
                sccs.append(sorted(comp))

    for n in sorted(nodes):
        if n not in indices:
            strongconnect(n)
    return sccs


def scan_stale_env_markers(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    hits: list[dict[str, Any]] = []
    mod = module_from_path(path, root)
    for i, line in enumerate(text.splitlines(), start=1):
        for marker in STALE_ENV_FALLBACK_MARKERS:
            if marker in line:
                hits.append(
                    {
                        "module": mod,
                        "path": str(path.relative_to(root)).replace("\\", "/"),
                        "lineno": i,
                        "marker": marker,
                        "line": line.strip()[:200],
                    }
                )
                break
    return hits


def scan_compat_markers(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    needles = (
        "COMPATIBILITY",
        "compatibility shim",
        "backward-compat",
        "Backward-compatible",
        "deprecated",
        "DEPRECATED",
        "legacy alias",
        "MUST NOT be treated as",
    )
    hits: list[dict[str, Any]] = []
    mod = module_from_path(path, root)
    lower_needles = [(n, n.lower()) for n in needles]
    for i, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        for orig, low_n in lower_needles:
            if low_n in low or orig in line:
                hits.append(
                    {
                        "module": mod,
                        "path": str(path.relative_to(root)).replace("\\", "/"),
                        "lineno": i,
                        "marker": orig,
                        "line": line.strip()[:200],
                    }
                )
                break
    return hits


def _package_prefix(dotted: str, depth: int = 2) -> str:
    """Return package prefix (default backend.<pkg>)."""
    parts = dotted.split(".")
    if len(parts) <= depth:
        return dotted
    return ".".join(parts[:depth])


def classify_claim(
    claim: dict[str, Any], registry: dict[str, Any]
) -> str:
    domain = claim["domain"]
    mod = claim["module"]
    auth = registry.get("by_domain", {}).get(domain)
    if not auth:
        return "unregistered_domain"
    if mod == auth["canonical_module"] or mod.startswith(auth["canonical_module"] + "."):
        return "canonical"
    for c in auth.get("competitors", []):
        if mod == c["module"] or mod.startswith(c["module"] + "."):
            return c.get("role", "competitor")
    # Same backend.<package> as canonical counts as satellite (adapter/helpers)
    canon_pkg = _package_prefix(auth["canonical_module"], 2)
    if mod == canon_pkg or mod.startswith(canon_pkg + "."):
        return "canonical_satellite"
    return "unregistered_competitor"


def build_graph(root: Path, *, include_extended: bool = True) -> dict[str, Any]:
    registry = build_canonical_registry()
    roots = list(PRIVATE_CORE_SCAN_ROOTS)
    if include_extended:
        roots.extend(EXTENDED_SCAN_ROOTS)

    files = _iter_py_files(root, roots)
    claims: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    env_hits: list[dict[str, Any]] = []
    compat_hits: list[dict[str, Any]] = []

    for path in files:
        claims.extend(scan_file_claims(path, root))
        edges.extend(extract_imports(path, root))
        # Limit noisy env scans to security/core/provider/research tools
        rel = str(path.relative_to(root)).replace("\\", "/")
        if any(
            rel.startswith(p)
            for p in (
                "backend/security/",
                "backend/core/",
                "backend/nexus_provider/",
                "backend/nexus_research/",
                "tools/research/",
            )
        ):
            env_hits.extend(scan_stale_env_markers(path, root))
        if any(
            rel.startswith(p)
            for p in (
                "backend/nexus_autonomy/",
                "backend/nexus_execution/",
                "backend/nexus_global_shadow/",
                "backend/nexus_real_shadow/",
                "backend/nexus_reflection/",
                "backend/nexus_research/",
            )
        ):
            compat_hits.extend(scan_compat_markers(path, root))

    for c in claims:
        if c.get("domain") == "_parse_error":
            c["classification"] = "parse_error"
        else:
            c["classification"] = classify_claim(c, registry)

    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in claims:
        if c.get("domain") and c["domain"] != "_parse_error":
            by_domain[c["domain"]].append(c)

    competing: dict[str, Any] = {}
    for domain, domain_claims in by_domain.items():
        modules = sorted({c["module"] for c in domain_claims})
        auth = registry["by_domain"].get(domain, {})
        canon = auth.get("canonical_module")
        non_canon = [m for m in modules if m != canon and not (canon and m.startswith(str(canon) + "."))]
        # Filter satellites of canonical package carefully — keep distinct packages
        distinct = []
        for m in non_canon:
            role = next(
                (x["classification"] for x in domain_claims if x["module"] == m),
                "unknown",
            )
            if role == "canonical_satellite":
                continue
            distinct.append({"module": m, "classification": role})
        competing[domain] = {
            "canonical_module": canon,
            "claimant_modules": modules,
            "non_canonical_claimants": distinct,
            "claimant_count": len(modules),
            "duplicate_authority_signal": len(distinct) > 0,
        }

    cycles = find_cycles(edges)

    # Critical findings from registry + graph
    critical: list[dict[str, Any]] = []
    for item in registry["summary"]["critical_competitors"]:
        critical.append({"kind": "registry_critical_competitor", **item})
    for domain, info in competing.items():
        unreg = [x for x in info["non_canonical_claimants"] if x["classification"] == "unregistered_competitor"]
        if unreg:
            critical.append(
                {
                    "kind": "unregistered_authority_claimant",
                    "domain": domain,
                    "modules": [x["module"] for x in unreg],
                    "severity": "high",
                }
            )
    if cycles:
        critical.append(
            {
                "kind": "circular_import_scc",
                "severity": "high",
                "sccs": cycles[:20],
                "scc_count": len(cycles),
            }
        )

    nodes = sorted({c["module"] for c in claims if c.get("module")})
    graph = {
        "schema": GRAPH_SCHEMA,
        "generated_at": _utc(),
        "lane": "V11_H_AUTHORITY_CONSOLIDATION",
        "scan_roots": roots,
        "scanned_files": len(files),
        "registry_version": registry["registry_version"],
        "nodes": [{"id": n, "kind": "module"} for n in nodes],
        "authority_claims": claims,
        "claims_by_domain": {k: v for k, v in sorted(by_domain.items())},
        "competing_authorities": competing,
        "import_edges": edges,
        "circular_import_sccs": cycles,
        "stale_env_fallback_hits": env_hits[:200],
        "stale_env_fallback_hit_count": len(env_hits),
        "compatibility_markers": compat_hits[:200],
        "compatibility_marker_count": len(compat_hits),
        "critical_findings": critical,
        "summary": {
            "domain_count": len(by_domain),
            "claim_count": len(claims),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "domains_with_duplicates": sorted(
                d for d, info in competing.items() if info["duplicate_authority_signal"]
            ),
            "circular_scc_count": len(cycles),
            "critical_finding_count": len(critical),
        },
    }
    return graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Build NEXUS authority graph")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-extended", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out_dir or artifact_dir(root)
    out.mkdir(parents=True, exist_ok=True)

    registry = build_canonical_registry()
    write_json(out / "canonical_authority_registry.json", registry)

    graph = build_graph(root, include_extended=not args.no_extended)
    write_json(out / "authority_graph.json", graph)

    print(
        {
            "artifact_dir": str(out),
            "scanned_files": graph["scanned_files"],
            "domains_with_duplicates": graph["summary"]["domains_with_duplicates"],
            "critical_finding_count": graph["summary"]["critical_finding_count"],
            "circular_scc_count": graph["summary"]["circular_scc_count"],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
