#!/usr/bin/env python3
"""Authoritative public private-field leak scanner (P0-A).

Counts REAL payload / DTO / serializer emissions of denied private fields in
public-owned packages. Probe fixtures, deny-lists, and adversarial hard-ban
assertions are classified as SCANNER_FALSE_POSITIVE via context — not via
blind file ignores.

Usage:
  python tools/public/scan_private_field_leaks.py [--root PATH] [--json]
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

# Keys historically attested as private_field_leak_count markers.
LEAK_FIELD_KEYS: frozenset[str] = frozenset(
    {
        "lesson_memory",
        "private_weights",
        "strategy_weights",
        "checkpoint_blob",
        "exchange_api_key",
        "wallet_private_key",
    }
)

# Dict-key literal forms: "lesson_memory": / 'strategy_weights':
KEY_LITERAL_RE = re.compile(
    r"""['"]("""
    + "|".join(re.escape(k) for k in sorted(LEAK_FIELD_KEYS))
    + r""")['"]\s*:"""
)

# Context windows that prove the match is a deny/probe/ban fixture, not a leak.
PROBE_CONTEXT_TOKENS: tuple[str, ...] = (
    "hard ban",
    "hard_ban",
    "hard_bans",
    "denied_private",
    "denied_fields",
    "deny_trap",
    "find_denied_fields",
    "assert_no_forbidden",
    "forbiddenpayload",
    "poison",
    "adversarial",
    "attack_",
    "serialize_allowlist",
    "allowlist_drop",
    "allowlist_leaked",
    "collect_field_names",
    "refuse_",
    "probe",
    "dirty_dto",
    "safe_public_seed",
    "disposition_fixed",
    "private_field_leakage",
    "prompt_lesson_leakage",
    # deny-list / constant membership
    "denied_private_fields",
    "forbidden_keys",
    "banned_fields",
    "private_field_patterns",
)

PUBLIC_PACKAGE_PREFIXES: tuple[str, ...] = (
    "backend/nexus_public_",
    "backend/nexus_customer_",
    "backend/nexus_publishing_gateway",
    "backend/founder_operator",
    "backend/public_mobile",
    "frontend/src/member",
    "frontend/src/pages/member",
    "frontend/src/public_",
)

SKIP_SUFFIXES: frozenset[str] = frozenset(
    {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".map"}
)
SCAN_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".ts", ".tsx", ".mjs", ".js", ".json"}
)


@dataclass(frozen=True)
class Hit:
    classification: str  # REAL_LEAK | SCANNER_FALSE_POSITIVE
    file: str
    line: int
    field: str
    match: str
    route: str | None
    dto: str | None
    serializer: str | None
    reason: str
    context: str


def _repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    return Path(__file__).resolve().parents[2]


def _rel_posix(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _under_public_prefix(rel: str) -> bool:
    return any(rel == p.rstrip("/") or rel.startswith(p) for p in PUBLIC_PACKAGE_PREFIXES)


def _iter_scan_files(root: Path) -> Iterable[Path]:
    """Walk repo and keep paths under public-owned prefix stems.

    Prefixes like ``backend/nexus_public_`` are stem filters (not directories).
    """
    candidates: list[Path] = []
    backend = root / "backend"
    if backend.is_dir():
        candidates.append(backend)
    frontend_src = root / "frontend" / "src"
    if frontend_src.is_dir():
        candidates.append(frontend_src)

    seen: set[Path] = set()
    for base in candidates:
        for path in base.rglob("*"):
            if not path.is_file() or path in seen:
                continue
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            if path.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if path.name in {"package-lock.json", "yarn.lock"}:
                continue
            rel = _rel_posix(root, path)
            if not _under_public_prefix(rel):
                continue
            seen.add(path)
            yield path

def _context_window(text: str, start: int, end: int, radius: int = 260) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)]


def _is_probe_context(ctx: str) -> bool:
    low = ctx.lower()
    return any(tok in low for tok in PROBE_CONTEXT_TOKENS)


def _nearest_def_name(text: str, pos: int) -> str | None:
    """Best-effort enclosing def/class name for route/dto/serializer attribution."""
    before = text[:pos]
    matches = list(re.finditer(r"(?m)^\s*(?:async\s+)?def\s+([A-Za-z_][\w]*)\s*\(", before))
    if not matches:
        matches = list(re.finditer(r"(?m)^\s*class\s+([A-Za-z_][\w]*)\s*[\(:]", before))
    if not matches:
        return None
    return matches[-1].group(1)


def _infer_route_dto_serializer(path: Path, func_name: str | None) -> tuple[str | None, str | None, str | None]:
    rel = str(path).replace("\\", "/").lower()
    route = None
    dto = None
    serializer = None
    if func_name:
        low = func_name.lower()
        if any(x in low for x in ("route", "endpoint", "handler", "api_", "get_", "post_")):
            route = func_name
        if any(x in low for x in ("dto", "model", "schema", "payload", "response")):
            dto = func_name
        if any(x in low for x in ("serialize", "sanitiz", "allowlist", "export", "publish")):
            serializer = func_name
    if "routes" in rel or "router" in rel or "api" in rel:
        route = route or func_name
    if "dto" in rel or "models" in rel:
        dto = dto or func_name or path.stem
    if "sanitiz" in rel or "allowlist" in rel or "serialize" in rel:
        serializer = serializer or func_name or path.stem
    return route, dto, serializer


