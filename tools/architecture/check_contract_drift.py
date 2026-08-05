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
    authority = getattr(exec_cost, "CANONICAL_COST_AUTHORITY", None)
    authority_count = getattr(exec_cost, "CANONICAL_COST_AUTHORITY_COUNT", None)
    contract_cls = getattr(exec_cost, "CostModelContract", None)
    if authority != "backend.nexus_execution.cost_model":
        findings.append(
            {
                "domain": "cost",
                "severity": "critical",
                "code": "CANONICAL_COST_AUTHORITY_MISMATCH",
                "expected": "backend.nexus_execution.cost_model",
                "observed": authority,
            }
        )
    if authority_count != 1:
        findings.append(
            {
                "domain": "cost",
                "severity": "critical",
                "code": "CANONICAL_COST_AUTHORITY_COUNT_NOT_ONE",
                "observed": authority_count,
            }
        )
    if contract_cls is None:
        findings.append(
            {
                "domain": "cost",
                "severity": "critical",
                "code": "COST_MODEL_CONTRACT_MISSING",
                "module": "backend.nexus_execution.cost_model",
            }
        )

    v_strat = None
    if not isinstance(strat_cost, dict):
        v_strat = getattr(strat_cost, "COST_MODEL_VERSION", None)
        strat_file = _module_file(root, "backend.nexus_strategy_engine.cost_semantics")
        strat_text = strat_file.read_text(encoding="utf-8") if strat_file.exists() else ""
        imports_canonical = "backend.nexus_execution.cost_model" in strat_text
        # Independent string assignment of COST_MODEL_VERSION (not a re-export).
        assigned = _read_assign(strat_file, "COST_MODEL_VERSION") if strat_file.exists() else None
        if assigned is not None and not imports_canonical:
            findings.append(
                {
                    "domain": "cost",
                    "severity": "critical",
                    "code": "COST_MODEL_VERSION_DIVERGENCE",
                    "canonical": v_exec,
                    "competitor_module": "backend.nexus_strategy_engine.cost_semantics",
                    "competitor_version": assigned,
                    "recommendation": (
                        "Re-export COST_MODEL_VERSION from backend.nexus_execution.cost_model."
                    ),
                }
            )
        elif v_exec and v_strat and v_exec != v_strat:
            findings.append(
                {
                    "domain": "cost",
                    "severity": "critical",
                    "code": "COST_MODEL_VERSION_DIVERGENCE",
                    "canonical": v_exec,
                    "competitor_module": "backend.nexus_strategy_engine.cost_semantics",
                    "competitor_version": v_strat,
                    "recommendation": (
                        "Align strategy cost_semantics versioning with execution cost_model."
                    ),
                }
            )
        elif not imports_canonical:
            findings.append(
                {
                    "domain": "cost",
                    "severity": "high",
                    "code": "COST_SEMANTICS_NOT_BRIDGED",
                    "module": "backend.nexus_strategy_engine.cost_semantics",
                    "recommendation": "Import COST_MODEL_VERSION from nexus_execution.cost_model.",
                }
            )

    # Compat simulator must not hard-code fee constants independently.
    compat = _module_file(root, "backend.nexus_autonomy.execution_simulator_v1_1")
    if compat.exists():
        text = compat.read_text(encoding="utf-8")
        uses_canonical = "backend.nexus_execution.cost_model" in text
        taker_assign = _read_assign(compat, "TAKER_FEE")
        if taker_assign is not None and not uses_canonical:
            findings.append(
                {
                    "domain": "cost",
                    "severity": "high",
                    "code": "COMPAT_SIM_HARDCODED_FEE",
                    "module": "backend.nexus_autonomy.execution_simulator_v1_1",
                    "observed_taker_fee": taker_assign,
                    "recommendation": "Route callers to nexus_execution.cost_model; keep shim read-only.",
                }
            )
        elif not uses_canonical:
            findings.append(
                {
                    "domain": "cost",
                    "severity": "high",
                    "code": "COMPAT_SIM_COST_NOT_BRIDGED",
                    "module": "backend.nexus_autonomy.execution_simulator_v1_1",
                    "recommendation": "Import fee/cost helpers from nexus_execution.cost_model.",
                }
            )
    return findings


