"""Hard-ban scans for PUB18-C Founder Live Operations."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.nexus_pub18_founder_live_ops.constants import (
    ALLOWED_CONTROLS,
    BANNED_CONTROLS,
    HARD_BANS,
    OWNED_PATHS,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _iter_owned_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_file():
            out.append(target)
        elif target.is_dir():
            for p in target.rglob("*"):
                if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                    out.append(p)
    return out


def _is_ban_context(text: str, start: int, end: int) -> bool:
    ctx = text[max(0, start - 220) : min(len(text), end + 120)].lower()
    return any(
        tok in ctx
        for tok in (
            "banned",
            "forbidden",
            "hard_ban",
            "hard ban",
            "must never",
            "must not",
            "reject",
            "refuse",
            "assert",
            "no_",
            "error:",
            "banned_controls",
            "is_banned",
            "banned_control",
        )
    )


# Patterns that indicate a banned control is being *exposed as actionable*.
_ACTIONABLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "trade_now",
        re.compile(
            r"""(?ix)
            (?:control|action|id)\s*[:=]\s*['\"]trade[_ ]?now['\"]
            | \bonClick\s*=\s*\{[^}]*trade[_ ]?now
            | ['\"]trade_now['\"]\s*,
            """
        ),
    ),
    (
        "override_risk",
        re.compile(
            r"""(?ix)
            (?:control|action|id)\s*[:=]\s*['\"]override[_ ]?risk['\"]
            | \bonClick\s*=\s*\{[^}]*override[_ ]?risk
            """
        ),
    ),
    (
        "force_long",
        re.compile(
            r"""(?ix)
            (?:control|action|id)\s*[:=]\s*['\"]force[_ ]?long['\"]
            | \bonClick\s*=\s*\{[^}]*force[_ ]?long
            """
        ),
    ),
    (
        "force_short",
        re.compile(
            r"""(?ix)
            (?:control|action|id)\s*[:=]\s*['\"]force[_ ]?short['\"]
            | \bonClick\s*=\s*\{[^}]*force[_ ]?short
            """
        ),
    ),
    (
        "change_leverage",
        re.compile(
            r"""(?ix)
            (?:control|action|id)\s*[:=]\s*['\"]change[_ ]?leverage['\"]
            | \bonClick\s*=\s*\{[^}]*change[_ ]?leverage
            """
        ),
    ),
    (
        "enable_mainnet",
        re.compile(
            r"""(?ix)
            (?:control|action|id)\s*[:=]\s*['\"]enable[_ ]?mainnet['\"]
            | \bonClick\s*=\s*\{[^}]*enable[_ ]?mainnet
            | MAINNET\s*=\s*True
            """
        ),
    ),
]


def count_banned_controls_in_owned_paths(root: Path | None = None) -> dict[str, Any]:
    """Count actionable banned-control exposures in owned paths. Target = 0."""
    root = root or _repo_root()
    hits: list[dict[str, str]] = []
    skip_names = {"hard_bans.py", "constants.py", "controls.py"}
    for path in _iter_owned_files(root):
        if path.name in skip_names:
            continue
        # Tests may assert bans — allowlist test files that only mention bans in asserts.
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for ban_id, pat in _ACTIONABLE_PATTERNS:
            for m in pat.finditer(text):
                if _is_ban_context(text, m.start(), m.end()):
                    continue
                # ALLOWED_CONTROLS tuple must never include banned ids — checked separately.
                hits.append(
                    {
                        "file": str(path.relative_to(root)).replace("\\", "/"),
                        "banned_control": ban_id,
                        "match": m.group(0)[:80],
                    }
                )
    # Structural: banned ids must not appear inside ALLOWED_CONTROLS.
    overlap = sorted(set(ALLOWED_CONTROLS) & set(BANNED_CONTROLS))
    for oid in overlap:
        hits.append(
            {
                "file": "backend/nexus_pub18_founder_live_ops/constants.py",
                "banned_control": oid,
                "match": "ALLOWED_CONTROLS∩BANNED_CONTROLS",
            }
        )
    return {
        "ok": len(hits) == 0,
        "banned_control_count": len(hits),
        "hits": hits,
        "banned_controls_catalog": list(BANNED_CONTROLS),
        "allowed_controls_catalog": list(ALLOWED_CONTROLS),
    }


def scan_exchange_write_behaviors(root: Path | None = None) -> dict[str, Any]:
    root = root or _repo_root()
    pats = [
        re.compile(r"(?i)\bplace_order\b"),
        re.compile(r"(?i)\bsubmit_order\b"),
        re.compile(r"(?i)\bEXCHANGE_WRITE\s*=\s*True\b"),
        re.compile(r"(?i)\bREAL_MONEY\s*=\s*True\b"),
    ]
    hits: list[dict[str, str]] = []
    for path in _iter_owned_files(root):
        if path.name in {"hard_bans.py", "constants.py"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in pats:
            for m in pat.finditer(text):
                if _is_ban_context(text, m.start(), m.end()):
                    continue
                hits.append(
                    {
                        "file": str(path.relative_to(root)).replace("\\", "/"),
                        "match": m.group(0),
                    }
                )
    return {"ok": len(hits) == 0, "hits": hits, "exchange_write_attempt_count": len(hits)}


def run_gate(root: Path | str | None = None) -> dict[str, Any]:
    root_path = Path(root) if root else _repo_root()
    banned = count_banned_controls_in_owned_paths(root_path)
    writes = scan_exchange_write_behaviors(root_path)
    ok = bool(banned["ok"]) and bool(writes["ok"]) and banned["banned_control_count"] == 0
    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "lane": "PUB18-C",
        "lane_name": "FOUNDER_LIVE_OPERATIONS",
        "hard_bans": list(HARD_BANS),
        "banned_control_count": banned["banned_control_count"],
        "banned_scan": banned,
        "exchange_write_scan": writes,
        "recommendation": (
            "NEXUS_PUB18_FOUNDER_LIVE_OPERATIONS_PASS"
            if ok
            else "NEXUS_PUB18_FOUNDER_LIVE_OPERATIONS_FAIL"
        ),
    }
