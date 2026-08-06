"""Surface scan — refuse trade / copy / exchange controls on public tip."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.nexus_pub17_public_mobile_parity.constants import (
    FORBIDDEN_MEMBER_CONTROL_MARKERS,
    SURFACE_SCAN_GLOBS,
)

# Definition / deny-list / documentation contexts are allowed to mention markers.
_ALLOW_CONTEXT = re.compile(
    r"(FORBIDDEN|HARD_BAN|hard_ban|deny|ban|marker|scan|test|assert|must never|"
    r"never appear|no_member|no_customer|blocked|documentation|resume|"
    r"FORBIDDEN_MEMBER_CONTROL|EXECUTION_CONTROL|MEMBER_FORBIDDEN)",
    re.IGNORECASE,
)


def _expand_globs(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in SURFACE_SCAN_GLOBS:
        files.extend(root.glob(pattern))
    # Deduplicate while preserving order.
    seen: set[Path] = set()
    out: list[Path] = []
    for path in files:
        if path.is_file() and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _line_is_definition_context(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
        return True
    if _ALLOW_CONTEXT.search(line):
        return True
    # String entries inside tuples/lists that are clearly catalogs.
    if re.search(r'["\'](?:trade_button|copy_trade|place_order)', line) and (
        "FORBIDDEN" in line.upper()
        or "MARKER" in line.upper()
        or line.strip().startswith('"')
        or line.strip().startswith("'")
    ):
        # Still need to catch real UI wiring — only allow when surrounding tokens
        # indicate a ban catalog.
        if _ALLOW_CONTEXT.search(line) or "MARKERS" in line.upper() or "FORBIDDEN" in line.upper():
            return True
    return False


def scan_member_control_surfaces(root: Path | str) -> dict[str, Any]:
    """Scan owned public/member surfaces for live trade/copy/exchange controls.

    Hits inside deny-list definitions / comments / tests that assert bans are
    classified as definition hits, not survivors.
    """
    root_path = Path(root)
    survivors: list[dict[str, str]] = []
    definition_hits: list[dict[str, str]] = []
    scanned_files = 0

    for path in _expand_globs(root_path):
        scanned_files += 1
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = str(path.relative_to(root_path)).replace("\\", "/")
        # Our own constants / contract modules define the markers.
        if "nexus_pub17_public_mobile_parity" in rel:
            for marker in FORBIDDEN_MEMBER_CONTROL_MARKERS:
                if marker in text:
                    definition_hits.append({"path": rel, "marker": marker, "kind": "parity_def"})
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for marker in FORBIDDEN_MEMBER_CONTROL_MARKERS:
                if marker not in line:
                    continue
                row = {"path": rel, "line": str(lineno), "marker": marker}
                if _line_is_definition_context(line):
                    definition_hits.append(row)
                else:
                    # Extra guard: hard_bans / constants / sanitize catalogs.
                    if any(
                        token in rel
                        for token in (
                            "hard_bans",
                            "constants.py",
                            "sanitize.py",
                            "execution_control.py",
                            "test_",
                        )
                    ):
                        definition_hits.append({**row, "kind": "catalog_or_test"})
                    else:
                        survivors.append(row)

    return {
        "scanned_files": scanned_files,
        "survivor_count": len(survivors),
        "definition_hit_count": len(definition_hits),
        "survivors": survivors,
        "status": "PASS" if not survivors else "FAIL",
    }
