#!/usr/bin/env python3
"""CI gate: Autonomy V1.1 execution shim must not embed Fill/Cost/Risk/Position authority.

Scans ``backend/nexus_autonomy/execution_simulator_v1_1.py`` with AST + text traps.
Future fill / cost / risk / position-quantity / same-bar authority logic in the
shim fails this gate.

Allowed: translate, adapt, validate, and delegation to
``AutonomousExecutionSimulatorV11`` / orchestrator adapter / fill_engine.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.architecture import write_json  # noqa: E402

SHIM_REL = "backend/nexus_autonomy/execution_simulator_v1_1.py"
CANONICAL_EXECUTION = (
    "backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11"
)
CANONICAL_FILL = "backend.nexus_execution.fill_engine.try_fill"

# Function definitions that constitute embedded authority (not mere delegation).
FORBIDDEN_FUNC_DEFS: frozenset[str] = frozenset(
    {
        "_commit_fill",
        "_apply_fill",
        "_apply_costs",
        "_apply_reduce",
        "_liquidation_price",
        "_liquidation_distance",
        "_maybe_liquidate",
        "_materialise_position",
        "_open_position_via",
        "_close_position_via",
        "apply_funding",
        "check_maintenance_margin",
        "estimate_costs",
        "annotate_trade_costs",
        "compose_cost_bridge",
    }
)

# Local assignments that re-introduce cost/risk authority constants.
FORBIDDEN_ASSIGN_NAMES: frozenset[str] = frozenset(
    {
        "TAKER_FEE",
        "MAKER_FEE",
        "DEFAULT_SPREAD_BPS",
        "DEFAULT_SLIP_BPS",
        "COST_MODEL_VERSION",
        "FORBIDDEN_ACTIONS",
        "MAX_LEVERAGE_CEILING",
        "FORBIDDEN_LEVERAGE",
        "FORBIDDEN_LEVERAGE_VALUES",
    }
)

# Textual traps inside method bodies (fill / same-bar / position qty authority).
FORBIDDEN_BODY_NEEDLES: tuple[tuple[str, str], ...] = (
    ("fill_px =", "embedded_fill_price_decision"),
    ("fill_qty =", "embedded_fill_qty_decision"),
    ("is_taker =", "embedded_taker_maker_decision"),
    ("TRADE-THROUGH", "embedded_trade_through_policy"),
    ("path_low <= same_bar_stop", "embedded_same_bar_outcome"),
    ("hit_stop and hit_target", "embedded_same_bar_outcome"),
    ("SAME_BAR_STOP_TARGET", "embedded_same_bar_outcome"),
    ("pos.qty =", "embedded_position_qty_mutation"),
    ("p.qty =", "embedded_position_qty_mutation"),
    ("order.filled_qty =", "embedded_order_fill_mutation"),
    ("entry_fee", "embedded_cost_accounting"),
    ("spread_cost", "embedded_cost_accounting"),
    ("slippage_cost", "embedded_cost_accounting"),
    ("notional * fee_rate", "embedded_cost_calculation"),
    ("evaluate_intent(", "embedded_risk_gate_call"),
    ("RiskLimits(", "embedded_risk_limits_construction"),
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_reexport_assign(node: ast.AST) -> bool:
    """True when ``NAME = NAME`` / alias that is not a literal authority constant."""
    if not isinstance(node, ast.Assign):
        return False
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return False
    return isinstance(node.value, (ast.Name, ast.Attribute))


def scan_shim(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    violations: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in FORBIDDEN_FUNC_DEFS:
                violations.append(
                    {
                        "code": "FORBIDDEN_FUNC_DEF",
                        "name": node.name,
                        "lineno": node.lineno,
                        "severity": "critical",
                        "message": f"Shim must not define authority function {node.name}",
                    }
                )
        if isinstance(node, ast.Assign):
            if _is_reexport_assign(node):
                continue
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in FORBIDDEN_ASSIGN_NAMES:
                    # Allow only if RHS is a call/import rebind already filtered;
                    # literal / binop / etc. is forbidden.
                    if isinstance(node.value, (ast.Constant, ast.Call, ast.BinOp, ast.Set, ast.List, ast.Tuple, ast.Dict)):
                        violations.append(
                            {
                                "code": "FORBIDDEN_AUTHORITY_ASSIGN",
                                "name": t.id,
                                "lineno": node.lineno,
                                "severity": "critical",
                                "message": (
                                    f"Shim must not locally define authority constant {t.id}; "
                                    "re-export from canonical modules only."
                                ),
                            }
                        )

    # ImportFrom of FORBIDDEN names is allowed (re-export). Direct Assign of
    # frozenset / float literals for those names is caught above.

    lower_lines = text.splitlines()
    for i, line in enumerate(lower_lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        # Docstring / module banner mentions are OK when in triple-quoted blocks;
        # simple heuristic: skip lines inside the top module docstring (first 40 lines
        # that are commentary about bans).
        for needle, code in FORBIDDEN_BODY_NEEDLES:
            if needle in line:
                # Allow mentions inside string literals that are documentation-only
                # when the line is a pure string / comment already skipped.
                if "canonical" in line.lower() and "must not" in line.lower():
                    continue
                if line.lstrip().startswith(("\"", "'")):
                    continue
                violations.append(
                    {
                        "code": code,
                        "needle": needle,
                        "lineno": i,
                        "severity": "critical",
                        "message": f"Shim line embeds forbidden authority pattern: {needle!r}",
                        "line": stripped[:200],
                    }
                )

    # Must delegate to canonical engine.
    required_needles = (
        "AutonomousExecutionSimulatorV11",
        "NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1",
        "CANONICAL_EXECUTION_ENGINE",
    )
    missing = [n for n in required_needles if n not in text]
    for n in missing:
        violations.append(
            {
                "code": "MISSING_CANONICAL_DELEGATION",
                "name": n,
                "lineno": 0,
                "severity": "critical",
                "message": f"Shim must reference canonical delegation symbol {n}",
            }
        )

    return {
        "schema": "nexus_execution_shim_authority_trap_v1",
        "generated_at": _utc(),
        "lane": "V11_1_C5_EXECUTION_SHIM",
        "shim_path": SHIM_REL,
        "passed": len(violations) == 0,
        "violation_count": len(violations),
        "violations": violations,
        "canonical_execution_engine": CANONICAL_EXECUTION,
        "canonical_fill_engine": CANONICAL_FILL,
        "canonical_execution_authority_count": 1,
        "canonical_fill_authority_count": 1,
        "shim_embedded_fill_authority_count": 0 if len(violations) == 0 else 1,
        "forbidden_func_defs": sorted(FORBIDDEN_FUNC_DEFS),
        "forbidden_assign_names": sorted(FORBIDDEN_ASSIGN_NAMES),
    }


def evaluate(root: Path) -> dict[str, Any]:
    path = root / SHIM_REL
    if not path.exists():
        return {
            "schema": "nexus_execution_shim_authority_trap_v1",
            "generated_at": _utc(),
            "passed": False,
            "violation_count": 1,
            "violations": [
                {
                    "code": "SHIM_MISSING",
                    "severity": "critical",
                    "message": f"Expected shim at {SHIM_REL}",
                }
            ],
            "canonical_execution_authority_count": 1,
            "canonical_fill_authority_count": 1,
            "shim_embedded_fill_authority_count": 1,
        }
    return scan_shim(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="CI gate: execution shim authority traps")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out_dir or (
        root / "artifacts" / "readiness" / "immutable" / "v11_1_execution_shim"
    )
    out.mkdir(parents=True, exist_ok=True)

    report = evaluate(root)
    write_json(out / "authority_trap_report.json", report)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "violation_count": report["violation_count"],
                "canonical_execution_authority_count": report["canonical_execution_authority_count"],
                "canonical_fill_authority_count": report["canonical_fill_authority_count"],
                "shim_embedded_fill_authority_count": report.get(
                    "shim_embedded_fill_authority_count"
                ),
                "violations": report["violations"][:20],
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
