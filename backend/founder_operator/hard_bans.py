"""Hard-ban + member-path secret scans for Founder Operator live binding (PUB2-D)."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

OWNED_PATHS: tuple[str, ...] = (
    "backend/founder_operator",
    "backend/api/founder_private_routes.py",
    "frontend/src/founder",
    "tests/test_founder_operator_ui_v1.py",
    "tests/test_founder_operator_live_binding_v2.py",
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
)

FORBIDDEN_MEMBER_IMPORTS: tuple[str, ...] = (
    "backend.founder_operator",
    "frontend/src/founder",
)

SECRET_KEY_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|api[_-]?secret|private[_-]?key|wallet[_-]?address|"
    r"exchange[_-]?credentials|lesson[_-]?memory[_-]?raw)\b"
)

BANNED_BEHAVIOR_PATTERNS = [
    re.compile(r"(?i)\bplace_order\b"),
    re.compile(r"(?i)\bsubmit_order\b"),
    re.compile(r"(?i)\bcreate_order\b"),
    re.compile(r"(?i)\bEXCHANGE_WRITE\s*=\s*True\b"),
    re.compile(r"(?i)\bMAINNET\s*=\s*True\b"),
    re.compile(r"(?i)\bREAL_MONEY\s*=\s*True\b"),
    re.compile(r"(?i)\bfabricat(?:e|ed|ing)_live\b"),
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


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
            "fabricate_live",
            "memberAccessible",
            "member_accessible",
            "prefer_simulated",
            "explicit simulated",
        )
    )


def scan_owned_write_behaviors(root: Path | None = None) -> dict[str, Any]:
    root = root or _repo_root()
    hits: list[dict[str, str]] = []
    skip_names = {"hard_bans.py"}
    for rel in OWNED_PATHS:
        for path in _iter_files(root, rel):
            if path.name in skip_names:
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


def scan_member_paths_for_founder_imports(root: Path | None = None) -> dict[str, Any]:
    """Member / public product paths must not import Founder operator live bindings."""
    root = root or _repo_root()
    hits: list[dict[str, str]] = []
    needles = (
        "backend.founder_operator",
        "founder_operator.live_bindings",
        "founder_operator.snapshot",
        "/api/nexus/founder/operator",
        "fetchFounderOperator",
        "FounderOperatorPage",
        "FounderOperatorShell",
    )
    for rel in MEMBER_PATH_GLOBS:
        for path in _iter_files(root, rel):
            # privacy page may mention keys as banned topics — allowlisted separately
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
            # AST import scan for python member/public modules
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
                        if mod == "backend.founder_operator" or mod.startswith(
                            "backend.founder_operator."
                        ):
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


def scan_member_paths_for_secret_literals(root: Path | None = None) -> dict[str, Any]:
    """Member paths must not embed private secret field assignments from founder surfaces."""
    root = root or _repo_root()
    hits: list[dict[str, str]] = []
    # Look for assignment-like secret materialization, not educational mentions.
    assign_pat = re.compile(
        r"(?i)(apiKey|api_key|private_key|privateKey|walletAddress|wallet_address|"
        r"exchange_credentials|exchangeCredentials)\s*[:=]\s*['\"][^'\"]+['\"]"
    )
    for rel in MEMBER_PATH_GLOBS:
        for path in _iter_files(root, rel):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in assign_pat.finditer(text):
                if _is_ban_allowlist(text, m.start(), m.end()):
                    continue
                hits.append(
                    {
                        "file": str(path.relative_to(root)).replace("\\", "/"),
                        "match": m.group(0)[:80],
                    }
                )
    return {
        "ok": len(hits) == 0,
        "hits": hits,
        "ban": "no_private_secrets_in_member_paths",
    }


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
        "FABRICATE_LIVE": os.environ.get("FABRICATE_LIVE", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {"ok": len(violations) == 0, "flags": flags, "violations": violations}


def run_hard_ban_pass(root: Path | str | None = None, *, pass_number: int = 1) -> dict[str, Any]:
    root_path = Path(root) if root else _repo_root()
    checks = {
        "env": env_hard_ban_guard(),
        "owned_behaviors": scan_owned_write_behaviors(root_path),
        "member_imports": scan_member_paths_for_founder_imports(root_path),
        "member_secrets": scan_member_paths_for_secret_literals(root_path),
    }
    ok = all(bool(v.get("ok")) for v in checks.values())
    return {
        "pass_number": pass_number,
        "ok": ok,
        "hard_bans": list(HARD_BANS),
        "checks": checks,
        "lane": "PUB2-D",
    }


def run_three_passes(root: Path | str | None = None) -> dict[str, Any]:
    passes = [run_hard_ban_pass(root, pass_number=i) for i in (1, 2, 3)]
    return {
        "ok": all(p["ok"] for p in passes),
        "passes": passes,
        "pass_count": 3,
        "lane": "PUB2-D",
        "lane_name": "FOUNDER_OPERATOR_UI_LIVE_BINDING",
    }
