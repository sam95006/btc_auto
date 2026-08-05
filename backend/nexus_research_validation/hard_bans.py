"""Hard-ban enforcement for V14-D robustness lab."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_research_validation.constants import HARD_BANS

BANNED_CLAIM_PATTERNS = [
    re.compile(r"(?i)\bQUALIFIED\b"),
    re.compile(r"(?i)\bPROFITABLE\b"),
    re.compile(r"(?i)WALK[_\s-]?FORWARD[_\s-]?PASS"),
    re.compile(r"(?i)OOS[_\s-]?PASS"),
    re.compile(r"(?i)\bPROMOTED\b"),
    re.compile(r"(?i)DEMO[_\s-]?READY"),
    re.compile(r"(?i)PROMOTION[_\s-]?READY"),
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
    raise HardBanViolation("HARD BAN: OOS consumption refused in V14-D")


def refuse_formal_walk_forward() -> None:
    raise HardBanViolation("HARD BAN: formal walk-forward refused in V14-D")


def refuse_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: exchange write refused in V14-D")


def refuse_auto_integrate() -> None:
    raise HardBanViolation("HARD BAN: auto-integrate refused in V14-D")


def scan_owned_paths_for_banned_claims(root: Path) -> dict[str, Any]:
    """Scan source owned paths only (not artifact echoes) for illicit claim language."""
    hits: list[dict[str, str]] = []
    code_roots = [
        "backend/nexus_research_validation/",
        "tools/research/robustness/",
        "tests/research_validation/",
    ]
    for rel in code_roots:
        target = root / rel
        if not target.exists():
            continue
        files = [
            p
            for p in target.rglob("*.py")
            if p.is_file()
        ]
        for path in files:
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
                        "none are qualification",
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
                        "qualified_label_accepted",
                        "banned_claim",
                        "denylist",
                        "deny",
                        "negative test",
                    )
                    if any(tok in ctx_l for tok in allow_tokens):
                        continue
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                            "snippet": text[m.start() : m.end() + 24],
                        }
                    )
    return {
        "schema": "v14_d_banned_claim_scan",
        "banned_claim_count": len(hits),
        "hits": hits,
        "ok": len(hits) == 0,
        "scanned_code_roots": code_roots,
    }
