"""Hard-ban enforcement for PUB2-B — three-pass scans."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.nexus_public_v2_live_binding.constants import (
    EXCHANGE_WRITE_MARKERS,
    HARD_BANS,
    OWNED_PATHS,
)
from backend.nexus_public_v2_live_binding.source_scan import (
    scan_forbidden_imports,
    scan_hardcoded_live_in_frontend,
    scan_status_json_writes,
)


class HardBanViolation(RuntimeError):
    """Raised when a PUB2-B hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "CUSTOMER_TRADING": os.environ.get("CUSTOMER_TRADING", "false").lower(),
        "FABRICATE_LIVE": os.environ.get("FABRICATE_LIVE", "false").lower(),
        "DEMO_AS_LIVE": os.environ.get("DEMO_AS_LIVE", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {"ok": len(violations) == 0, "flags": flags, "violations": violations}


def refuse_demo_as_live() -> None:
    raise HardBanViolation("HARD BAN: DEMO/FIXTURE must not merge into LIVE bindings (PUB2-B)")


def refuse_fabricated_live() -> None:
    raise HardBanViolation("HARD BAN: fabricated live values refused (PUB2-B)")


def refuse_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: exchange write refused (PUB2-B)")


def refuse_private_core() -> None:
    raise HardBanViolation("HARD BAN: private-core exposure refused (PUB2-B)")


def refuse_pr_merge() -> None:
    raise HardBanViolation("HARD BAN: PR26/PR27 merge refused (PUB2-B)")


def _owned_py(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_file() and target.suffix == ".py":
            files.append(target)
        elif target.is_dir():
            files.extend(p for p in target.rglob("*.py") if p.is_file())
    return sorted(set(files))


def _allowlisted(text: str, start: int, end: int) -> bool:
    ctx = text[max(0, start - 200) : min(len(text), end + 100)].lower()
    tokens = (
        "hard ban",
        "hard_ban",
        "refuse_",
        "banned",
        "forbidden",
        "must not",
        "never",
        "no_exchange",
        "no_fabricat",
        "violation",
        "assert",
    )
    return any(t in ctx for t in tokens)


def scan_write_markers(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _owned_py(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel.endswith("constants.py") or rel.endswith("hard_bans.py"):
            continue
        for marker in EXCHANGE_WRITE_MARKERS:
            idx = 0
            while True:
                found = text.find(marker, idx)
                if found < 0:
                    break
                if not _allowlisted(text, found, found + len(marker)):
                    hits.append({"file": rel, "marker": marker})
                idx = found + len(marker)
    return {"ok": len(hits) == 0, "hits": hits}


def scan_demo_merge(root: Path) -> dict[str, Any]:
    """LIVE binder must refuse FIXTURE/DEMO merge."""
    binder = root / "backend" / "nexus_public_v2_live_binding" / "binder.py"
    try:
        text = binder.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return {"ok": False, "notes": [str(exc)]}
    required = (
        "LIVE-only",
        "demo_data",
        "FIXTURE",
        "DEMO",
    )
    missing = [t for t in required if t not in text]
    # Must raise on non-LIVE
    has_refuse = "DEMO/FIXTURE merge refused" in text or "refused" in text
    return {"ok": len(missing) == 0 and has_refuse, "missing": missing, "has_refuse": has_refuse}


def run_hard_ban_pass(root: Path | str, *, pass_number: int) -> dict[str, Any]:
    root_path = Path(root)
    checks = {
        "env": env_hard_ban_guard(),
        "imports": scan_forbidden_imports(root_path),
        "write_markers": scan_write_markers(root_path),
        "demo_merge": scan_demo_merge(root_path),
        "hardcoded_frontend": scan_hardcoded_live_in_frontend(root_path),
        "status_json": scan_status_json_writes(root_path),
    }
    ok = all(bool(v.get("ok")) for v in checks.values())
    return {
        "pass_number": pass_number,
        "ok": ok,
        "hard_bans": list(HARD_BANS),
        "checks": checks,
    }


def run_three_passes(root: Path | str) -> dict[str, Any]:
    passes = [run_hard_ban_pass(root, pass_number=i) for i in (1, 2, 3)]
    ok = all(bool(p["ok"]) for p in passes)
    return {
        "ok": ok,
        "pass_count": 3,
        "passes": passes,
        "hard_bans_intact": ok,
        "lane": "PUB2-B",
        "lane_name": "LIVE_DATA_END_TO_END_BINDING",
    }
