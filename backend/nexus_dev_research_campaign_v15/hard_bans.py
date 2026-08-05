"""Hard-ban enforcement for V15-C real development research campaign."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_dev_research_campaign_v15.constants import (
    HARD_BANS,
    OOS_RESERVED_END_MS,
    OOS_RESERVED_START_MS,
    OWNED_PATHS,
)

BANNED_CLAIM_PATTERNS = [
    re.compile(r"(?i)\bQUALIFIED\b"),
    re.compile(r"(?i)\bPROFITABLE\b"),
    re.compile(r"(?i)WALK[_\s-]?FORWARD[_\s-]?PASS"),
    re.compile(r"(?i)OOS[_\s-]?PASS"),
    re.compile(r"(?i)\bPROMOTED\b"),
    re.compile(r"(?i)DEMO[_\s-]?READY"),
    re.compile(r"(?i)PROMOTION[_\s-]?READY"),
    re.compile(r"(?i)stable\s+profitabilit"),
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
        "FORMAL_WALK_FORWARD": os.environ.get("FORMAL_WALK_FORWARD", "false").lower(),
        "OOS_EXECUTE": os.environ.get("OOS_EXECUTE", "false").lower(),
        "OOS_CONSUME": os.environ.get("OOS_CONSUME", "false").lower(),
        "AUTO_INTEGRATE": os.environ.get("AUTO_INTEGRATE", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": sorted(HARD_BANS),
    }


def refuse_oos_consume() -> None:
    raise HardBanViolation("HARD BAN: OOS consumption refused in V15-C")


def refuse_formal_walk_forward() -> None:
    raise HardBanViolation("HARD BAN: formal walk-forward refused in V15-C")


def refuse_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: exchange write refused in V15-C")


def refuse_auto_integrate() -> None:
    raise HardBanViolation("HARD BAN: auto-integrate refused in V15-C")


def assert_interval_not_oos(start_ms: int, end_ms: int) -> None:
    """Fail closed if requested interval overlaps untouched OOS reservation."""
    if end_ms < start_ms:
        raise HardBanViolation("HARD BAN: invalid interval end < start")
    # overlap with [OOS_RESERVED_START_MS, OOS_RESERVED_END_MS]
    if start_ms <= OOS_RESERVED_END_MS and end_ms >= OOS_RESERVED_START_MS:
        raise HardBanViolation(
            f"HARD BAN: interval overlaps untouched OOS "
            f"[{OOS_RESERVED_START_MS},{OOS_RESERVED_END_MS}]"
        )


def scan_owned_paths_for_banned_claims(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    code_roots = [p for p in OWNED_PATHS if not p.endswith(".json") and "artifacts/" not in p]
    for rel in code_roots:
        target = root / rel
        if not target.exists():
            continue
        for path in target.rglob("*.py"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in BANNED_CLAIM_PATTERNS:
                for m in pat.finditer(text):
                    start = max(0, m.start() - 400)
                    end = min(len(text), m.end() + 200)
                    ctx_l = text[start:end].lower()
                    allow_tokens = (
                        "banned",
                        "hard ban",
                        "hard_ban",
                        "not a qualification",
                        "allowed_labels",
                        "banned_label",
                        "banned_label_fragments",
                        "do not",
                        "never",
                        "refused",
                        "refuse_",
                        "no formal",
                        "no oos",
                        "qualification_claim",
                        "assert_label_allowed",
                        "pytest.raises",
                        "raises(valueerror)",
                        "not in allowed_labels",
                        "not_qualified",
                        "development_promising_not_qualified",
                        "banned_claim",
                        "denylist",
                        "deny",
                        "negative test",
                        "no stable profitabilit",
                        "do not claim stable",
                        "do not emit qualified",
                        "no qualified",
                        "never qualification",
                        "never emits qualification",
                    )
                    if any(tok in ctx_l for tok in allow_tokens):
                        continue
                    # Allow the exact allowed label token DEVELOPMENT_PROMISING_NOT_QUALIFIED
                    window = text[max(0, m.start() - 40) : m.end() + 40]
                    if "DEVELOPMENT_PROMISING_NOT_QUALIFIED" in window and m.group(0).upper() == "QUALIFIED":
                        continue
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                            "snippet": text[m.start() : m.end() + 24],
                        }
                    )
    return {
        "schema": "v15_c_banned_claim_scan",
        "banned_claim_count": len(hits),
        "hits": hits,
        "ok": len(hits) == 0,
        "scanned_code_roots": code_roots,
    }


def assert_no_status_json(artifact_dir: Path) -> dict[str, Any]:
    """V15-C hard ban: no *_status.json files under owned artifact dir."""
    offenders: list[str] = []
    if artifact_dir.exists():
        for p in artifact_dir.rglob("*status.json"):
            offenders.append(str(p).replace("\\", "/"))
        for p in artifact_dir.rglob("*_status.json"):
            path_s = str(p).replace("\\", "/")
            if path_s not in offenders:
                offenders.append(path_s)
    return {
        "ok": len(offenders) == 0,
        "offenders": offenders,
        "rule": "no_*_status.json",
    }
