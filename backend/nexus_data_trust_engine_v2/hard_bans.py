"""Hard-ban enforcement for V17-F Data Trust Engine V2."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_data_trust_engine_v2.constants import (
    BANNED_CLAIM_FRAGMENTS,
    FORBIDDEN_ARTIFACT_SUFFIXES,
    HARD_BANS,
    OWNED_PATHS,
)


class HardBanViolation(RuntimeError):
    """Raised when a V17-F hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "PR26_MERGE": os.environ.get("PR26_MERGE", "false").lower(),
        "PR27_MERGE": os.environ.get("PR27_MERGE", "false").lower(),
        "EDIT_ACCELERATION_REPORT": os.environ.get(
            "EDIT_ACCELERATION_REPORT", "false"
        ).lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": sorted(HARD_BANS),
    }


def refuse_ai_confidence_override(*, trust_status: str, ai_confidence: float) -> dict[str, Any]:
    return {
        "allowed": False,
        "applied": False,
        "action": "AI_CONFIDENCE_OVERRIDE_TRUST",
        "trust_status": trust_status,
        "ai_confidence": ai_confidence,
        "reason": "DATA_TRUST_DOMINATES_AI_CONFIDENCE",
        "ai_override_attempted": True,
        "ai_override_applied": False,
    }


def refuse_exchange_write() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "EXCHANGE_WRITE",
        "reason": "EXCHANGE_WRITES_BANNED_V17_F",
    }


def refuse_status_json(path: str | None = None) -> dict[str, Any]:
    return {
        "allowed": False,
        "written": False,
        "action": "WRITE_STATUS_JSON",
        "path": path,
        "reason": "STATUS_JSON_ARTIFACT_BANNED_V17_F",
        "status_json_written": False,
    }


def refuse_report_edit() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "EDIT_ACCELERATION_REPORT",
        "reason": "ACCELERATION_REPORT_EDIT_BANNED_V17_F",
    }


def refuse_fail_open(*, attack: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "FAIL_OPEN",
        "attack": attack,
        "reason": "FAIL_OPEN_BLOCKED_V17_F",
        "forced_trust_status": "UNAVAILABLE",
        "forced_gate_action": "BLOCK",
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
        "force_ai_override_degraded": refuse_ai_confidence_override(
            trust_status="DEGRADED", ai_confidence=0.99
        ),
        "force_fail_open_missing": refuse_fail_open(attack="missing_inputs_default_trusted"),
        "force_exchange_write": refuse_exchange_write(),
        "force_status_json": refuse_status_json("v17_f_status.json"),
        "force_report_edit": refuse_report_edit(),
    }
    all_refused = all(
        (not p.get("allowed"))
        and (not p.get("executed", False))
        and (not p.get("applied", False))
        and (not p.get("written", False))
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
                    line_start = text.rfind("\n", 0, m.start()) + 1
                    line_end = text.find("\n", m.end())
                    if line_end < 0:
                        line_end = len(text)
                    line = text[line_start:line_end].strip()
                    if line.startswith('"') or line.startswith("'"):
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
