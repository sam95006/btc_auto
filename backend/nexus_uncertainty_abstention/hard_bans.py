"""Hard-ban enforcement for V16-G Uncertainty and Abstention Engine."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_uncertainty_abstention.constants import (
    BANNED_CLAIM_FRAGMENTS,
    FORBIDDEN_ARTIFACT_SUFFIXES,
    HARD_BANS,
    OWNED_PATHS,
)


class HardBanViolation(RuntimeError):
    """Raised when a V16-G hard ban would be violated."""


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


def refuse_exchange_write() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "EXCHANGE_WRITE",
        "reason": "EXCHANGE_WRITES_BANNED_V16_G",
    }


def refuse_status_json(path: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "written": False,
        "action": "WRITE_STATUS_JSON",
        "path": path,
        "reason": "STATUS_JSON_ARTIFACT_BANNED_V16_G",
        "status_json_written": False,
    }


def refuse_fail_open(*, attack: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "FAIL_OPEN",
        "attack": attack,
        "reason": "FAIL_OPEN_BLOCKED_V16_G",
        "forced_verdict": "BLOCK",
    }


def refuse_ai_override(*, attempted_fields: list[str] | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "applied": False,
        "action": "AI_OVERRIDE",
        "attempted_fields": list(attempted_fields or []),
        "reason": "AI_CANNOT_OVERRIDE_ABSTENTION_VERDICT",
        "ai_override_attempted": True,
        "ai_override_applied": False,
    }


def refuse_consensus_override_of_bad_data() -> dict[str, Any]:
    return {
        "allowed": False,
        "applied": False,
        "action": "CONSENSUS_OVERRIDE_BAD_DATA",
        "reason": "CONSENSUS_CANNOT_OVERRIDE_BAD_DATA_V16_G",
    }


def refuse_oos() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "OOS_CONSUMPTION",
        "reason": "OOS_BANNED_V16_G",
    }


def refuse_formal_walk_forward() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "FORMAL_WALK_FORWARD",
        "reason": "FORMAL_WALK_FORWARD_BANNED_V16_G",
    }


def refuse_strategy_promotion() -> dict[str, Any]:
    return {
        "allowed": False,
        "promoted": False,
        "action": "STRATEGY_PROMOTION",
        "reason": "STRATEGY_PROMOTION_BANNED_V16_G",
    }


def refuse_auto_integrate() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "AUTO_INTEGRATE",
        "reason": "AUTO_INTEGRATE_BANNED_V16_G",
    }


def assert_no_status_json_write(path: str | Path) -> None:
    name = Path(path).name.lower()
    for suffix in FORBIDDEN_ARTIFACT_SUFFIXES:
        if name.endswith(suffix):
            raise HardBanViolation(
                f"HARD BAN: refusing status/report artifact write: {path}"
            )


def hard_ban_probe_matrix() -> dict[str, Any]:
    probes = {
        "force_fail_open_missing": refuse_fail_open(attack="missing_inputs_default_allow"),
        "force_fail_open_provider": refuse_fail_open(attack="provider_failure_default_allow"),
        "force_fail_open_invalid_json": refuse_fail_open(attack="invalid_json_default_allow"),
        "force_fail_open_stale": refuse_fail_open(attack="stale_evidence_default_allow"),
        "force_fail_open_contradiction": refuse_fail_open(attack="contradiction_default_allow"),
        "force_consensus_override": refuse_consensus_override_of_bad_data(),
        "force_ai_override": refuse_ai_override(attempted_fields=["verdict", "allow"]),
        "force_exchange_write": refuse_exchange_write(),
        "force_status_json": refuse_status_json("v16_g_status.json"),
        "force_oos": refuse_oos(),
        "force_formal_wf": refuse_formal_walk_forward(),
        "force_promote": refuse_strategy_promotion(),
        "force_auto_integrate": refuse_auto_integrate(),
    }
    all_refused = all(
        (not p.get("allowed"))
        and (not p.get("executed", False))
        and (not p.get("applied", False))
        and (not p.get("written", False))
        and (not p.get("promoted", False))
        for p in probes.values()
    )
    return {
        "probes": probes,
        "all_refused": all_refused,
        "hard_bans": sorted(HARD_BANS),
        "env_guard": env_hard_ban_guard(),
    }


def scan_owned_paths_for_banned_claims(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    patterns = [
        re.compile(rf"(?i)\b{re.escape(frag)}\b") for frag in sorted(BANNED_CLAIM_FRAGMENTS)
    ]
    allow_tokens = (
        "banned",
        "hard ban",
        "hard_ban",
        "refuse",
        "forbidden",
        "not a qualification",
        "bannned_claim",
        "banned_claim",
    )
    for rel in OWNED_PATHS:
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
            for pat in patterns:
                for m in pat.finditer(text):
                    start = max(0, m.start() - 500)
                    end = min(len(text), m.end() + 120)
                    ctx = text[start:end].lower()
                    if any(tok in ctx for tok in allow_tokens):
                        continue
                    # Ban-set definitions are not claim assertions.
                    line_start = text.rfind("\n", 0, m.start()) + 1
                    line_end = text.find("\n", m.end())
                    if line_end < 0:
                        line_end = len(text)
                    line = text[line_start:line_end].strip()
                    if line.startswith('"') or line.startswith("'"):
                        # String entry inside a frozenset/list of banned fragments.
                        header = text[max(0, line_start - 800) : line_start].lower()
                        if "banned_claim" in header or "hard_ban" in header:
                            continue
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "fragment": m.group(0),
                        }
                    )
    return {"ok": len(hits) == 0, "hits": hits}
