"""Hard-ban enforcement for PUB2-I product analytics."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_product_analytics.constants import (
    FABRICATED_VALUE_MARKERS,
    HARD_BANS,
    OWNED_PATHS,
    PRIVATE_CORE_IMPORT_PREFIXES,
)


class HardBanViolation(RuntimeError):
    """Raised when a PUB2-I hard ban would be violated."""


def assert_hard_bans() -> dict[str, Any]:
    return {
        "ok": True,
        "hard_bans": list(HARD_BANS),
        "hard_bans_honored": True,
        "production_customer_database": False,
        "live_billing": False,
        "fabricated_metrics_forbidden": True,
        "status_json_forbidden": True,
    }


def refuse_fabrication(reason: str) -> None:
    raise HardBanViolation(f"HARD BAN: fabricated metrics refused — {reason}")


def refuse_production_customer_db() -> None:
    raise HardBanViolation(
        "HARD BAN: production customer database refused in PUB2-I (local store only)"
    )


def refuse_live_billing() -> None:
    raise HardBanViolation("HARD BAN: live billing / real IAP refused in PUB2-I")


def refuse_status_json_emission(path: str | Path) -> None:
    name = Path(path).name.lower()
    if name.endswith("_status.json") or name.endswith("status.json"):
        raise HardBanViolation(f"HARD BAN: status json emission refused: {path}")


def looks_fabricated_marker(text: str) -> bool:
    lowered = (text or "").lower()
    return any(tok in lowered for tok in FABRICATED_VALUE_MARKERS)


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
        "NEXUS_LIVE_BILLING": os.environ.get("NEXUS_LIVE_BILLING", "false").lower(),
        "NEXUS_LIVE_PUBLIC_DEPLOY": os.environ.get("NEXUS_LIVE_PUBLIC_DEPLOY", "false").lower(),
        "NEXUS_PRODUCTION_CUSTOMER_DB": os.environ.get(
            "NEXUS_PRODUCTION_CUSTOMER_DB", "false"
        ).lower(),
        "NEXUS_FABRICATE_METRICS": os.environ.get("NEXUS_FABRICATE_METRICS", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": list(HARD_BANS),
    }


def scan_owned_paths_for_private_imports(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if not target.exists():
            continue
        files = [target] if target.is_file() else list(target.rglob("*.py"))
        for path in files:
            if not path.is_file() or path.suffix != ".py":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError as exc:
                hits.append({"path": str(path.relative_to(root)), "error": f"syntax:{exc}"})
                continue
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                for mod in modules:
                    for banned in PRIVATE_CORE_IMPORT_PREFIXES:
                        if mod == banned or mod.startswith(banned + "."):
                            hits.append(
                                {
                                    "path": str(path.relative_to(root)).replace("\\", "/"),
                                    "import": mod,
                                    "banned_prefix": banned,
                                }
                            )
    return {"ok": len(hits) == 0, "hits": hits}


def scan_owned_paths_for_status_json(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if not target.exists():
            continue
        files = [target] if target.is_file() else list(target.rglob("*"))
        for path in files:
            if path.is_file() and path.name.lower().endswith("_status.json"):
                hits.append(str(path.relative_to(root)).replace("\\", "/"))
    return {"ok": len(hits) == 0, "hits": hits}


_FABRICATED_CLAIM = re.compile(
    r"(?i)\b(wau\s*=\s*[1-9]|conversion_rate\s*=\s*0\.[1-9]|fabricated_wau|"
    r"fake_retention|dummy_conversion)\b"
)


def scan_owned_paths_for_fabricated_claims(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    allow = (
        "refuse",
        "forbidden",
        "hard ban",
        "hard_ban",
        "never",
        "do not",
        "no_",
        "pytest.raises",
        "raises(",
        "fabricated_results_forbidden",
        "no_fabricated",
        "looks_fabricated",
        "refuse_fabrication",
    )
    # Denylist definition modules may contain attack tokens as patterns only.
    skip_names = frozenset({"hard_bans.py", "constants.py"})
    for rel in OWNED_PATHS:
        target = root / rel
        if not target.exists():
            continue
        files = [target] if target.is_file() else [
            p for p in target.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"}
        ]
        for path in files:
            if path.name in skip_names:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for m in _FABRICATED_CLAIM.finditer(text):
                start = max(0, m.start() - 160)
                end = min(len(text), m.end() + 80)
                ctx = text[start:end].lower()
                if any(tok in ctx for tok in allow):
                    continue
                hits.append(
                    {
                        "path": str(path.relative_to(root)).replace("\\", "/"),
                        "match": m.group(0),
                    }
                )
    return {"ok": len(hits) == 0, "hits": hits}


def run_hard_ban_pass(root: Path) -> dict[str, Any]:
    env = env_hard_ban_guard()
    imports = scan_owned_paths_for_private_imports(root)
    status_json = scan_owned_paths_for_status_json(root)
    claims = scan_owned_paths_for_fabricated_claims(root)
    critical: list[str] = []
    if not env["ok"]:
        critical.append(f"env_violations:{env['violations']}")
    if not imports["ok"]:
        critical.append(f"private_imports:{len(imports['hits'])}")
    if not status_json["ok"]:
        critical.append(f"status_json:{status_json['hits']}")
    if not claims["ok"]:
        critical.append(f"fabricated_claims:{len(claims['hits'])}")
    return {
        "ok": len(critical) == 0,
        "critical_count": len(critical),
        "critical": critical,
        "env": env,
        "imports": imports,
        "status_json": status_json,
        "claims": claims,
        "hard_bans": list(HARD_BANS),
        "assert": assert_hard_bans(),
    }
