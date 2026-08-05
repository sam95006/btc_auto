"""Hard-ban enforcement for PUB-F Real-Time Transport."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_realtime_transport.constants import (
    FORBIDDEN_ENVIRONMENTS,
    FORBIDDEN_PRIVATE_TOPICS,
    HARD_BANS,
    OWNED_PATHS,
    PRIVATE_CORE_IMPORT_PREFIXES,
)

BANNED_CLAIM_PATTERNS = [
    re.compile(r"(?i)\bPROFITABLE\b"),
    re.compile(r"(?i)PROFITABILITY[_\s-]?GUARANTEE"),
    re.compile(r"(?i)\bQUALIFIED\b"),
    re.compile(r"(?i)LIVE[_\s-]?BILLING[_\s-]?ENABLED"),
    re.compile(r"(?i)PRODUCTION[_\s-]?CUSTOMER[_\s-]?DB"),
    re.compile(r"(?i)PRIVATE[_\s-]?EVENT[_\s-]?STREAM[_\s-]?EXPOSED"),
]


class HardBanViolation(RuntimeError):
    """Raised when a hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
        "NEXUS_LIVE_BILLING": os.environ.get("NEXUS_LIVE_BILLING", "false").lower(),
        "AUTO_INTEGRATE": os.environ.get("AUTO_INTEGRATE", "false").lower(),
        "NEXUS_LIVE_PUBLIC_DEPLOY": os.environ.get("NEXUS_LIVE_PUBLIC_DEPLOY", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    env = (os.environ.get("NEXUS_REALTIME_ENV") or os.environ.get("NEXUS_ENV") or "LOCAL").strip().upper()
    if env in {"DEV", "DEVELOPMENT", "TEST", "CI"}:
        env = "LOCAL"
    if env in FORBIDDEN_ENVIRONMENTS:
        violations.append(f"FORBIDDEN_ENV:{env}")
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "environment": env,
        "violations": violations,
        "hard_bans": list(HARD_BANS),
    }


def refuse_private_topic(topic: str) -> None:
    norm = str(topic).strip().lower()
    if norm in FORBIDDEN_PRIVATE_TOPICS or norm.startswith("private.") or norm.startswith("founder."):
        raise HardBanViolation(f"HARD BAN: private event stream topic refused: {topic}")


def refuse_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: exchange write refused in PUB-F")


def refuse_live_public_deploy() -> None:
    raise HardBanViolation("HARD BAN: live public deployment refused in PUB-F")


def refuse_auto_integrate() -> None:
    raise HardBanViolation("HARD BAN: auto-integrate refused in PUB-F")


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


def scan_owned_paths_for_banned_claims(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    allow_tokens = (
        "banned",
        "hard ban",
        "hard_ban",
        "refuse_",
        "refused",
        "never",
        "do not",
        "no_",
        "forbidden",
        "denied",
        "pytest.raises",
        "raises(",
        "hardbanviolation",
    )
    for rel in OWNED_PATHS:
        target = root / rel
        if not target.exists():
            continue
        files = [target] if target.is_file() else [
            p for p in target.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"}
        ]
        for path in files:
            # Skip generated proof digests / reports that echo ban names
            name = path.name.lower()
            if name.endswith("_status.json"):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in BANNED_CLAIM_PATTERNS:
                for m in pat.finditer(text):
                    start = max(0, m.start() - 200)
                    end = min(len(text), m.end() + 120)
                    ctx = text[start:end].lower()
                    if any(tok in ctx for tok in allow_tokens):
                        continue
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "match": m.group(0),
                        }
                    )
    return {"ok": len(hits) == 0, "hits": hits}


def scan_for_private_topic_literals(root: Path) -> dict[str, Any]:
    """Ensure owned code never publishes/subscribes private topics except as deny lists."""
    hits: list[dict[str, str]] = []
    deny_context = (
        "forbidden",
        "refuse",
        "hard_ban",
        "denied",
        "ban",
        "assert",
        "frozenset",
        "hardbanviolation",
    )
    usage_context = (
        "subscribe",
        "publish",
        "open(",
        "connect",
        "emit(",
        "stream_id=",
        "topic=",
    )
    for rel in ("backend/nexus_public_realtime_transport/",):
        target = root / rel
        if not target.exists():
            continue
        for path in target.rglob("*.py"):
            # Deny-list definition module is the allow-list source of truth.
            if path.name == "constants.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            lower = text.lower()
            for topic in FORBIDDEN_PRIVATE_TOPICS:
                if topic not in lower:
                    continue
                for m in re.finditer(re.escape(topic), lower):
                    window = lower[max(0, m.start() - 100) : m.end() + 100]
                    if any(tok in window for tok in deny_context):
                        continue
                    if "forbidden_private_topics" in window or "refuse_private_topic" in window:
                        continue
                    # Only flag if it looks like an operational use.
                    if not any(tok in window for tok in usage_context):
                        continue
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "topic": topic,
                        }
                    )
    return {"ok": len(hits) == 0, "hits": hits}


def run_hard_ban_pass(root: Path) -> dict[str, Any]:
    env = env_hard_ban_guard()
    imports = scan_owned_paths_for_private_imports(root)
    claims = scan_owned_paths_for_banned_claims(root)
    topics = scan_for_private_topic_literals(root)
    critical: list[str] = []
    if not env["ok"]:
        critical.append(f"env_violations:{env['violations']}")
    if not imports["ok"]:
        critical.append(f"private_imports:{len(imports['hits'])}")
    if not claims["ok"]:
        critical.append(f"banned_claims:{len(claims['hits'])}")
    if not topics["ok"]:
        critical.append(f"private_topic_literals:{len(topics['hits'])}")
    return {
        "ok": len(critical) == 0,
        "critical_count": len(critical),
        "critical": critical,
        "env": env,
        "imports": imports,
        "claims": claims,
        "private_topics": topics,
        "hard_bans": list(HARD_BANS),
    }
