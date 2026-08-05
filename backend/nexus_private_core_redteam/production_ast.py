"""V15-L production AST mutation wrapper.

Reuses V11 production AST kill-suite against Private Core security modules.
Platform-blocked mutants are NEVER counted as PASS.
Surviving Critical mutations block V15 readiness.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_autonomy.security_mutation_v11.production_ast import (
    run_production_ast_mutation,
)
from backend.nexus_private_core_redteam.constants import (
    PRODUCTION_AST_REQUIRED_DETECT_KILLS,
    PRODUCTION_MUTATION_TARGETS,
)


def run_v15_production_ast_campaign(root: Path | None = None) -> dict[str, Any]:
    """Execute production AST mutation; classify platform-blocked ≠ PASS."""
    raw = run_production_ast_mutation(root=root)
    results = list(raw.get("results") or [])

    killed = int(raw.get("killed_count") or raw.get("killed") or 0)
    survivors = int(raw.get("survivor_count") or raw.get("survivors") or 0)
    equivalent = int(raw.get("equivalent_count") or raw.get("equivalent") or 0)
    errors = int(raw.get("error_count") or raw.get("errors") or 0)

    platform_blocked: list[dict[str, Any]] = []
    required_kill_status: dict[str, str] = {}
    for r in results:
        mid = str(r.get("mutant_id") or "")
        status = str(r.get("status") or "")
        detail = str(r.get("detail") or "").lower()
        if status == "survived" or (
            status not in {"killed", "equivalent"}
            and any(t in detail for t in ("platform", "unarmed", "env_blocked", "import"))
        ):
            if any(t in detail for t in ("platform", "unarmed", "env_blocked")):
                platform_blocked.append(
                    {
                        "mutant_id": mid,
                        "status": "platform_blocked_not_pass",
                        "detail": r.get("detail"),
                    }
                )
        if mid in PRODUCTION_AST_REQUIRED_DETECT_KILLS:
            required_kill_status[mid] = status

    missing_required = [
        mid
        for mid in PRODUCTION_AST_REQUIRED_DETECT_KILLS
        if required_kill_status.get(mid) != "killed"
        and mid not in {r.get("mutant_id") for r in results if r.get("status") == "equivalent"}
    ]
    required_not_killed = [
        mid
        for mid, st in required_kill_status.items()
        if st not in {"killed", "equivalent"}
    ]

    unresolved_blockers: list[str] = []
    for pb in platform_blocked:
        unresolved_blockers.append(f"platform_blocked:{pb['mutant_id']}")
    for mid in required_not_killed:
        unresolved_blockers.append(f"required_mutant_not_killed:{mid}")
    if survivors > 0:
        unresolved_blockers.append(f"production_ast_survivors:{survivors}")

    platform_blocked_pass_count = 0  # invariant: always 0
    passed = (
        survivors == 0
        and errors == 0
        and not platform_blocked
        and not required_not_killed
        and platform_blocked_pass_count == 0
    )

    return {
        "campaign": "v15_production_ast_mutation",
        "targets": list(PRODUCTION_MUTATION_TARGETS),
        "required_detect_kills": list(PRODUCTION_AST_REQUIRED_DETECT_KILLS),
        "killed": killed,
        "survivors": survivors,
        "equivalent": equivalent,
        "errors": errors,
        "platform_blocked_count": len(platform_blocked),
        "platform_blocked": platform_blocked,
        "platform_blocked_pass_count": platform_blocked_pass_count,
        "required_kill_status": required_kill_status,
        "missing_required": missing_required,
        "unresolved_blockers": unresolved_blockers,
        "passed": passed,
        "results": results,
        "raw_summary": {
            k: raw.get(k)
            for k in (
                "killed_count",
                "survivor_count",
                "equivalent_count",
                "error_count",
                "mutant_total",
                "required_detect_kills_ok",
            )
            if k in raw
        },
    }
