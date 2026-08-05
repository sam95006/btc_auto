"""Hard-ban guards for PUB2-G Concierge app."""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from backend.nexus_customer_validation_concierge.constants import (
    ALLOWED_ENVIRONMENTS,
    FORBIDDEN_PAYLOAD_KEYS,
    HARD_BANS,
    OWNED_PATHS,
    PRIVATE_CORE_IMPORT_PREFIXES,
)
from tools.customer_validation.hard_bans import HardBanViolation


def current_environment() -> str:
    return (
        os.environ.get("NEXUS_CONCIERGE_ENV")
        or os.environ.get("NEXUS_PUBLIC_ENV")
        or os.environ.get("FLASK_ENV")
        or "local_staging"
    ).strip().lower()


def require_local_staging() -> dict[str, Any]:
    env = current_environment()
    if env not in ALLOWED_ENVIRONMENTS:
        raise HardBanViolation(
            f"HARD BAN: Concierge app local_staging_only (got env={env!r})"
        )
    if os.environ.get("NEXUS_LIVE_PUBLIC_DEPLOYMENT", "").lower() in ("1", "true", "yes"):
        raise HardBanViolation("HARD BAN: live public deployment refused in PUB2-G")
    return {"ok": True, "environment": env, "hard_bans": list(HARD_BANS)}


def assert_no_forbidden_keys(payload: Any, path: str = "$") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_l = str(key).lower()
            if key_l in FORBIDDEN_PAYLOAD_KEYS or any(
                token in key_l for token in ("api_secret", "private_key", "wallet_")
            ):
                raise HardBanViolation(f"HARD BAN: forbidden payload key {path}.{key}")
            assert_no_forbidden_keys(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            assert_no_forbidden_keys(item, f"{path}[{i}]")


def scan_owned_sources_for_private_imports(root: Path) -> list[str]:
    violations: list[str] = []
    for rel in OWNED_PATHS:
        target = root / rel
        files: list[Path]
        if target.is_file():
            files = [target]
        elif target.is_dir():
            files = sorted(target.rglob("*.py"))
        else:
            continue
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                violations.append(f"syntax:{path}:{exc}")
                continue
            for node in ast.walk(tree):
                mod = None
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mod = node.module
                if not mod:
                    continue
                for prefix in PRIVATE_CORE_IMPORT_PREFIXES:
                    if mod == prefix or mod.startswith(prefix + "."):
                        violations.append(f"{path.relative_to(root)}:{mod}")
    return violations


def refuse_status_json_write(path: Path | str) -> None:
    name = Path(path).name
    if name.endswith("_status.json") or name.endswith("_report.json"):
        raise HardBanViolation(f"HARD BAN: refusing to write {name}")
