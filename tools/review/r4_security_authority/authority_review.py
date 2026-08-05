"""Authority registry / duplicate-gate / SCC review against Lane H + base tree."""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from tools.review.r4_security_authority.origin_loader import load_lane_h_summary


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _module_from_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _extract_imports(path: Path, root: Path) -> list[tuple[str, str]]:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except (OSError, SyntaxError, ValueError):
        return []
    mod = _module_from_path(path, root)
    edges: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append((mod, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.level:
                edges.append((mod, node.module))
    return edges


def find_backend_sccs(root: Path) -> list[list[str]]:
    edges: list[tuple[str, str]] = []
    backend = root / "backend"
    if not backend.exists():
        return []
    for path in backend.rglob("*.py"):
        if "zeabur" in path.parts or "__pycache__" in path.parts:
            continue
        edges.extend(_extract_imports(path, root))

    graph: dict[str, set[str]] = defaultdict(set)
    nodes: set[str] = set()
    for s, t in edges:
        if not s.startswith("backend.") or not t.startswith("backend."):
            continue
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


def verify_cost_model_divergence(root: Path) -> dict[str, Any]:
    exec_path = root / "backend/nexus_execution/cost_model.py"
    strat_path = root / "backend/nexus_strategy_engine/cost_semantics.py"
    exec_ver = strat_ver = None
    for path, attr in ((exec_path, "exec"), (strat_path, "strat")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        m = re.search(r'COST_MODEL_VERSION\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            if attr == "exec":
                exec_ver = m.group(1)
            else:
                strat_ver = m.group(1)
    divergent = bool(exec_ver and strat_ver and exec_ver != strat_ver)
    return {
        "code": "COST_MODEL_VERSION_DIVERGENCE",
        "confirmed": divergent,
        "execution_version": exec_ver,
        "strategy_version": strat_ver,
        "severity": "critical" if divergent else "info",
    }


def verify_fill_shim_embeds_authority(root: Path) -> dict[str, Any]:
    shim = root / "backend/nexus_autonomy/execution_simulator_v1_1.py"
    if not shim.is_file():
        return {"code": "FILL_SHIM_EMBED", "confirmed": False, "detail": "shim_missing"}
    text = shim.read_text(encoding="utf-8")
    markers = [
        "COMPATIBILITY",
        "try_fill",
        "FILL",
        "fill",
        "fee",
        "slippage",
    ]
    hits = [m for m in markers if m.lower() in text.lower() or m in text]
    # Strong signal: file contains both compatibility claim and fill logic
    has_compat = "COMPATIBILITY" in text.upper() or "compatibility" in text.lower()
    has_fill_logic = bool(
        re.search(r"def\s+(try_fill|_fill|fill_order|apply_fill)", text)
    ) or ("partial fill" in text.lower()) or ("same_bar" in text.lower())
    confirmed = has_compat and (has_fill_logic or text.lower().count("fill") > 15)
    return {
        "code": "AUTONOMY_SHIM_EMBEDS_FILL_AUTHORITY",
        "confirmed": confirmed,
        "has_compat_marker": has_compat,
        "has_fill_logic": has_fill_logic,
        "fill_token_count": len(re.findall(r"\bfill\b", text, re.I)),
        "severity": "critical" if confirmed else "high",
        "path": "backend/nexus_autonomy/execution_simulator_v1_1.py",
    }


def verify_parallel_retry(root: Path) -> dict[str, Any]:
    edge = root / "backend/nexus_edge_discovery/provider_transport_v23.py"
    canon = root / "backend/nexus_provider/retry_policy.py"
    edge_exists = edge.is_file()
    canon_exists = canon.is_file()
    local_backoff = False
    imports_canon = False
    if edge_exists:
        text = edge.read_text(encoding="utf-8")
        imports_canon = "nexus_provider.retry_policy" in text or "retry_policy" in text
        local_backoff = bool(
            re.search(r"backoff|Retry-After|retry_after|sleep\(", text, re.I)
        ) and not imports_canon
    return {
        "code": "PARALLEL_RETRY_IMPLEMENTATION",
        "confirmed": edge_exists and canon_exists and local_backoff,
        "edge_transport_present": edge_exists,
        "canonical_retry_present": canon_exists,
        "imports_canonical": imports_canon,
        "local_backoff_signals": local_backoff,
        "severity": "critical" if (edge_exists and canon_exists and local_backoff) else "info",
    }


def review_duplicate_authority_gate(h_summary: dict[str, Any]) -> dict[str, Any]:
    """Lane H CI gate PASSes while critical blockers remain — flag false-confidence risk."""
    gate_passed = bool(h_summary.get("ci_gate_passed"))
    blocker_count = int(h_summary.get("blocker_count") or 0)
    critical = list(h_summary.get("critical_blockers") or [])
    return {
        "check": "duplicate_authority_gate",
        "ci_gate_passed": gate_passed,
        "blocker_count": blocker_count,
        "critical_blocker_count": len(critical),
        "false_confidence_risk": gate_passed and blocker_count > 0,
        "detail": (
            "CI duplicate-authority gate PASSes by baselining known competitors; "
            "it does NOT clear critical multi-authority blockers. Integration must "
            "treat H as audit/registry/gate only — not runtime authority remediation."
        ),
        "critical_blockers": critical,
    }


def run_authority_review(
    root: Path | None = None,
    origin_h: Path | None = None,
) -> dict[str, Any]:
    root = (root or _repo_root()).resolve()
    h_summary = load_lane_h_summary(origin_h) if origin_h else {
        "artifacts_present": False,
        "blocker_count": 0,
        "critical_blockers": [],
        "ci_gate_passed": False,
        "circular_scc_count": 0,
        "circular_import_sccs": [],
    }

    sccs = find_backend_sccs(root)
    # Prefer H artifact SCCs when present (full scan including packages H covered)
    h_sccs = list(h_summary.get("circular_import_sccs") or [])
    scc_source = "lane_h_artifact" if h_sccs else "r4_independent_scan"
    scc_list = h_sccs or sccs

    cost = verify_cost_model_divergence(root)
    fill = verify_fill_shim_embeds_authority(root)
    retry = verify_parallel_retry(root)
    gate = review_duplicate_authority_gate(h_summary)

    findings: list[dict[str, Any]] = []
    for item in (cost, fill, retry):
        if item.get("confirmed"):
            findings.append(
                {
                    "severity": item.get("severity", "critical"),
                    "code": item["code"],
                    "detail": item,
                    "source": "r4_independent_confirm",
                }
            )

    if len(scc_list) > 0:
        findings.append(
            {
                "severity": "high",
                "code": "CIRCULAR_IMPORT_SCC",
                "detail": {
                    "circular_scc_count": len(scc_list),
                    "sccs": scc_list,
                    "source": scc_source,
                },
                "source": scc_source,
            }
        )

    if gate.get("false_confidence_risk"):
        findings.append(
            {
                "severity": "high",
                "code": "DUPLICATE_GATE_BASELINE_FALSE_CONFIDENCE",
                "detail": gate,
                "source": "r4_gate_semantics",
            }
        )

    # Multi-scope from H blockers
    for b in h_summary.get("critical_blockers") or []:
        code = b.get("code")
        if code in {
            "COST_MODEL_VERSION_DIVERGENCE",
            "DUAL_LIFECYCLE_VOCABULARY",
            "PARALLEL_RETRY_IMPLEMENTATION",
            "MULTI_SCOPE_AUTHORITY",
        }:
            domain = b.get("domain")
            already = any(
                f.get("code") == code
                and (
                    domain is None
                    or (isinstance(f.get("detail"), dict) and f["detail"].get("domain") == domain)
                    or f.get("domain") == domain
                )
                for f in findings
            )
            if already:
                continue
            findings.append(
                {
                    "severity": "critical",
                    "code": code,
                    "domain": domain,
                    "detail": b,
                    "source": "lane_h_blocker",
                }
            )

    critical_count = sum(1 for f in findings if f.get("severity") == "critical")
    return {
        "schema": "v11_r4_authority_review_v1",
        "lane_h": {
            "artifacts_present": bool(h_summary.get("artifacts_present")),
            "ci_gate_passed": h_summary.get("ci_gate_passed"),
            "blocker_count": h_summary.get("blocker_count"),
            "registry_version": h_summary.get("registry_version"),
            "graph_summary": h_summary.get("graph_summary"),
        },
        "circular_scc_count": len(scc_list),
        "circular_import_sccs": scc_list,
        "scc_source": scc_source,
        "independent_r4_scc_count": len(sccs),
        "cost_divergence": cost,
        "fill_shim": fill,
        "parallel_retry": retry,
        "duplicate_authority_gate": gate,
        "findings": findings,
        "critical_finding_count": critical_count,
        "high_finding_count": sum(1 for f in findings if f.get("severity") == "high"),
    }