def _classify_literal_hit(
    *,
    rel: str,
    line: int,
    field: str,
    match: str,
    ctx: str,
    func_name: str | None,
    path: Path,
) -> Hit:
    route, dto, serializer = _infer_route_dto_serializer(path, func_name)
    if _is_probe_context(ctx):
        return Hit(
            classification="SCANNER_FALSE_POSITIVE",
            file=rel,
            line=line,
            field=field,
            match=match,
            route=route,
            dto=dto,
            serializer=serializer,
            reason="denied-field literal appears in probe/deny/hard-ban/adversarial fixture context",
            context=re.sub(r"\s+", " ", ctx).strip()[:240],
        )
    # Deny-list constant files that only enumerate forbidden names (no emission).
    if path.name in {"constants.py", "deny_traps.py"} and (
        "denied" in ctx.lower() or "forbidden" in ctx.lower() or "ban" in ctx.lower()
    ):
        return Hit(
            classification="SCANNER_FALSE_POSITIVE",
            file=rel,
            line=line,
            field=field,
            match=match,
            route=route,
            dto=dto,
            serializer=serializer,
            reason="field name enumerated in deny/ban constants (not emitted)",
            context=re.sub(r"\s+", " ", ctx).strip()[:240],
        )
    return Hit(
        classification="REAL_LEAK",
        file=rel,
        line=line,
        field=field,
        match=match,
        route=route,
        dto=dto,
        serializer=serializer,
        reason="denied private field key literal without probe/deny context — treat as response/DTO emission risk",
        context=re.sub(r"\s+", " ", ctx).strip()[:240],
    )


def _ast_public_model_leaks(root: Path, path: Path, text: str) -> list[Hit]:
    """Flag public DTO/model classes that declare denied private fields as attributes."""
    hits: list[Hit] = []
    rel = str(path.relative_to(root)).replace("\\", "/")
    if path.suffix != ".py":
        return hits
    # Only attribute declarations on *dto* / *model* / *schema* modules matter.
    if not any(tok in rel.lower() for tok in ("/dto", "models", "schema", "serializer")):
        return hits
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return hits
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        class_low = node.name.lower()
        if not any(tok in class_low for tok in ("dto", "model", "schema", "response", "payload")):
            continue
        for stmt in node.body:
            names: list[str] = []
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                names.append(stmt.target.id)
            elif isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        names.append(t.id)
            for name in names:
                if name in LEAK_FIELD_KEYS:
                    hits.append(
                        Hit(
                            classification="REAL_LEAK",
                            file=rel,
                            line=getattr(stmt, "lineno", 0) or 0,
                            field=name,
                            match=name,
                            route=None,
                            dto=node.name,
                            serializer=None,
                            reason=f"public DTO/model {node.name} declares denied field {name}",
                            context=node.name,
                        )
                    )
    return hits


def scan_private_field_leaks(root: Path | None = None) -> dict[str, Any]:
    repo = _repo_root(root)
    all_hits: list[Hit] = []
    for path in _iter_scan_files(repo):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(repo)).replace("\\", "/")
        # Skip pure test modules under tests/ (not in PUBLIC_PACKAGE_PREFIXES anyway)
        for m in KEY_LITERAL_RE.finditer(text):
            field = m.group(1)
            line = text.count("\n", 0, m.start()) + 1
            ctx = _context_window(text, m.start(), m.end())
            func_name = _nearest_def_name(text, m.start())
            all_hits.append(
                _classify_literal_hit(
                    rel=rel,
                    line=line,
                    field=field,
                    match=m.group(0),
                    ctx=ctx,
                    func_name=func_name,
                    path=path,
                )
            )
        all_hits.extend(_ast_public_model_leaks(repo, path, text))

    real = [h for h in all_hits if h.classification == "REAL_LEAK"]
    fps = [h for h in all_hits if h.classification == "SCANNER_FALSE_POSITIVE"]
    return {
        "ok": len(real) == 0,
        "private_field_leak_count": len(real),
        "scanner_false_positive_count": len(fps),
        "survivors": [asdict(h) for h in real],
        "false_positives_classified": [asdict(h) for h in fps],
        "fields_watched": sorted(LEAK_FIELD_KEYS),
        "root": str(repo),
        "scanner": "tools/public/scan_private_field_leaks.py",
        "scanner_version": "p0a-v1-context-aware",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    args = parser.parse_args(argv)
    report = scan_private_field_leaks(args.root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            json.dumps(
                {
                    "ok": report["ok"],
                    "private_field_leak_count": report["private_field_leak_count"],
                    "scanner_false_positive_count": report["scanner_false_positive_count"],
                    "survivors": report["survivors"],
                },
                indent=2,
            )
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
