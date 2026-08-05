"""Hard-ban guards for PUB2-H security/privacy red team."""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from backend.nexus_public_security_privacy_redteam.constants import (
    FORBIDDEN_IMPORT_PREFIXES,
    HARD_BANS,
    OWNED_PATHS,
)


class HardBanViolation(RuntimeError):
    """Raised when a PUB2-H hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
        "NEXUS_PUBLIC_LIVE_BILLING": os.environ.get("NEXUS_PUBLIC_LIVE_BILLING", "false").lower(),
        "NEXUS_PUBLIC_SHARE_PRIVATE_JWT": os.environ.get(
            "NEXUS_PUBLIC_SHARE_PRIVATE_JWT", "false"
        ).lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {"ok": len(violations) == 0, "flags": flags, "violations": violations}


def assert_env_hard_bans() -> None:
    result = env_hard_ban_guard()
    if not result["ok"]:
        raise HardBanViolation(f"HARD BAN: forbidden env flags: {result['violations']}")


def refuse_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: public exchange-write path refused")


def refuse_shared_private_jwt() -> None:
    raise HardBanViolation("HARD BAN: shared private JWT issuer refused")


def refuse_status_json_artifact() -> None:
    raise HardBanViolation("HARD BAN: human-facing *_status.json artifacts refused in PUB2-H")


def scan_owned_imports(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_PATHS:
        target = root / rel
        files: list[Path] = []
        if target.is_file() and target.suffix == ".py":
            files = [target]
        elif target.is_dir():
            files = [p for p in target.rglob("*.py") if p.is_file()]
        for path in files:
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source, filename=str(path))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                for mod in modules:
                    for prefix in FORBIDDEN_IMPORT_PREFIXES:
                        if mod == prefix or mod.startswith(prefix + "."):
                            hits.append(
                                {
                                    "file": str(path.relative_to(root)).replace("\\", "/"),
                                    "module": mod,
                                }
                            )
    return {"ok": len(hits) == 0, "hits": hits}


def scan_no_status_json(root: Path) -> dict[str, Any]:
    """PUB2-H must not emit human-facing *_status.json under owned paths."""
    hits: list[str] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if not target.exists():
            continue
        if target.is_file():
            continue
        for path in target.rglob("*_status.json"):
            hits.append(str(path.relative_to(root)).replace("\\", "/"))
        for path in target.rglob("*report*.json"):
            name = path.name.lower()
            if "status" in name or name.endswith("_report.json"):
                # Allow schema constants mentioning report; block artifact files only.
                if "artifacts" in str(path).replace("\\", "/"):
                    hits.append(str(path.relative_to(root)).replace("\\", "/"))
    return {"ok": len(hits) == 0, "hits": hits, "hard_bans": sorted(HARD_BANS)}
