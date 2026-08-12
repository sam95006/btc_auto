"""Static + live authority scan across Lane A Decision and Lane B Execution."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.review.r1_decision_execution.lane_loader import LaneImportContext, LaneRoots


CANONICAL = {
    "execution": "backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11",
    "fill": "backend.nexus_execution.fill_engine.try_fill",
    "cost": "backend.nexus_execution.cost_model.COST_MODEL_VERSION",
    "risk": "backend.nexus_execution.risk_gates.RiskLimits",
    "decision_object": "backend.nexus_decision.decision_object.DecisionObject",
    "decision_lifecycle": "backend.nexus_decision.state_machine.DecisionStateMachine",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _scan_decision_intent_minting(roots: LaneRoots) -> list[dict[str, Any]]:
    """Decision orchestrator mints intent_id/position_id without execution authority."""
    orch = roots.lane_a / "backend" / "nexus_decision" / "orchestrator.py"
    text = _read(orch)
    conflicts: list[dict[str, Any]] = []
    if re.search(r'intent_id\s*=\s*.*f?"?intent_', text):
        conflicts.append(
            {
                "id": "AUTH_DECISION_MINTS_INTENT_ID",
                "severity": "critical",
                "domain": "intent",
                "detail": (
                    "DecisionLifecycleOrchestrator assigns intent_id locally on APPROVED_SIMULATED "
                    "without creating backend.nexus_execution OrderIntent via the canonical adapter."
                ),
                "lane_a_claim": "obj.intent_id = ... intent_{uuid}",
                "canonical": "backend.nexus_execution.contracts.OrderIntent",
            }
        )
    if re.search(r'position_id\s*=\s*.*f?"?pos_', text):
        conflicts.append(
            {
                "id": "AUTH_DECISION_MINTS_POSITION_ID",
                "severity": "critical",
                "domain": "position",
                "detail": (
                    "DecisionLifecycleOrchestrator assigns position_id on record→MONITORING "
                    "without PositionRecord authority from AutonomousExecutionSimulatorV11."
                ),
                "lane_a_claim": "obj.position_id = ... pos_{uuid}",
                "canonical": "backend.nexus_execution.contracts.PositionRecord",
            }
        )
    return conflicts


def _scan_risk_dual_authority(roots: LaneRoots) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    orch = _read(roots.lane_a / "backend" / "nexus_decision" / "orchestrator.py")
    if "deterministic_risk_result" in orch:
        conflicts.append(
            {
                "id": "AUTH_DECISION_RISK_BYPASS",
                "severity": "critical",
                "domain": "risk",
                "detail": (
                    "Decision decide() accepts an opaque deterministic_risk_result dict and never "
                    "invokes backend.nexus_execution.risk_gates. Dual risk authority."
                ),
                "lane_a_claim": "deterministic_risk_result.allowed",
                "canonical": CANONICAL["risk"],
            }
        )
    return conflicts


def _scan_cost_version(roots: LaneRoots) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    cost_a = list((roots.lane_a / "backend").rglob("cost_model.py"))
    cost_b = roots.lane_b / "backend" / "nexus_execution" / "cost_model.py"
    versions: dict[str, str] = {}
    if cost_b.is_file():
        m = re.search(r'COST_MODEL_VERSION\s*=\s*"([^"]+)"', _read(cost_b))
        if m:
            versions["nexus_execution"] = m.group(1)
    # Strategy cost semantics may exist on base/lane trees.
    for root in (roots.lane_a, roots.lane_b):
        for path in root.rglob("*cost_semantics*.py"):
            text = _read(path)
            m = re.search(r'(COST_MODEL_VERSION|COST_SEMANTICS_VERSION|VERSION)\s*=\s*"([^"]+)"', text)
            if m:
                versions[str(path.relative_to(root))] = m.group(2)
        for path in root.rglob("cost_semantics.py"):
            text = _read(path)
            for m in re.finditer(r'([A-Z_]*VERSION[A-Z_]*)\s*=\s*"([^"]+)"', text):
                versions[f"{path.relative_to(root)}:{m.group(1)}"] = m.group(2)
    # Also scan review worktree base for strategy cost version (present on e4f30f9).
    review_root = Path(__file__).resolve().parents[3]
    strat = review_root / "backend"
    if strat.is_dir():
        for path in strat.rglob("*cost*.py"):
            if "nexus_execution" in str(path):
                continue
            text = _read(path)
            for m in re.finditer(
                r'(COST_MODEL_VERSION|NEXUS_CONSERVATIVE_EXECUTION_PROXY[A-Z0-9_]*)\s*=\s*"([^"]+)"',
                text,
            ):
                versions[f"base:{path.relative_to(review_root)}:{m.group(1)}"] = m.group(2)
            if "NEXUS_CONSERVATIVE_EXECUTION_PROXY" in text:
                m2 = re.search(r'"(NEXUS_CONSERVATIVE_EXECUTION_PROXY[^"]*)"', text)
                if m2:
                    versions[f"base:{path.relative_to(review_root)}:proxy"] = m2.group(1)

    uniq = sorted(set(versions.values()))
    if len(uniq) > 1:
        conflicts.append(
            {
                "id": "AUTH_COST_MODEL_VERSION_MISMATCH",
                "severity": "critical",
                "domain": "cost",
                "detail": f"Multiple cost model version strings observed: {versions}",
                "versions": versions,
                "canonical": CANONICAL["cost"],
            }
        )
    # Decision never binds cost model version on approval.
    orch = _read(roots.lane_a / "backend" / "nexus_decision" / "orchestrator.py")
    if "COST_MODEL" not in orch and "cost_model" not in orch:
        conflicts.append(
            {
                "id": "AUTH_DECISION_NO_COST_VERSION_BIND",
                "severity": "high",
                "domain": "cost",
                "detail": (
                    "Decision APPROVED_SIMULATED does not bind or validate COST_MODEL_VERSION; "
                    "approval evidence cannot prove which cost authority would price the Intent."
                ),
                "canonical": CANONICAL["cost"],
            }
        )
    return conflicts


def _scan_fill_authority_single(roots: LaneRoots) -> list[dict[str, Any]]:
    """Lane B should declare single canonical fill authority; Decision must not fill."""
    conflicts: list[dict[str, Any]] = []
    with LaneImportContext(roots):
        from backend.nexus_execution.microstructure_realism_v11.adapter import (  # noqa: WPS433
            CANONICAL_EXECUTION_ENGINE_COUNT,
        )

        if CANONICAL_EXECUTION_ENGINE_COUNT != 1:
            conflicts.append(
                {
                    "id": "AUTH_FILL_ENGINE_COUNT_NE_1",
                    "severity": "critical",
                    "domain": "fill",
                    "detail": f"CANONICAL_EXECUTION_ENGINE_COUNT={CANONICAL_EXECUTION_ENGINE_COUNT}",
                }
            )
    # Decision must not import fill_engine
    for path in (roots.lane_a / "backend" / "nexus_decision").rglob("*.py"):
        text = _read(path)
        if "fill_engine" in text or "try_fill" in text:
            conflicts.append(
                {
                    "id": "AUTH_DECISION_IMPORTS_FILL",
                    "severity": "critical",
                    "domain": "fill",
                    "detail": f"{path.name} references fill authority",
                }
            )
    return conflicts


def _scan_bridge_absence(roots: LaneRoots) -> list[dict[str, Any]]:
    """No Decision↔Execution adapter module exists on either lane."""
    conflicts: list[dict[str, Any]] = []
    bridge_names = (
        "decision_execution_bridge",
        "decision_to_intent",
        "intent_bridge",
        "lifecycle_bridge",
    )
    found = []
    for root in (roots.lane_a, roots.lane_b):
        for name in bridge_names:
            hits = list(root.rglob(f"*{name}*"))
            found.extend(str(h) for h in hits)
    # Also search imports
    for root in (roots.lane_a, roots.lane_b):
        for path in root.rglob("*.py"):
            if "nexus_decision" not in str(path) and "nexus_execution" not in str(path):
                continue
            text = _read(path)
            if "nexus_decision" in str(path) and "nexus_execution" in text:
                found.append(str(path))
            if "nexus_execution" in str(path) and "nexus_decision" in text:
                found.append(str(path))
    if not found:
        conflicts.append(
            {
                "id": "AUTH_NO_DECISION_EXECUTION_BRIDGE",
                "severity": "critical",
                "domain": "mapping",
                "detail": (
                    "No Decision↔Intent↔Position bridge module exists. Lanes A and B are "
                    "authority-isolated; mapping invariants are unenforceable at runtime."
                ),
            }
        )
    return conflicts


def _scan_checkpoint_scope(roots: LaneRoots) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    decision_ckpt = roots.lane_a / "backend" / "nexus_decision" / "checkpoint.py"
    if decision_ckpt.is_file():
        conflicts.append(
            {
                "id": "AUTH_DECISION_CHECKPOINT_PARALLEL",
                "severity": "high",
                "domain": "checkpoint",
                "detail": (
                    "DecisionCheckpointStore is a parallel checkpoint authority vs Session/"
                    "recovery envelopes (Lane H MULTI_SCOPE_AUTHORITY_CHECKPOINT)."
                ),
                "module": "backend.nexus_decision.checkpoint.DecisionCheckpointStore",
            }
        )
    return conflicts


def scan_authorities(roots: LaneRoots | None = None) -> dict[str, Any]:
    from tools.review.r1_decision_execution.lane_loader import resolve_lane_roots

    roots = roots or resolve_lane_roots()
    conflicts: list[dict[str, Any]] = []
    conflicts.extend(_scan_decision_intent_minting(roots))
    conflicts.extend(_scan_risk_dual_authority(roots))
    conflicts.extend(_scan_cost_version(roots))
    conflicts.extend(_scan_fill_authority_single(roots))
    conflicts.extend(_scan_bridge_absence(roots))
    conflicts.extend(_scan_checkpoint_scope(roots))

    # Live confirmation of Lane B single engine + cost version.
    with LaneImportContext(roots):
        from backend.nexus_execution.cost_model import COST_MODEL_VERSION  # noqa: WPS433
        from backend.nexus_execution.microstructure_realism_v11 import (  # noqa: WPS433
            CANONICAL_EXECUTION_ENGINE,
            CANONICAL_EXECUTION_ENGINE_COUNT,
        )
        from backend.nexus_decision.decision_object import SCHEMA_VERSION  # noqa: WPS433

        live = {
            "cost_model_version": COST_MODEL_VERSION,
            "canonical_execution_engine": CANONICAL_EXECUTION_ENGINE,
            "canonical_execution_engine_count": CANONICAL_EXECUTION_ENGINE_COUNT,
            "decision_schema_version": SCHEMA_VERSION,
        }

    return {
        "canonical": CANONICAL,
        "authority_conflicts": conflicts,
        "authority_conflict_count": len(conflicts),
        "live": live,
        "lane_a": str(roots.lane_a),
        "lane_b": str(roots.lane_b),
        "lane_a_source": roots.lane_a_source,
        "lane_b_source": roots.lane_b_source,
    }
