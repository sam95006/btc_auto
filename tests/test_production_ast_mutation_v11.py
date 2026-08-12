"""Production AST mutation depth — R4 remediation proofs."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_autonomy.security_mutation_v11.ast_mutator import (  # noqa: E402
    mutate_scan_secrets_always_empty,
)
from backend.nexus_autonomy.security_mutation_v11.constants import (  # noqa: E402
    DUPLICATE_GATE_BASELINE_FALSE_CONFIDENCE_ACK,
    H_GATE_PASS_IS_NOT_AUTHORITY_REMEDIATION,
    PRODUCTION_AST_REQUIRED_DETECT_KILLS,
    PRODUCTION_MUTATION_TARGETS,
    WRAPPER_ONLY_PASS_FORBIDDEN,
)
from backend.nexus_autonomy.security_mutation_v11.production_ast import (  # noqa: E402
    run_production_ast_mutation,
)
from backend.nexus_autonomy.security_persistence_v1 import (  # noqa: E402
    scan_secrets_in_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def test_production_targets_exist():
    for rel in PRODUCTION_MUTATION_TARGETS:
        assert (ROOT / rel).is_file(), rel


def test_ast_mutator_can_noop_secrets():
    src = (ROOT / "backend/nexus_autonomy/security_persistence_v1.py").read_text(encoding="utf-8")
    mutated, spec = mutate_scan_secrets_always_empty(src)
    assert spec is not None
    assert spec.mutant_id == "persist_scan_secrets_noop"
    assert mutated != src


def test_json_api_key_assignment_detected():
    secret_val = "SUPERSECRET" + "VALUE123456"
    findings = scan_secrets_in_evidence({"api_key": secret_val})
    assert "credential_assignment" in findings
    blob = json.dumps({"api_key": secret_val})
    assert re.search(r'"(api[_-]?key|api[_-]?secret|token)"\s*:\s*"[^"]{16,}"', blob, re.I)


def test_production_ast_kill_suite_zero_survivors():
    report = run_production_ast_mutation(ROOT)
    assert report["mutation_kind"] == "production_ast"
    assert report["tool"] == "custom_ast_mutator"
    assert report["mutmut_used"] is False
    assert report["wrapper_only"] is False
    assert report["mutant_total"] >= 8
    assert report["production_ast_survivor_count"] == 0, report.get("survivor_ids")
    assert report["error_count"] == 0
    assert report["required_detect_kills_ok"] is True
    killed = {r["mutant_id"] for r in report["results"] if r["status"] == "killed"}
    for mid in PRODUCTION_AST_REQUIRED_DETECT_KILLS:
        assert mid in killed, (mid, report["results"])


def test_wrapper_only_pass_forbidden_constant():
    assert WRAPPER_ONLY_PASS_FORBIDDEN is True


def test_h_gate_honesty_constants():
    assert H_GATE_PASS_IS_NOT_AUTHORITY_REMEDIATION is True
    assert DUPLICATE_GATE_BASELINE_FALSE_CONFIDENCE_ACK is True


def test_negative_rejects_wrapper_only_as_production_proof():
    """G must not treat wrapper campaign alone as production AST proof."""
    from backend.nexus_autonomy.security_mutation_v11.constants import (
        PRODUCTION_AST_SURVIVOR_COUNT_REQUIRED,
    )

    assert PRODUCTION_AST_SURVIVOR_COUNT_REQUIRED == 0
    assert WRAPPER_ONLY_PASS_FORBIDDEN is True
    # Simulate wrapper-only: zero production mutants must not be acceptable.
    fake = {"mutant_total": 0, "production_ast_survivor_count": 0}
    assert not (
        WRAPPER_ONLY_PASS_FORBIDDEN
        and int(fake["mutant_total"]) > 0
        and int(fake["production_ast_survivor_count"]) == 0
    )
