#!/usr/bin/env python3
"""Founder C2 — Lifecycle Vocabulary Unification V11.1 (two-pass).

Emits artifacts under:
  artifacts/readiness/immutable/v11_1_lifecycle_vocabulary/

Hard bans: no merge/deploy/WF/OOS/Demo/exchange/mainnet/real money/G delete.
Does not collapse lifecycles into one state machine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ART_REL = Path("artifacts/readiness/immutable/v11_1_lifecycle_vocabulary")
OWNED_SCAN_PATHS = [
    "backend/nexus_contracts/lifecycle",
    "backend/nexus_contracts/authority_registry.py",
    "tools/architecture/check_contract_drift.py",
    "tools/architecture/run_authority_consolidation.py",
    "tools/architecture/run_lifecycle_vocabulary_v11_1.py",
    "tests/architecture/test_lifecycle_vocabulary_v11_1.py",
    "artifacts/readiness/immutable/v11_1_lifecycle_vocabulary",
]

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]

NEGATIVE_FIXTURES: tuple[dict[str, Any], ...] = (
    {
        "id": "neg_decision_closed_position_open",
        "snapshot": {
            "decision_state": "CLOSED",
            "position_state": "OPEN",
            "position_qty": "1",
        },
        "expect_codes": ["INV_DECISION_CLOSED_POSITION_OPEN"],
    },
    {
        "id": "neg_session_completed_unresolved_intent",
        "snapshot": {
            "session_state": "COMPLETED",
            "intent_state": "WORKING",
            "position_state": "NONE",
        },
        "expect_codes": ["INV_SESSION_COMPLETED_UNRESOLVED_INTENT"],
    },
    {
        "id": "neg_reflection_complete_before_exit",
        "snapshot": {
            "reflection_state": "COMPLETE",
            "decision_state": "MONITORING",
            "exit_evidence": False,
        },
        "expect_codes": ["INV_REFLECTION_COMPLETE_BEFORE_EXIT"],
    },
    {
        "id": "neg_position_closed_residual_qty",
        "snapshot": {
            "position_state": "CLOSED",
            "position_qty": "0.5",
            "decision_state": "EXITED",
        },
        "expect_codes": ["INV_POSITION_CLOSED_RESIDUAL_QTY"],
    },
    {
        "id": "neg_session_control_silent_homonym",
        "snapshot": {
            "session_state": "COMPLETED",
            "control_plane_state": "KILLED",
        },
        "expect_codes": ["INV_SESSION_CONTROL_ADAPTER"],
    },
)

POSITIVE_FIXTURES: tuple[dict[str, Any], ...] = (
    {
        "id": "pos_happy_flat_close",
        "snapshot": {
            "decision_state": "CLOSED",
            "session_state": "COMPLETED",
            "intent_state": "FILLED",
            "order_state": "FILLED",
            "position_state": "CLOSED",
            "position_qty": "0",
            "reflection_state": "COMPLETE",
            "exit_evidence": True,
            "control_plane_state": "STOPPED",
        },
    },
    {
        "id": "pos_running_open",
        "snapshot": {
            "decision_state": "MONITORING",
            "session_state": "RUNNING",
            "intent_state": "WORKING",
            "order_state": "ACCEPTED",
            "position_state": "OPEN",
            "position_qty": "1",
            "reflection_state": "PENDING",
            "exit_evidence": False,
            "control_plane_state": "RUNNING",
        },
    },
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def scan_secrets(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_SCAN_PATHS:
        target = root / rel
        files: list[Path]
        if target.is_dir():
            files = [
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in {".py", ".json", ".md", ".yml", ".yaml"}
            ]
        elif target.is_file():
            files = [target]
        else:
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v11_1_lifecycle_vocabulary_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": OWNED_SCAN_PATHS,
    }


def run_validation_matrix() -> dict[str, Any]:
    from backend.nexus_contracts.lifecycle.invariants import validate_snapshot

    rows: list[dict[str, Any]] = []
    for fix in NEGATIVE_FIXTURES:
        result = validate_snapshot(fix["snapshot"])
        codes = {v["code"] for v in result["violations"]}
        expected = set(fix["expect_codes"])
        ok = (not result["valid"]) and expected.issubset(codes)
        rows.append(
            {
                "id": fix["id"],
                "kind": "negative",
                "ok": ok,
                "valid": result["valid"],
                "expected_codes": sorted(expected),
                "observed_codes": sorted(codes),
                "critical_count": result["critical_count"],
            }
        )
    for fix in POSITIVE_FIXTURES:
        result = validate_snapshot(fix["snapshot"])
        ok = result["valid"] is True and result["critical_count"] == 0
        rows.append(
            {
                "id": fix["id"],
                "kind": "positive",
                "ok": ok,
                "valid": result["valid"],
                "critical_count": result["critical_count"],
                "violations": result["violations"],
            }
        )
    return {
        "schema": "v11_1_lifecycle_vocabulary_validation_matrix",
        "created_at": _utc(),
        "row_count": len(rows),
        "passed": all(r["ok"] for r in rows),
        "rows": rows,
    }


def adversarial_review(pass_id: str, artifacts: dict[str, Any]) -> dict[str, Any]:
    """Pass-local adversarial self-review — hunt residual blockers."""
    findings: list[dict[str, Any]] = []

    ontology = artifacts.get("ontology") or {}
    if ontology.get("policy", {}).get("collapse_to_single_fsm") is not False:
        findings.append(
            {
                "severity": "critical",
                "code": "COLLAPSE_POLICY_VIOLATION",
                "message": "Ontology must keep collapse_to_single_fsm=false",
            }
        )

    adapter = artifacts.get("adapter") or {}
    if adapter.get("policy", {}).get("silent_homonym_mapping") is not False:
        findings.append(
            {
                "severity": "critical",
                "code": "SILENT_HOMONYM_ALLOWED",
                "message": "Adapter must forbid silent homonym mapping",
            }
        )

    matrix = artifacts.get("validation_matrix") or {}
    if not matrix.get("passed"):
        findings.append(
            {
                "severity": "critical",
                "code": "VALIDATION_MATRIX_FAILED",
                "message": "Positive/negative matrix must pass",
            }
        )

    drift = artifacts.get("drift") or {}
    critical_codes = {
        f.get("code")
        for f in (drift.get("findings") or [])
        if f.get("severity") == "critical"
    }
    if "DUAL_LIFECYCLE_VOCABULARY" in critical_codes:
        findings.append(
            {
                "severity": "critical",
                "code": "DUAL_LIFECYCLE_VOCABULARY_UNRESOLVED",
                "message": "Adapter did not clear DUAL_LIFECYCLE_VOCABULARY critical finding",
            }
        )

    blockers = artifacts.get("consolidation_blockers") or []
    lifecycle_multi = [
        b
        for b in blockers
        if b.get("domain") == "lifecycle"
        and b.get("code") in {"MULTI_SCOPE_AUTHORITY", "MULTI_SCOPE_AUTHORITY_LIFECYCLE"}
    ]
    if lifecycle_multi:
        findings.append(
            {
                "severity": "critical",
                "code": "MULTI_SCOPE_AUTHORITY_LIFECYCLE_UNRESOLVED",
                "message": "Lifecycle multi-scope authority still blocking",
                "blockers": lifecycle_multi,
            }
        )

    secrets = artifacts.get("secret_scan") or {}
    if int(secrets.get("secret_leak_count") or 0) > 0:
        findings.append(
            {
                "severity": "critical",
                "code": "SECRET_LEAK",
                "message": "Secret patterns detected in owned paths",
            }
        )

    # High: confirm negative fixtures cover mission examples
    neg_ids = {r["id"] for r in (matrix.get("rows") or []) if r.get("kind") == "negative"}
    required_neg = {
        "neg_decision_closed_position_open",
        "neg_session_completed_unresolved_intent",
        "neg_reflection_complete_before_exit",
        "neg_position_closed_residual_qty",
    }
    missing = sorted(required_neg - neg_ids)
    if missing:
        findings.append(
            {
                "severity": "high",
                "code": "MISSING_NEGATIVE_COVERAGE",
                "message": f"Missing required negative fixtures: {missing}",
            }
        )

    critical = [f for f in findings if f.get("severity") == "critical"]
    high = [f for f in findings if f.get("severity") == "high"]
    return {
        "schema": "v11_1_lifecycle_vocabulary_adversarial_review",
        "pass_id": pass_id,
        "created_at": _utc(),
        "finding_count": len(findings),
        "critical_count": len(critical),
        "high_count": len(high),
        "findings": findings,
        "passed": len(critical) == 0,
    }


def collect_pass(root: Path, pass_id: str) -> dict[str, Any]:
    from backend.nexus_contracts.authority_registry import build_canonical_registry
    from backend.nexus_contracts.lifecycle.adapters import ControlPlaneSessionAdapter
    from backend.nexus_contracts.lifecycle.blocked_ambiguous import blocked_ambiguous_policy
    from backend.nexus_contracts.lifecycle.compatibility import compatibility_report
    from backend.nexus_contracts.lifecycle.invariants import CROSS_LIFECYCLE_INVARIANTS
    from backend.nexus_contracts.lifecycle.ontology import build_ontology
    from backend.nexus_contracts.lifecycle.transitions import transition_mapping_report
    from tools.architecture.check_contract_drift import run_drift_checks
    from tools.architecture.run_authority_consolidation import run_pass as consol_pass

    ontology = build_ontology()
    adapter = ControlPlaneSessionAdapter().to_dict()
    invariants = {
        "schema": "nexus_cross_lifecycle_invariants_v11_1",
        "invariants": list(CROSS_LIFECYCLE_INVARIANTS),
    }
    compatibility = compatibility_report()
    transitions = transition_mapping_report()
    blocked = blocked_ambiguous_policy()
    validation_matrix = run_validation_matrix()
    secret_scan = scan_secrets(root)
    drift = run_drift_checks(root)
    registry = build_canonical_registry()

    # Lightweight consolidation slice for lifecycle blockers only (no rewrite of Lane H arts).
    consol = consol_pass(root, root / "artifacts" / "readiness" / "immutable" / "_tmp_lifecycle_consol", pass_id)
    consolidation_blockers = list(consol.get("blockers") or [])

    bundle = {
        "ontology": ontology,
        "adapter": adapter,
        "invariants": invariants,
        "compatibility": compatibility,
        "transitions": transitions,
        "blocked_ambiguous": blocked,
        "validation_matrix": validation_matrix,
        "secret_scan": secret_scan,
        "drift": drift,
        "consolidation_blockers": consolidation_blockers,
        "registry_summary": registry.get("summary"),
    }
    review = adversarial_review(pass_id, bundle)

    lifecycle_status = (registry.get("by_domain") or {}).get("lifecycle") or {}
    dual_critical = any(
        f.get("code") == "DUAL_LIFECYCLE_VOCABULARY" and f.get("severity") == "critical"
        for f in drift.get("findings") or []
    )
    multi_lifecycle = any(
        b.get("domain") == "lifecycle"
        and b.get("code") in {"MULTI_SCOPE_AUTHORITY", "MULTI_SCOPE_AUTHORITY_LIFECYCLE"}
        for b in consolidation_blockers
    )

    status = {
        "schema": "v11_1_lifecycle_vocabulary_status",
        "pass_id": pass_id,
        "created_at": _utc(),
        "branch": "feature/v11_1-lifecycle-vocabulary",
        "ontology_version": ontology.get("version"),
        "adapter_contract_id": adapter.get("contract_id"),
        "lifecycle_registry_status": lifecycle_status.get("status"),
        "DUAL_LIFECYCLE_VOCABULARY_resolved": not dual_critical,
        "MULTI_SCOPE_AUTHORITY_LIFECYCLE_resolved": not multi_lifecycle,
        "validation_matrix_passed": validation_matrix.get("passed"),
        "adversarial_passed": review.get("passed"),
        "secret_leak_count": secret_scan.get("secret_leak_count"),
        "collapse_to_single_fsm": False,
        "passed": bool(
            review.get("passed")
            and validation_matrix.get("passed")
            and not dual_critical
            and not multi_lifecycle
            and int(secret_scan.get("secret_leak_count") or 0) == 0
        ),
    }
    return {
        "status": status,
        "ontology": ontology,
        "adapter": adapter,
        "invariants": invariants,
        "compatibility": compatibility,
        "transitions": transitions,
        "blocked_ambiguous": blocked,
        "validation_matrix": validation_matrix,
        "secret_scan": secret_scan,
        "drift_findings": [
            f
            for f in (drift.get("findings") or [])
            if f.get("domain") == "lifecycle" or "LIFECYCLE" in str(f.get("code") or "")
        ],
        "consolidation_blockers_lifecycle": [
            b for b in consolidation_blockers if b.get("domain") == "lifecycle"
        ],
        "adversarial_review": review,
        "metrics": {
            "scope_count": len(ontology.get("scopes") or []),
            "trading_loop_scope_count": len(ontology.get("trading_loop_scopes") or []),
            "adapter_allowed_pairs": adapter.get("allowed_pair_count"),
            "invariant_count": len(CROSS_LIFECYCLE_INVARIANTS),
            "compatibility_rows": compatibility.get("row_count"),
            "transition_edges": transitions.get("edge_count"),
            "negative_fixture_count": sum(
                1 for r in validation_matrix.get("rows") or [] if r.get("kind") == "negative"
            ),
            "positive_fixture_count": sum(
                1 for r in validation_matrix.get("rows") or [] if r.get("kind") == "positive"
            ),
            "adversarial_critical": review.get("critical_count"),
            "adversarial_high": review.get("high_count"),
        },
        "content_sha256": "",
    }


def write_pass_artifacts(art: Path, payload: dict[str, Any], pass_id: str) -> None:
    # Stable hash without nested sha field
    body = {k: v for k, v in payload.items() if k != "content_sha256"}
    payload["content_sha256"] = _sha(body)
    _write(art / f"{pass_id}_bundle.json", payload)
    _write(art / f"{pass_id}_status.json", payload["status"])
    _write(art / f"{pass_id}_adversarial_review.json", payload["adversarial_review"])
    _write(art / f"{pass_id}_metrics.json", payload["metrics"])


def write_shared_artifacts(art: Path, payload: dict[str, Any]) -> None:
    _write(art / "ontology.json", payload["ontology"])
    _write(art / "adapter_contract.json", payload["adapter"])
    _write(art / "cross_lifecycle_invariants.json", payload["invariants"])
    _write(art / "terminal_compatibility_table.json", payload["compatibility"])
    _write(art / "cross_scope_transitions.json", payload["transitions"])
    _write(art / "blocked_ambiguous_semantics.json", payload["blocked_ambiguous"])
    _write(art / "validation_matrix.json", payload["validation_matrix"])
    _write(art / "secret_scan.json", payload["secret_scan"])
    _write(art / "lifecycle_drift_slice.json", payload["drift_findings"])
    _write(
        art / "lifecycle_blockers_slice.json",
        {
            "generated_at": _utc(),
            "blockers": payload["consolidation_blockers_lifecycle"],
            "DUAL_LIFECYCLE_VOCABULARY_resolved": payload["status"][
                "DUAL_LIFECYCLE_VOCABULARY_resolved"
            ],
            "MULTI_SCOPE_AUTHORITY_LIFECYCLE_resolved": payload["status"][
                "MULTI_SCOPE_AUTHORITY_LIFECYCLE_resolved"
            ],
        },
    )


def write_summary(art: Path, pass1: dict[str, Any], pass2: dict[str, Any]) -> None:
    lines = [
        "# V11.1 Lifecycle Vocabulary Unification — Summary",
        "",
        f"Generated: {_utc()}",
        "",
        "## Resolution",
        "",
        f"- DUAL_LIFECYCLE_VOCABULARY resolved: `{pass2['status']['DUAL_LIFECYCLE_VOCABULARY_resolved']}`",
        f"- MULTI_SCOPE_AUTHORITY_LIFECYCLE resolved: `{pass2['status']['MULTI_SCOPE_AUTHORITY_LIFECYCLE_resolved']}`",
        f"- Collapse to single FSM: `{pass2['status']['collapse_to_single_fsm']}`",
        f"- Adversarial passed: `{pass2['status']['adversarial_passed']}`",
        f"- Validation matrix passed: `{pass2['status']['validation_matrix_passed']}`",
        "",
        "## Metrics",
        "",
    ]
    for k, v in (pass2.get("metrics") or {}).items():
        lines.append(f"- {k}: `{v}`")
    lines.extend(
        [
            "",
            "## Pass delta",
            "",
            f"- Pass1 passed: `{pass1['status'].get('passed')}`",
            f"- Pass2 passed: `{pass2['status'].get('passed')}`",
            f"- Pass1 adversarial critical: `{pass1['adversarial_review'].get('critical_count')}`",
            f"- Pass2 adversarial critical: `{pass2['adversarial_review'].get('critical_count')}`",
            "",
            "## Policy",
            "",
            "- No merge/deploy from this lane.",
            "- No WF/OOS/Demo/exchange/mainnet/real-money.",
            "- No mass-delete of compatibility modules.",
            "- Lifecycles remain scoped; adapter mediates Session↔ControlPlane only.",
            "",
        ]
    )
    (art / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    _write(
        art / "status.json",
        {
            **pass2["status"],
            "pass1_passed": pass1["status"].get("passed"),
            "pass2_passed": pass2["status"].get("passed"),
            "content_sha256_pass2": pass2.get("content_sha256"),
        },
    )
    _write(
        art / "BLOCKERS.json",
        {
            "generated_at": _utc(),
            "blocker_count": pass2["adversarial_review"].get("critical_count"),
            "blockers": [
                f
                for f in pass2["adversarial_review"].get("findings") or []
                if f.get("severity") == "critical"
            ],
            "high_findings": [
                f
                for f in pass2["adversarial_review"].get("findings") or []
                if f.get("severity") == "high"
            ],
            "DUAL_LIFECYCLE_VOCABULARY_resolved": pass2["status"][
                "DUAL_LIFECYCLE_VOCABULARY_resolved"
            ],
            "MULTI_SCOPE_AUTHORITY_LIFECYCLE_resolved": pass2["status"][
                "MULTI_SCOPE_AUTHORITY_LIFECYCLE_resolved"
            ],
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="V11.1 lifecycle vocabulary two-pass runner")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()
    root = args.root.resolve()
    art = root / ART_REL
    art.mkdir(parents=True, exist_ok=True)

    # Clean tmp consol dir between passes
    tmp = root / "artifacts" / "readiness" / "immutable" / "_tmp_lifecycle_consol"
    if tmp.exists():
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    pass1 = collect_pass(root, "pass1")
    write_pass_artifacts(art, pass1, "pass1")
    write_shared_artifacts(art, pass1)

    pass2 = pass1
    if args.passes >= 2:
        if tmp.exists():
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)
        pass2 = collect_pass(root, "pass2")
        write_pass_artifacts(art, pass2, "pass2")
        write_shared_artifacts(art, pass2)

    write_summary(art, pass1, pass2)

    # Remove ephemeral consolidation scratch
    if tmp.exists():
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    print(
        json.dumps(
            {
                "out_dir": str(art).replace("\\", "/"),
                "pass1_passed": pass1["status"].get("passed"),
                "pass2_passed": pass2["status"].get("passed"),
                "DUAL_LIFECYCLE_VOCABULARY_resolved": pass2["status"][
                    "DUAL_LIFECYCLE_VOCABULARY_resolved"
                ],
                "MULTI_SCOPE_AUTHORITY_LIFECYCLE_resolved": pass2["status"][
                    "MULTI_SCOPE_AUTHORITY_LIFECYCLE_resolved"
                ],
                "metrics": pass2.get("metrics"),
            },
            indent=2,
        )
    )
    return 0 if pass2["status"].get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
