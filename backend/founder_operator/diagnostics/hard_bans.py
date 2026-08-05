"""Hard-ban scanners for UX-C Founder Operator Diagnostics."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

OWNED_PATHS: tuple[str, ...] = (
    "backend/founder_operator/diagnostics",
    "backend/api/founder_private_routes.py",
    "frontend/src/founder",
    "tests/test_founder_operator_diagnostics_v16.py",
)

MEMBER_PATH_GLOBS: tuple[str, ...] = (
    "frontend/src/pages/member",
    "frontend/src/pages/Member*.tsx",
    "frontend/src/member",
    "backend/nexus_public_auth",
    "backend/nexus_publishing_gateway",
    "backend/nexus_public_decision_cloud",
    "backend/nexus_public_live_data",
    "backend/nexus_public_realtime_transport",
    "backend/nexus_public_ui_trace",
    "backend/nexus_public_mobile_notify",
)

HARD_BANS: tuple[str, ...] = (
    "no_demo_order",
    "no_shadow_order",
    "no_exchange_write",
    "no_mainnet",
    "no_real_money",
    "no_formal_wf",
    "no_real_oos",
    "no_member_session_access",
    "no_strategy_promotion",
    "no_fabricated_live_values",
    "no_private_secrets_in_member_paths",
    "no_mainnet_shortcut",
    "no_real_trade_shortcut",
    "no_status_json_report",
    "observe_authorize_research_only",
)

BANNED_BEHAVIOR_PATTERNS = [
    re.compile(r"(?i)\bplace_order\b"),
    re.compile(r"(?i)\bsubmit_order\b"),
    re.compile(r"(?i)\bcreate_order\b"),
    re.compile(r"(?i)\bEXCHANGE_WRITE\s*=\s*True\b"),
    re.compile(r"(?i)\bMAINNET\s*=\s*True\b"),
    re.compile(r"(?i)\bREAL_MONEY\s*=\s*True\b"),
    re.compile(r"(?i)\bmainnet_shortcut\s*=\s*True\b"),
    re.compile(r"(?i)\breal_trade_shortcut\s*=\s*True\b"),
    re.compile(r"(?i)\bfabricat(?:e|ed|ing)_live\b"),
]

STATUS_JSON_WRITE_PATTERNS = [
    re.compile(r"(?i)artifacts/readiness/.+status\.json"),
    re.compile(r"(?i)write_text\([^\)]*status\.json"),
    re.compile(r"(?i)open\([^\)]*status\.json[^\)]*[\"']w"),
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _iter_files(root: Path, rel: str) -> list[Path]:
    target = root / rel
    if "*" in rel:
        return [p for p in root.glob(rel) if p.is_file()]
    if target.is_file():
        return [target]
    if target.is_dir():
        out: list[Path] = []
        for p in target.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".json"}:
                out.append(p)
        return out
    return []


def _is_ban_allowlist(text: str, start: int, end: int) -> bool:
    ctx = text[max(0, start - 180) : min(len(text), end + 80)].lower()
    return any(
        tok in ctx
        for tok in (
            "hard ban",
            "hard_ban",
            "forbidden",
            "refuse",
            "must not",
            "never",
            "assert",
            "no_exchange",
            "no_fabricat",
            "no_status_json",
            "statusjsonreport",
            "mainnetshortcut",
            "realtradeshortcut",
            "memberaccessible",
            "member_accessible",
        )
    )


def scan_owned_write_behaviors(root: Path | None = None) -> dict[str, Any]:
    root = root or _repo_root()
    hits: list[dict[str, str]] = []
    skip_names = {"hard_bans.py", "diagnostics_hard_bans.py"}
    for rel in OWNED_PATHS:
        for path in _iter_files(root, rel):
            if path.name in skip_names:
                continue
            # This file may itself scan patterns — allow when path is this module
            if path.name == "hard_bans.py" and "diagnostics" in str(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in BANNED_BEHAVIOR_PATTERNS:
                for m in pat.finditer(text):
                    if _is_ban_allowlist(text, m.start(), m.end()):
                        continue
                    hits.append(
                        {
                            "file": str(path.relative_to(root)).replace("\\", "/"),
                            "match": m.group(0),
                        }
                    )
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_exchange_write"}


def scan_no_status_json_report(root: Path | None = None) -> dict[str, Any]:
    """Owned diagnostics code must not write status JSON reports."""
    root = root or _repo_root()
    hits: list[dict[str, str]] = []
    for rel in ("backend/founder_operator/diagnostics",):
        for path in _iter_files(root, rel):
            if path.name in {"hard_bans.py", "three_pass.py"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in STATUS_JSON_WRITE_PATTERNS:
                for m in pat.finditer(text):
                    if _is_ban_allowlist(text, m.start(), m.end()):
                        continue
                    hits.append(
                        {
                            "file": str(path.relative_to(root)).replace("\\", "/"),
                            "match": m.group(0)[:100],
                        }
                    )
    # Also ensure no lane status artifact was committed under diagnostics
    art = root / "artifacts" / "readiness" / "immutable"
    if art.is_dir():
        for p in art.rglob("*founder*diagnos*"):
            if p.is_file() and p.suffix == ".json":
                hits.append(
                    {
                        "file": str(p.relative_to(root)).replace("\\", "/"),
                        "match": "status_json_artifact_present",
                    }
                )
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_status_json_report"}


def scan_member_paths_for_diagnostics(root: Path | None = None) -> dict[str, Any]:
    root = root or _repo_root()
    hits: list[dict[str, str]] = []
    needles = (
        "backend.founder_operator.diagnostics",
        "/api/nexus/founder/diagnostics",
        "fetchFounderDiagnostics",
        "FounderDiagnosticsPage",
        "NEXUS_FOUNDER_OPERATOR_DIAGNOSTICS_V16",
    )
    for rel in MEMBER_PATH_GLOBS:
        for path in _iter_files(root, rel):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for needle in needles:
                if needle in text:
                    hits.append(
                        {
                            "file": str(path.relative_to(root)).replace("\\", "/"),
                            "needle": needle,
                        }
                    )
            if path.suffix == ".py":
                try:
                    tree = ast.parse(text, filename=str(path))
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    mods: list[str] = []
                    if isinstance(node, ast.Import):
                        mods = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        mods = [node.module]
                    for mod in mods:
                        if mod.startswith("backend.founder_operator.diagnostics"):
                            hits.append(
                                {
                                    "file": str(path.relative_to(root)).replace("\\", "/"),
                                    "needle": mod,
                                }
                            )
    return {
        "ok": len(hits) == 0,
        "hits": hits,
        "ban": "no_member_session_access",
    }


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
        "FABRICATE_LIVE": os.environ.get("FABRICATE_LIVE", "false").lower(),
        "NEXUS_MAINNET_SHORTCUT": os.environ.get("NEXUS_MAINNET_SHORTCUT", "false").lower(),
        "NEXUS_REAL_TRADE_SHORTCUT": os.environ.get("NEXUS_REAL_TRADE_SHORTCUT", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {"ok": len(violations) == 0, "flags": flags, "violations": violations}


def run_hard_ban_pass(root: Path | str | None = None, *, pass_number: int = 1) -> dict[str, Any]:
    root_path = Path(root) if root else _repo_root()
    checks = {
        "env": env_hard_ban_guard(),
        "owned_behaviors": scan_owned_write_behaviors(root_path),
        "member_imports": scan_member_paths_for_diagnostics(root_path),
        "no_status_json": scan_no_status_json_report(root_path),
    }
    ok = all(bool(v.get("ok")) for v in checks.values())
    return {
        "pass_number": pass_number,
        "ok": ok,
        "hard_bans": list(HARD_BANS),
        "checks": checks,
        "lane": "UX-C",
    }
