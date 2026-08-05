"""Pass-2 residual risk register — explicit high findings that are not silent.

These are recorded even when the campaign PASSes, so Founders see residual
attack surface without converting known mitigated issues into false FAIL.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_autonomy.security_mutation_v11.models import Finding


def residual_high_findings() -> list[Finding]:
    """Known residual risks after kill-suite PASS (explicit, not unresolved blockers)."""
    return [
        Finding(
            severity="high",
            code="secret_scan_json_assignment_blind_spot",
            detail=(
                "scan_secrets_in_evidence credential_assignment regex misses JSON "
                "quoted keys (\"api_key\": \"...\"); substring pattern:api_key still hits. "
                "Do not rely on credential_assignment alone for JSON evidence."
            ),
            fail_closed=False,
        ),
        Finding(
            severity="high",
            code="symlink_escape_platform_dependent",
            detail=(
                "Windows may deny symlink creation without privilege; campaign marks "
                "symlink mutants equivalent/platform_skip. Re-run on symlink-capable host "
                "before treating symlink jail as production-proven."
            ),
            fail_closed=False,
        ),
        Finding(
            severity="high",
            code="mutation_surface_is_in_memory_wrappers",
            detail=(
                "Mutations are in-memory weakened subjects, not AST edits of production "
                "modules. Surviving source-level mutants outside owned wrappers remain a "
                "coverage gap for future mutmut/cosmic-ray integration."
            ),
            fail_closed=False,
        ),
    ]


def residual_as_dicts() -> list[dict[str, Any]]:
    return [f.to_dict() for f in residual_high_findings()]
