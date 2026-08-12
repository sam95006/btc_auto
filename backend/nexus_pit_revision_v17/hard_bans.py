"""Hard-ban enforcement for V17-D PIT / revision control."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_pit_revision_v17.constants import (
    BANNED_CLAIM_FRAGMENTS,
    HARD_BANS,
    OWNED_PATHS,
)


class HardBanViolation(RuntimeError):
    """Raised when a V17-D hard ban would be violated."""


class MissingAsKnownAtError(HardBanViolation):
    """Research queries must supply AS_KNOWN_AT."""


class TodayRevisionForPastBacktestError(HardBanViolation):
    """Ban using today's / latest revision for a past AS_KNOWN_AT backtest."""


class FutureLeakageError(HardBanViolation):
    """Revision or availability after AS_KNOWN_AT must not leak."""


class UnavailableAtTimeError(HardBanViolation):
    """Silent fill of unavailable-at-time data is banned."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "FORMAL_WALK_FORWARD": os.environ.get("FORMAL_WALK_FORWARD", "false").lower(),
        "OOS_EXECUTE": os.environ.get("OOS_EXECUTE", "false").lower(),
        "OOS_CONSUME": os.environ.get("OOS_CONSUME", "false").lower(),
        "AUTO_INTEGRATE": os.environ.get("AUTO_INTEGRATE", "false").lower(),
        "PR26_MERGE": os.environ.get("PR26_MERGE", "false").lower(),
        "PR27_MERGE": os.environ.get("PR27_MERGE", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": sorted(HARD_BANS),
    }


def refuse_missing_as_known_at() -> None:
    raise MissingAsKnownAtError(
        "no_research_query_without_as_known_at: AS_KNOWN_AT timestamp is mandatory"
    )


def refuse_today_revision_for_past_backtest(*, as_known_at: int, latest_revision_time: int) -> None:
    raise TodayRevisionForPastBacktestError(
        "no_today_revision_for_past_backtest:"
        f"as_known_at={as_known_at}<latest_revision_time={latest_revision_time}"
    )


def refuse_future_leakage(*, axis: str, value: int, as_known_at: int) -> None:
    raise FutureLeakageError(
        f"no_future_leakage:{axis}={value}>as_known_at={as_known_at}"
    )


def refuse_unavailable_silent_fill(*, series_id: str, as_known_at: int) -> None:
    raise UnavailableAtTimeError(
        f"no_unavailable_at_time_silent_fill:series={series_id}:as_known_at={as_known_at}"
    )


def refuse_exchange_write() -> dict[str, Any]:
    return {
        "allowed": False,
        "executed": False,
        "action": "EXCHANGE_WRITE",
        "reason": "EXCHANGE_WRITES_BANNED_V17_D",
    }


def refuse_report_edit() -> dict[str, Any]:
    return {
        "allowed": False,
        "written": False,
        "action": "ACCELERATION_REPORT_EDIT",
        "reason": "REPORT_EDIT_BANNED_V17_D",
    }


def hard_ban_probe_matrix() -> dict[str, Any]:
    env = env_hard_ban_guard()
    return {
        "schema": "v17_d_hard_ban_probe_matrix",
        "env_ok": env["ok"],
        "env": env,
        "exchange_write": refuse_exchange_write(),
        "report_edit": refuse_report_edit(),
        "hard_bans": list(HARD_BANS),
    }


def scan_owned_paths_for_banned_claims(repo_root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    patterns = [
        re.compile(rf"(?i){re.escape(frag)}") for frag in sorted(BANNED_CLAIM_FRAGMENTS)
    ]
    allow_tokens = (
        "banned",
        "hard ban",
        "hard_ban",
        "refuse",
        "forbidden",
        "non_claims",
        "banned_claim",
        "no formal",
        "no oos",
        "not live",
        "fixture_only",
    )
    for rel in OWNED_PATHS:
        path = repo_root / rel
        files: list[Path]
        if path.is_dir():
            files = [p for p in path.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"}]
        elif path.is_file():
            files = [path]
        else:
            continue
        for fp in files:
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in patterns:
                for m in pat.finditer(text):
                    start = max(0, m.start() - 400)
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
                        if "banned_claim" in header or "hard_ban" in header or "non_claims" in header:
                            continue
                    hits.append(
                        {
                            "path": str(fp.relative_to(repo_root)).replace("\\", "/"),
                            "fragment": m.group(0),
                        }
                    )
    return {
        "ok": len(hits) == 0,
        "hits": hits,
        "scanned_owned_paths": list(OWNED_PATHS),
    }


_AS_KNOWN_AT_RE = re.compile(r"as_known_at", re.IGNORECASE)


def require_as_known_at_in_signature(fn: Any) -> bool:
    """Lightweight check that research callables declare as_known_at."""
    code = getattr(fn, "__code__", None)
    if code is None:
        return False
    return "as_known_at" in code.co_varnames