def check_lifecycle_drift(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    session_sm = _module_file(root, "backend.nexus_autonomy.session_state_machine")
    control_sm = _module_file(root, "backend.nexus_private_control.state_machine")
    s_states = _read_assign(session_sm, "CANONICAL_STATES") if session_sm.exists() else None
    c_states = _read_assign(control_sm, "CANONICAL_STATES") if control_sm.exists() else None
    if not (s_states and c_states and set(s_states) != set(c_states)):
        return findings

    # Dual vocabularies are intentional (scoped). Critical only when the V11.1
    # adapter contract is missing or fails its own presence checks.
    adapter_mod = _safe_import("backend.nexus_contracts.lifecycle.adapters")
    adapter_ok = False
    adapter_detail: str | None = None
    if isinstance(adapter_mod, dict) and "__import_error__" in adapter_mod:
        adapter_detail = adapter_mod["__import_error__"]
    elif adapter_mod is not None and hasattr(adapter_mod, "adapter_contract_present"):
        try:
            adapter_ok = bool(adapter_mod.adapter_contract_present())
        except Exception as exc:  # noqa: BLE001
            adapter_detail = f"{type(exc).__name__}: {exc}"
    else:
        adapter_detail = "adapter_contract_present_missing"

    base = {
        "domain": "lifecycle",
        "session_states": list(s_states) if isinstance(s_states, (list, tuple)) else s_states,
        "control_plane_states": list(c_states) if isinstance(c_states, (list, tuple)) else c_states,
        "adapter_module": "backend.nexus_contracts.lifecycle.adapters",
        "adapter_contract_present": adapter_ok,
    }
    if adapter_ok:
        findings.append(
            {
                **base,
                "severity": "informational",
                "code": "DUAL_LIFECYCLE_VOCABULARY_SCOPED",
                "resolved_code": "DUAL_LIFECYCLE_VOCABULARY",
                "recommendation": (
                    "Scoped dual vocabulary retained. Homonymous tokens must use "
                    "ControlPlaneSessionAdapter; silent name identity remains banned."
                ),
            }
        )
    else:
        findings.append(
            {
                **base,
                "severity": "critical",
                "code": "DUAL_LIFECYCLE_VOCABULARY",
                "adapter_error": adapter_detail,
                "recommendation": (
                    "Keep scoped (session vs control-plane). Publish explicit adapter "
                    "contract under backend.nexus_contracts.lifecycle.adapters before "
                    "any state mapping."
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

    # Parallel algorithm authority: FunctionDef of retry primitives outside canonical package.
    banned_defs = {
        "parse_retry_after",
        "parse_rate_limit_reset",
        "parse_quota_reset_at",
        "backoff_with_jitter",
        "exponential_backoff_with_jitter",
        "compute_resume_wait_s",
    }
    canonical_roots = {
        "backend/nexus_provider/retry_policy.py",
        "backend\\nexus_provider\\retry_policy.py",
    }
    scan_roots = [
        root / "backend",
        root / "tools" / "research",
    ]
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if rel in {"backend/nexus_provider/retry_policy.py"}:
                continue
            if "nexus_provider" in rel.replace("\\", "/"):
                # package re-exports / adapters allowed; only FunctionDef is banned outside retry_policy
                pass
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(text)
            except (OSError, SyntaxError):
                continue
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name in banned_defs:
                    # Thin adapter wrapping canonical may keep the name only if it
                    # clearly delegates (contains nexus_provider import in module).
                    uses_canonical = (
                        "backend.nexus_provider" in text
                        or "nexus_provider.retry_policy" in text
                    )
                    # Adapter exception: call-through wrappers that import canonical
                    # are allowed only when the FunctionDef body is tiny.
                    stmts = list(node.body)
                    if (
                        stmts
                        and isinstance(stmts[0], ast.Expr)
                        and isinstance(getattr(stmts[0], "value", None), ast.Constant)
                    ):
                        stmts = stmts[1:]
                    is_thin_adapter = uses_canonical and len(stmts) <= 4
                    if not is_thin_adapter:
                        findings.append(
                            {
                                "domain": "provider_retry",
                                "severity": "critical",
                                "code": "PARALLEL_RETRY_IMPLEMENTATION",
                                "module": rel.replace("/", ".").removesuffix(".py"),
                                "symbol": node.name,
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
