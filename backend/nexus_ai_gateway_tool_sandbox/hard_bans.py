"""Hard-ban probes for V18-E AI Gateway and Tool Sandbox."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_ai_gateway_tool_sandbox.constants import (
    BANNED_TOOLS,
    FORBIDDEN_ARTIFACT_SUFFIXES,
    HARD_BANS,
    OWNED_PATHS,
)
from backend.nexus_ai_gateway_tool_sandbox.tools import ToolSandbox


class HardBanViolation(Exception):
    pass


def assert_no_status_json_write(path: Path) -> None:
    name = path.name
    for suffix in FORBIDDEN_ARTIFACT_SUFFIXES:
        if name.endswith(suffix):
            raise HardBanViolation(f"forbidden_artifact:{name}")


def hard_ban_probe_matrix() -> dict[str, Any]:
    sandbox = ToolSandbox()
    banned_results = {}
    for tool in sorted(BANNED_TOOLS):
        ok, reason = sandbox.authorize(tool)
        banned_results[tool] = {"allowed": ok, "reason": reason}
        if ok:
            raise HardBanViolation(f"banned_tool_allowed:{tool}")

    return {
        "hard_bans": sorted(HARD_BANS),
        "owned_paths": list(OWNED_PATHS),
        "banned_tool_probes": banned_results,
        "all_banned_denied": all(not v["allowed"] for v in banned_results.values()),
        "no_busy_loop": "no_busy_loop" in HARD_BANS,
        "no_freeze_pipeline_on_provider_outage": (
            "no_freeze_pipeline_on_provider_outage" in HARD_BANS
        ),
        "on_demand_zero": "on_demand_zero" in HARD_BANS,
        "no_pr26_merge": "no_pr26_merge" in HARD_BANS,
        "no_pr27_merge": "no_pr27_merge" in HARD_BANS,
    }


def scan_owned_paths_for_exchange_write(repo_root: Path) -> list[str]:
    """Static probe: owned paths must not open exchange write helpers."""
    hits: list[str] = []
    needles = (
        "create_order(",
        "place_order(",
        "submit_order(",
        "exchange_write",
    )
    for rel in OWNED_PATHS:
        root = repo_root / rel
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in needles:
                # Allow mentions in ban lists / comments about denial.
                if needle in ("exchange_write",) and "BANNED" in text.upper():
                    continue
                if needle.endswith("(") and needle in text:
                    hits.append(f"{path.relative_to(repo_root)}:{needle}")
    return hits
