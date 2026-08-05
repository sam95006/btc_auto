"""Hard-ban enforcement for Public Decision Cloud (PUB-B) — two-pass scans."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_decision_cloud.constants import (
    EXCHANGE_API_MARKERS,
    HARD_BANS,
    OWNED_PATHS,
    PRIVATE_CORE_IMPORT_PREFIXES,
)

# Trading / mutation verbs banned in owned Decision Cloud source (allowlist of ban docs)
BANNED_BEHAVIOR_PATTERNS = [
    re.compile(r"(?i)\bplace_order\b"),
    re.compile(r"(?i)\bsubmit_order\b"),
    re.compile(r"(?i)\bcreate_order\b"),
    re.compile(r"(?i)\bexecute_trade\b"),
    re.compile(r"(?i)\bcopy_trad(?:e|ing)\b"),
    re.compile(r"(?i)\bEXCHANGE_WRITE\s*=\s*True\b"),
    re.compile(r"(?i)\bMAINNET\s*=\s*True\b"),
    re.compile(r"(?i)\bREAL_MONEY\s*=\s*True\b"),
]


class HardBanViolation(RuntimeError):
    """Raised when a PUB-B hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
        "CUSTOMER_TRADING": os.environ.get("CUSTOMER_TRADING", "false").lower(),
        "AUTO_ORDERS": os.environ.get("AUTO_ORDERS", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": list(HARD_BANS),
    }


def refuse_customer_trading() -> None:
    raise HardBanViolation("HARD BAN: customer trading refused in PUB-B Decision Cloud")


def refuse_exchange_api() -> None:
    raise HardBanViolation("HARD BAN: exchange API calls refused in PUB-B Decision Cloud")


def refuse_private_core_import() -> None:
    raise HardBanViolation("HARD BAN: private-core direct imports refused in PUB-B Decision Cloud")


def refuse_order_placement() -> None:
    raise HardBanViolation("HARD BAN: order placement refused in PUB-B Decision Cloud")


def _owned_py_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_file() and target.suffix == ".py":
            files.append(target)
            continue
        if target.is_dir():
            files.extend(p for p in target.rglob("*.py") if p.is_file())
    return sorted(set(files))


def _is_allowlisted_ban_context(text: str, match_start: int, match_end: int) -> bool:
    start = max(0, match_start - 220)
    end = min(len(text), match_end + 120)
    ctx = text[start:end].lower()
    allow_tokens = (
        "hard ban",
        "hard_ban",
        "banned",
        "refuse_",
        "no_exchange",
        "no_customer",
        "never",
        "must not",
        "forbidden",
        "violation",
        "assert",
        "raise hardban",
    )
    return any(tok in ctx for tok in allow_tokens)


def scan_imports(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _owned_py_files(root):
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for mod in modules:
                for prefix in PRIVATE_CORE_IMPORT_PREFIXES:
                    if mod == prefix or mod.startswith(prefix + "."):
                        hits.append(
                            {
                                "file": str(path.relative_to(root)).replace("\\", "/"),
                                "module": mod,
                                "prefix": prefix,
                            }
                        )
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_private_core_direct_imports"}


def scan_exchange_markers(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _owned_py_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for marker in EXCHANGE_API_MARKERS:
            idx = 0
            while True:
                found = text.find(marker, idx)
                if found < 0:
                    break
                if not _is_allowlisted_ban_context(text, found, found + len(marker)):
                    # EXCHANGE_API_MARKERS listing in constants is intentional documentation
                    rel = str(path.relative_to(root)).replace("\\", "/")
                    if rel.endswith("constants.py") and "EXCHANGE_API_MARKERS" in text[max(0, found - 80) : found + 80]:
                        idx = found + len(marker)
                        continue
                    if rel.endswith("hard_bans.py"):
                        idx = found + len(marker)
                        continue
                    hits.append({"file": rel, "marker": marker})
                idx = found + len(marker)
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_exchange_apis"}


def scan_banned_behaviors(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _owned_py_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in BANNED_BEHAVIOR_PATTERNS:
            for m in pat.finditer(text):
                if _is_allowlisted_ban_context(text, m.start(), m.end()):
                    continue
                hits.append(
                    {
                        "file": str(path.relative_to(root)).replace("\\", "/"),
                        "match": m.group(0),
                    }
                )
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_customer_trading"}


def run_hard_ban_pass(root: Path | str, *, pass_number: int) -> dict[str, Any]:
    root_path = Path(root)
    env = env_hard_ban_guard()
    imports = scan_imports(root_path)
    exchange = scan_exchange_markers(root_path)
    behaviors = scan_banned_behaviors(root_path)
    checks = {
        "env": env,
        "imports": imports,
        "exchange_markers": exchange,
        "behaviors": behaviors,
    }
    ok = all(bool(v.get("ok")) for v in checks.values())
    return {
        "pass_number": pass_number,
        "ok": ok,
        "hard_bans": list(HARD_BANS),
        "checks": checks,
        "owned_paths": list(OWNED_PATHS),
    }


def run_two_passes(root: Path | str) -> dict[str, Any]:
    p1 = run_hard_ban_pass(root, pass_number=1)
    p2 = run_hard_ban_pass(root, pass_number=2)
    return {
        "ok": bool(p1["ok"] and p2["ok"]),
        "passes": [p1, p2],
        "pass_count": 2,
        "hard_bans_intact": bool(p1["ok"] and p2["ok"]),
        "lane": "PUB-B",
    }
