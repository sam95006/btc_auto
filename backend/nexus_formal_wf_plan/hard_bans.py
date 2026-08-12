"""Hard-ban enforcement for V15-F Formal Walk-Forward Plan Compiler."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_formal_wf_plan.constants import HARD_BAN_FLAGS, HARD_BANS, OWNED_PATHS

BANNED_CLAIM_PATTERNS = [
    re.compile(r"(?i)\bQUALIFIED\b"),
    re.compile(r"(?i)\bPROFITABLE\b"),
    re.compile(r"(?i)WALK[_\s-]?FORWARD[_\s-]?PASS(?:ED)?"),
    re.compile(r"(?i)WALK[_\s-]?FORWARD[_\s-]?EXECUTED"),
    re.compile(r"(?i)OOS[_\s-]?PASS(?:ED)?"),
    re.compile(r"(?i)\bPROMOTED\b"),
    re.compile(r"(?i)DEMO[_\s-]?READY"),
    re.compile(r"(?i)PROMOTION[_\s-]?READY"),
]


class HardBanViolation(RuntimeError):
    """Raised when a hard ban would be violated."""


def canonical_hard_ban_flags() -> dict[str, Any]:
    """Immutable hard-ban flag snapshot — never trust caller-mutated dicts."""
    return dict(HARD_BAN_FLAGS)


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
        "FORMAL_WALK_FORWARD": os.environ.get("FORMAL_WALK_FORWARD", "false").lower(),
        "FORMAL_WALK_FORWARD_EXECUTE": os.environ.get(
            "FORMAL_WALK_FORWARD_EXECUTE", "false"
        ).lower(),
        "OOS_EXECUTE": os.environ.get("OOS_EXECUTE", "false").lower(),
        "OOS_CONSUME": os.environ.get("OOS_CONSUME", "false").lower(),
        "OOS_RESERVE": os.environ.get("OOS_RESERVE", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": list(HARD_BANS),
    }


def refuse_formal_walk_forward_execution() -> None:
    raise HardBanViolation(
        "HARD BAN: formal walk-forward execution refused in V15-F (plan compile only)"
    )


def refuse_oos_execute() -> None:
    raise HardBanViolation("HARD BAN: OOS execution refused in V15-F")


def refuse_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: exchange write refused in V15-F")


def assert_plan_not_executed(plan: dict[str, Any]) -> None:
    if plan.get("formal_walk_forward_executed") is not False:
        raise HardBanViolation(
            "HARD BAN: formal_walk_forward_executed must be false on every plan"
        )
    if plan.get("status") != "PLAN_READY_EXECUTION_BLOCKED":
        raise HardBanViolation(
            "HARD BAN: plan status must remain PLAN_READY_EXECUTION_BLOCKED"
        )
    if plan.get("executed") is True:
        raise HardBanViolation("HARD BAN: plan marked executed")


def scan_owned_paths_for_banned_claims(root: Path) -> dict[str, Any]:
    """Scan owned source paths for illicit claim language."""
    hits: list[dict[str, str]] = []
    allow_tokens = (
        "banned",
        "hard ban",
        "hard_ban",
        "refuse_",
        "refused",
        "do not",
        "never",
        "not executed",
        "execution_blocked",
        "execution blocked",
        "plan_ready_execution_blocked",
        "formal_walk_forward_executed\": false",
        "formal_walk_forward_executed=false",
        "no formal",
        "no_oos",
        "negative test",
        "pytest.raises",
        "raises(hardbanviolation)",
        "raises(valueerror)",
        "denylist",
        "deny",
        "assert_",
        "must be false",
        "must remain",
        "banned_claim",
        "allowed_labels",
    )
    code_roots = [p for p in OWNED_PATHS if not p.startswith("artifacts/")]
    for rel in code_roots:
        target = root / rel
        if not target.exists():
            continue
        files = (
            [p for p in target.rglob("*.py") if p.is_file()]
            if target.is_dir()
            else ([target] if target.suffix == ".py" else [])
        )
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
        "schema": "v15_f_banned_claim_scan",
        "banned_claim_count": len(hits),
        "hits": hits,
        "ok": len(hits) == 0,
        "scanned_code_roots": code_roots,
    }
