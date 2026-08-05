#!/usr/bin/env python3
"""Contract-drift checker for Private Core authorities (V11 Lane H).

Compares canonical registry declarations against live module attributes
(COST_MODEL_VERSION, CANONICAL_EXECUTION_ENGINE, CANONICAL_STATES, etc.).
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_contracts.authority_registry import (  # noqa: E402
    build_canonical_registry,
    get_authority,
)
from backend.nexus_contracts.authority_signatures import DRIFT_SCHEMA  # noqa: E402
from tools.architecture import artifact_dir, write_json  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_import(module: str) -> Any | None:
    try:
        return importlib.import_module(module)
    except Exception as exc:  # noqa: BLE001 — drift report must not crash
        return {"__import_error__": f"{type(exc).__name__}: {exc}"}


def _read_assign(module_path: Path, name: str) -> Any:
    """Read a simple module-level assignment via AST without importing."""
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None

    def _eval(value: ast.AST) -> Any:
        try:
            return ast.literal_eval(value)
        except Exception:  # noqa: BLE001
            return ast.unparse(value) if hasattr(ast, "unparse") else "<expr>"

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return _eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return _eval(node.value)
    return None


def _module_file(root: Path, dotted: str) -> Path:
    parts = dotted.split(".")
    return root.joinpath(*parts).with_suffix(".py")


def check_execution_drift(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    auth = get_authority("execution")
    adapter = _safe_import("backend.nexus_execution.orchestrator_adapter_v1")
    if isinstance(adapter, dict) and "__import_error__" in adapter:
        findings.append(
            {
                "domain": "execution",
                "severity": "critical",
                "code": "IMPORT_FAILED",
                "detail": adapter["__import_error__"],
            }
        )
        return findings
    engine = getattr(adapter, "CANONICAL_EXECUTION_ENGINE", None)
    count = getattr(adapter, "CANONICAL_EXECUTION_ENGINE_COUNT", None)
    expected = f"{auth.canonical_module}.{auth.canonical_symbol}"
    if engine != expected:
        findings.append(
            {
                "domain": "execution",
                "severity": "critical",
                "code": "CANONICAL_ENGINE_MISMATCH",
                "expected": expected,
                "observed": engine,
            }
        )
    if count != 1:
        findings.append(
            {
                "domain": "execution",
                "severity": "critical",
                "code": "ENGINE_COUNT_NOT_ONE",
                "observed": count,
            }
        )
    return findings


def check_cost_drift(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    exec_cost = _safe_import("backend.nexus_execution.cost_model")
    strat_cost = _safe_import("backend.nexus_strategy_engine.cost_semantics")
    if isinstance(exec_cost, dict):
        findings.append(
            {
                "domain": "cost",
                "severity": "critical",
                "code": "IMPORT_FAILED",
                "module": "backend.nexus_execution.cost_model",
                "detail": exec_cost["__import_error__"],
            }
        )
        return findings
    v_exec = getattr(exec_cost, "COST_MODEL_VERSION", None)
    v_strat = None
    if not isinstance(strat_cost, dict):
        v_strat = getattr(strat_cost, "COST_MODEL_VERSION", None)
    if v_exec and v_strat and v_exec != v_strat:
        findings.append(
            {
                "domain": "cost",
                "severity": "critical",
                "code": "COST_MODEL_VERSION_DIVERGENCE",
                "canonical": v_exec,
                "competitor_module": "backend.nexus_strategy_engine.cost_semantics",
                "competitor_version": v_strat,
                "recommendation": (
                    "Align strategy cost_semantics versioning with execution cost_model "
                    "or explicitly namespace as research-proxy (not Session cost authority)."
                ),
            }
        )
    # Compat simulator fee floats vs Decimal model
    compat = _module_file(root, "backend.nexus_autonomy.execution_simulator_v1_1")
    if compat.exists():
        taker = _read_assign(compat, "TAKER_FEE")
        if taker is not None:
            findings.append(
                {
                    "domain": "cost",
                    "severity": "high",
                    "code": "COMPAT_SIM_HARDCODED_FEE",
                    "module": "backend.nexus_autonomy.execution_simulator_v1_1",
                    "observed_taker_fee": taker,
                    "recommendation": "Route callers to nexus_execution.cost_model; keep shim read-only.",
                }
            )
    return findings


def check_lifecycle_drift(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    session_sm = _module_file(root, "backend.nexus_autonomy.session_state_machine")
    control_sm = _module_file(root, "backend.nexus_private_control.state_machine")
    s_states = _read_assign(session_sm, "CANONICAL_STATES") if session_sm.exists() else None
    c_states = _read_assign(control_sm, "CANONICAL_STATES") if control_sm.exists() else None
    if s_states and c_states and set(s_states) != set(c_states):
        findings.append(
            {
                "domain": "lifecycle",
                "severity": "critical",
                "code": "DUAL_LIFECYCLE_VOCABULARY",
                "session_states": list(s_states) if isinstance(s_states, (list, tuple)) else s_states,
                "control_plane_states": list(c_states) if isinstance(c_states, (list, tuple)) else c_states,
                "recommendation": (
                    "Keep scoped (session vs control-plane). Block any code that maps states "
                    "by identical name without an explicit adapter contract."
                ),
            }
        )
    return findings


def check_provider_retry_drift(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    provider = _safe_import("backend.nexus_provider.retry_policy")
    if isinstance(provider, dict):
        findings.append(
            {
                "domain": "provider_retry",
                "severity": "critical",
                "code": "IMPORT_FAILED",
                "detail": provider["__import_error__"],
            }
        )
        return findings
    # Detect parallel backoff in edge discovery via AST presence
    edge = root / "backend" / "nexus_edge_discovery" / "provider_transport_v23.py"
    if edge.exists():
        text = edge.read_text(encoding="utf-8")
        uses_canonical = "backend.nexus_provider" in text or "nexus_provider.retry_policy" in text
        has_own = "exponential_backoff_with_jitter" in text or "def exponential_backoff" in text
        if has_own and not uses_canonical:
            findings.append(
                {
                    "domain": "provider_retry",
                    "severity": "critical",
                    "code": "PARALLEL_RETRY_IMPLEMENTATION",
                    "module": "backend.nexus_edge_discovery.provider_transport_v23",
                    "recommendation": (
                        "Import parse_retry_after / backoff_with_jitter from "
                        "backend.nexus_provider.retry_policy; deprecate local copy."
                    ),
                }
            )
    stage4 = root / "tools" / "research" / "stage4_provider_chain.py"
    if stage4.exists():
        text = stage4.read_text(encoding="utf-8")
        if "Stage4ProviderCircuitBreaker" in text and "nexus_provider" not in text:
            findings.append(
                {
                    "domain": "provider_retry",
                    "severity": "high",
                    "code": "STAGE4_PARALLEL_CIRCUIT_BREAKER",
                    "module": "tools.research.stage4_provider_chain",
                    "recommendation": "Prefer backend.nexus_provider.circuit_breaker for new code.",
                }
            )
    return findings


def check_checkpoint_drift(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    auth = get_authority("checkpoint")
    canonical = _safe_import(auth.canonical_module)
    if isinstance(canonical, dict) and "__import_error__" in canonical:
        findings.append(
            {
                "domain": "checkpoint",
                "severity": "critical",
                "code": "CANONICAL_ENVELOPE_IMPORT_FAILED",
                "module": auth.canonical_module,
                "detail": canonical["__import_error__"],
            }
        )
        return findings
    store_cls = getattr(canonical, auth.canonical_symbol, None)
    if store_cls is None:
        findings.append(
            {
                "domain": "checkpoint",
                "severity": "critical",
                "code": "CANONICAL_ENVELOPE_SYMBOL_MISSING",
                "module": auth.canonical_module,
                "symbol": auth.canonical_symbol,
            }
        )
    envelope = _safe_import("backend.nexus_checkpoint")
    if isinstance(envelope, dict) and "__import_error__" in envelope:
        findings.append(
            {
                "domain": "checkpoint",
                "severity": "critical",
                "code": "ENVELOPE_PACKAGE_IMPORT_FAILED",
                "detail": envelope["__import_error__"],
            }
        )
    else:
        count = getattr(envelope, "CANONICAL_CHECKPOINT_ENVELOPE_COUNT", None)
        if count != 1:
            findings.append(
                {
                    "domain": "checkpoint",
                    "severity": "critical",
                    "code": "ENVELOPE_COUNT_NOT_ONE",
                    "observed": count,
                }
            )
        schema = getattr(envelope, "ENVELOPE_SCHEMA", None)
        if schema != "nexus_checkpoint_envelope_v1":
            findings.append(
                {
                    "domain": "checkpoint",
                    "severity": "critical",
                    "code": "ENVELOPE_SCHEMA_MISMATCH",
                    "expected": "nexus_checkpoint_envelope_v1",
                    "observed": schema,
                }
            )

    # Payload owners remain; document as informational when adapters exist.
    payload_owners = [
        ("backend.nexus_reflection.checkpoint", "CHECKPOINT_SCHEMA_V4"),
        ("backend.nexus_private_control.checkpoint", None),
        ("backend.nexus_decision.checkpoint", None),
        ("backend.nexus_recovery.crash_recovery", None),
    ]
    present = []
    for mod, key in payload_owners:
        fp = _module_file(root, mod)
        if fp.exists():
            entry: dict[str, Any] = {"module": mod, "exists": True, "role": "payload_owner"}
            if key:
                entry[key] = _read_assign(fp, key)
            present.append(entry)
    adapters = root / "backend" / "nexus_checkpoint" / "adapters.py"
    if len(present) >= 2:
        if adapters.exists():
            findings.append(
                {
                    "domain": "checkpoint",
                    "severity": "informational",
                    "code": "MULTI_PAYLOAD_SCHEMAS_ADAPTED",
                    "modules": present,
                    "adapter_module": "backend.nexus_checkpoint.adapters",
                    "recommendation": (
                        "Payload schemas remain subsystem-owned; cross-domain resume must "
                        "go through nexus_checkpoint adapters into the canonical envelope."
                    ),
                }
            )
        else:
            findings.append(
                {
                    "domain": "checkpoint",
                    "severity": "critical",
                    "code": "MULTI_SCOPE_AUTHORITY_CHECKPOINT",
                    "modules": present,
                    "recommendation": (
                        "Publish canonical envelope + explicit adapters before deletion waves."
                    ),
                }
            )
    return findings


def check_fill_risk_presence(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for domain, mod, symbol in (
        ("fill", "backend.nexus_execution.fill_engine", "try_fill"),
        ("risk", "backend.nexus_execution.risk_gates", "RiskLimits"),
    ):
        m = _safe_import(mod)
        if isinstance(m, dict):
            findings.append(
                {
                    "domain": domain,
                    "severity": "critical",
                    "code": "IMPORT_FAILED",
                    "module": mod,
                    "detail": m["__import_error__"],
                }
            )
            continue
        if not hasattr(m, symbol):
            findings.append(
                {
                    "domain": domain,
                    "severity": "critical",
                    "code": "CANONICAL_SYMBOL_MISSING",
                    "module": mod,
                    "symbol": symbol,
                }
            )
    return findings


def run_drift_checks(root: Path) -> dict[str, Any]:
    registry = build_canonical_registry()
    findings: list[dict[str, Any]] = []
    findings.extend(check_execution_drift(root))
    findings.extend(check_cost_drift(root))
    findings.extend(check_lifecycle_drift(root))
    findings.extend(check_provider_retry_drift(root))
    findings.extend(check_checkpoint_drift(root))
    findings.extend(check_fill_risk_presence(root))

    by_sev: dict[str, int] = {}
    for f in findings:
        by_sev[f.get("severity", "unknown")] = by_sev.get(f.get("severity", "unknown"), 0) + 1

    blockers = [f for f in findings if f.get("severity") == "critical"]
    return {
        "schema": DRIFT_SCHEMA,
        "generated_at": _utc(),
        "lane": "V11_H_AUTHORITY_CONSOLIDATION",
        "registry_version": registry["registry_version"],
        "finding_count": len(findings),
        "severity_counts": by_sev,
        "findings": findings,
        "blockers": blockers,
        "passed": len(blockers) == 0,
        "note": (
            "passed=false indicates contract drift blockers for consolidation readiness; "
            "Lane H does not auto-fix competitor modules."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check NEXUS authority contract drift")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--fail-on-blocker", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out_dir or artifact_dir(root)
    report = run_drift_checks(root)
    write_json(out / "contract_drift_report.json", report)
    print(
        json.dumps(
            {
                "finding_count": report["finding_count"],
                "severity_counts": report["severity_counts"],
                "blocker_count": len(report["blockers"]),
                "passed": report["passed"],
            },
            indent=2,
        )
    )
    if args.fail_on_blocker and not report["passed"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
