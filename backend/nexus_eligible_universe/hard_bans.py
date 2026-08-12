"""Hard-ban enforcement for V18-C Eligible Universe Engine."""
from __future__ import annotations

import os
from typing import Any

from backend.nexus_eligible_universe.constants import HARD_BANS


class HardBanViolation(RuntimeError):
    """Raised when a V18-C hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO": os.environ.get("DEMO", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "PR26_MERGE": os.environ.get("PR26_MERGE", "false").lower(),
        "PR27_MERGE": os.environ.get("PR27_MERGE", "false").lower(),
        "EDIT_ACCELERATION_REPORT": os.environ.get(
            "EDIT_ACCELERATION_REPORT", "false"
        ).lower(),
        "ARCHIVE_REBUILD": os.environ.get("ARCHIVE_REBUILD", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": sorted(HARD_BANS),
    }


def refuse_exchange_write() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "EXCHANGE_WRITE",
        "reason": "V18_C_HARD_BAN_NO_EXCHANGE_WRITE",
    }


def refuse_mainnet() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "MAINNET",
        "reason": "V18_C_HARD_BAN_NO_MAINNET",
    }


def refuse_demo() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "DEMO",
        "reason": "V18_C_HARD_BAN_NO_DEMO",
    }


def refuse_pr_merge(pr: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": f"PR{pr}_MERGE",
        "reason": f"V18_C_HARD_BAN_NO_PR{pr}_MERGE",
    }


def refuse_report_edit() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "ACCELERATION_REPORT_EDIT",
        "reason": "V18_C_HARD_BAN_NO_REPORT_EDIT",
    }


def refuse_archive_rebuild() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "ARCHIVE_REBUILD",
        "reason": "V18_C_HARD_BAN_NO_ARCHIVE_REBUILD",
    }


def refuse_unknown_as_eligible() -> dict[str, Any]:
    return {
        "allowed": False,
        "applied": False,
        "action": "UNKNOWN_DEFAULT_ELIGIBLE",
        "reason": "V18_C_HARD_BAN_UNKNOWN_MUST_NOT_DEFAULT_ELIGIBLE",
    }


def hard_ban_probe_matrix() -> dict[str, Any]:
    probes = {
        "exchange_write": refuse_exchange_write(),
        "mainnet": refuse_mainnet(),
        "demo": refuse_demo(),
        "pr26": refuse_pr_merge("26"),
        "pr27": refuse_pr_merge("27"),
        "report_edit": refuse_report_edit(),
        "archive_rebuild": refuse_archive_rebuild(),
        "unknown_as_eligible": refuse_unknown_as_eligible(),
    }
    all_refused = all(
        (not p.get("allowed", True)) and (not p.get("executed", False)) and (not p.get("applied", False))
        for p in probes.values()
    )
    env = env_hard_ban_guard()
    return {
        "probes": probes,
        "all_refused": all_refused,
        "env_guard": env,
    }
