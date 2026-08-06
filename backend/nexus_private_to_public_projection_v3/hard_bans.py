"""Hard-ban probes for PUB17-C Private-to-Public Projection V3."""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from backend.nexus_private_to_public_projection_v3.allowlist import (
    ForbiddenPayloadKeyError,
    assert_allowlisted_only,
    collect_field_names,
    count_execution_controls,
    serialize_allowlist,
)
from backend.nexus_private_to_public_projection_v3.constants import (
    BANNED_PRIVATE_FIELDS,
    FAIL_RECOMMENDATION,
    HARD_BANS,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PRIVATE_CORE_IMPORT_PREFIXES,
)
from backend.nexus_private_to_public_projection_v3.fixtures import (
    adversarial_dirty_payload,
    private_core_fixture,
)
from backend.nexus_private_to_public_projection_v3.inference_redteam import (
    run_inference_redteam,
)
from backend.nexus_private_to_public_projection_v3.projector import (
    REQUIRED_PUBLIC_KEYS,
    project_private_to_public,
)


class HardBanViolation(RuntimeError):
    """Raised when a PUB17-C hard ban would be violated."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {"ok": len(violations) == 0, "flags": flags, "violations": violations}


def scan_private_core_imports(root: Path | None = None) -> list[str]:
    root = root or repo_root()
    hits: list[str] = []
    for rel in OWNED_PATHS:
        base = root / rel
        if not base.exists():
            continue
        paths = [base] if base.is_file() else list(base.rglob("*.py"))
        for path in paths:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for prefix in PRIVATE_CORE_IMPORT_PREFIXES:
                            if alias.name == prefix or alias.name.startswith(prefix + "."):
                                hits.append(f"{path}:{alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    for prefix in PRIVATE_CORE_IMPORT_PREFIXES:
                        if node.module == prefix or node.module.startswith(prefix + "."):
                            hits.append(f"{path}:{node.module}")
    return hits


def pass1_completeness() -> dict[str, Any]:
    proj = project_private_to_public(private_core_fixture())
    missing = [k for k in REQUIRED_PUBLIC_KEYS if k not in proj]
    assert_allowlisted_only(proj)
    exec_count = int(proj.get("member_execution_control_count", -1))
    ok = (
        not missing
        and exec_count == 0
        and proj.get("private_fields_included") is False
        and proj.get("raw_memory_graph") is False
    )
    return {
        "pass": 1,
        "name": "completeness",
        "ok": ok,
        "missing": missing,
        "member_execution_control_count": exec_count,
        "projection_keys": sorted(proj.keys()),
    }


def pass2_adversarial() -> dict[str, Any]:
    dirty = adversarial_dirty_payload()
    proj = project_private_to_public(dirty)
    names = {n.lower() for n in collect_field_names(proj)}
    leaked = sorted(b for b in BANNED_PRIVATE_FIELDS if b.lower() in names)
    # Direct allow-list probe
    smuggled = serialize_allowlist(
        {
            **proj,
            "entry_threshold": 0.55,
            "execution_controls": {"place_order": True},
            "founder_capital": 1,
        }
    )
    smuggle_names = collect_field_names(smuggled)
    smuggle_leaks = [
        k
        for k in ("entry_threshold", "execution_controls", "founder_capital")
        if k in smuggle_names
    ]
    ok = not leaked and not smuggle_leaks and count_execution_controls(proj) == 0
    return {
        "pass": 2,
        "name": "adversarial",
        "ok": ok,
        "banned_leaks": leaked,
        "smuggle_leaks": smuggle_leaks,
        "member_execution_control_count": int(proj.get("member_execution_control_count", -1)),
    }


def pass3_inference_and_imports() -> dict[str, Any]:
    redteam = run_inference_redteam()
    imports = scan_private_core_imports()
    env = env_hard_ban_guard()
    ok = (
        redteam["survivor_count"] == 0
        and not imports
        and env["ok"]
    )
    return {
        "pass": 3,
        "name": "inference_and_imports",
        "ok": ok,
        "inference_survivor_count": redteam["survivor_count"],
        "inference_survivors": redteam["survivors"],
        "private_core_imports": imports,
        "env": env,
        "redteam": redteam,
    }


def run_three_passes() -> dict[str, Any]:
    p1 = pass1_completeness()
    p2 = pass2_adversarial()
    p3 = pass3_inference_and_imports()
    passes = [p1, p2, p3]
    ok = all(p["ok"] for p in passes)
    # Final projection attestation
    proj = project_private_to_public(private_core_fixture())
    exec_count = int(proj.get("member_execution_control_count", -1))
    survivors = int(p3.get("inference_survivor_count", -1))
    if exec_count != 0:
        ok = False
    if survivors != 0:
        ok = False
    return {
        "schema": "pub17_c_hard_bans_v1",
        "hard_bans": list(HARD_BANS),
        "passes": passes,
        "ok": ok,
        "member_execution_control_count": exec_count,
        "inference_survivor_count": survivors,
        "recommendation": PASS_RECOMMENDATION if ok else FAIL_RECOMMENDATION,
        "status": "PASS" if ok else "FAIL",
    }


def refuse_execution_controls() -> None:
    raise HardBanViolation("HARD BAN: execution controls refused on public projection")


def refuse_proprietary_thresholds() -> None:
    raise HardBanViolation("HARD BAN: proprietary thresholds refused on public projection")


def refuse_report_edit() -> None:
    raise HardBanViolation("HARD BAN: acceleration report edit refused")


def refuse_pr26_pr27() -> None:
    raise HardBanViolation("HARD BAN: PR26/PR27 merge refused")
