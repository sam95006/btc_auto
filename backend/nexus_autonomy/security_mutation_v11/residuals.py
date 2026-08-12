"""Pass-2 residual risk register — explicit high findings that are not silent.

These are recorded even when the campaign PASSes, so Founders see residual
attack surface without converting known mitigated issues into false FAIL.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_autonomy.security_mutation_v11.constants import H_GATE_HONESTY_NOTE
from backend.nexus_autonomy.security_mutation_v11.models import Finding


def residual_high_findings() -> list[Finding]:
    """Known residual risks after kill-suite PASS (explicit, not unresolved blockers)."""
    return [
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
            code="wrapper_campaign_is_supplemental_only",
            detail=(
                "In-memory wrapper mutants remain as a supplemental kill suite. "
                "PASS now requires production AST mutation "
                "(production_ast_survivor_count=0, wrapper_only_pass_forbidden=true). "
                "Do not treat wrapper-only evidence as production-module proof."
            ),
            fail_closed=False,
        ),
        Finding(
            severity="high",
            code="DUPLICATE_GATE_BASELINE_FALSE_CONFIDENCE",
            detail=H_GATE_HONESTY_NOTE,
            fail_closed=False,
        ),
    ]


def residual_as_dicts() -> list[dict[str, Any]]:
    return [f.to_dict() for f in residual_high_findings()]
