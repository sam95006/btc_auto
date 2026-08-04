"""Process-versus-outcome classification for Private Core completed trades.

Canonical classes:
  GOOD_PROCESS_WIN / GOOD_PROCESS_LOSS / BAD_PROCESS_WIN / BAD_PROCESS_LOSS / UNDETERMINED

Process quality is derived from explicit evidence — never from PnL alone.
"""
from __future__ import annotations

from typing import Any


CANONICAL_CLASSES = (
    "GOOD_PROCESS_WIN",
    "GOOD_PROCESS_LOSS",
    "BAD_PROCESS_WIN",
    "BAD_PROCESS_LOSS",
    "UNDETERMINED",
)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def derive_process_quality(evidence: dict[str, Any] | None) -> str:
    """Return GOOD | BAD | UNDETERMINED from structured process evidence."""
    if not isinstance(evidence, dict) or not evidence:
        return "UNDETERMINED"

    required_keys = (
        "rule_violation_ids",
        "missing_evidence_ids",
        "risk_gate_results",
        "cost_gate_results",
        "data_quality_results",
        "prohibited_action_results",
        "entry_rule_compliance",
        "exit_rule_compliance",
    )
    present = [k for k in required_keys if k in evidence]
    if len(present) < 3:
        # Too little structured evidence to adjudicate process quality.
        return "UNDETERMINED"

    violations = _as_list(evidence.get("rule_violation_ids"))
    missing = _as_list(evidence.get("missing_evidence_ids"))
    prohibited = _as_list(evidence.get("prohibited_action_results"))
    risk = evidence.get("risk_gate_results") or {}
    cost = evidence.get("cost_gate_results") or {}
    data_q = evidence.get("data_quality_results") or {}
    entry = str(evidence.get("entry_rule_compliance") or "").upper()
    exit_c = str(evidence.get("exit_rule_compliance") or "").upper()

    bad_signals = 0
    if violations:
        bad_signals += 1
    if missing:
        bad_signals += 1
    if any(str(x).upper() in {"FAIL", "VIOLATION", "REJECTED", "TRUE", "1"} for x in prohibited):
        bad_signals += 1
    if isinstance(risk, dict) and str(risk.get("status") or risk.get("result") or "").upper() in {
        "FAIL",
        "BLOCKED",
        "VIOLATION",
    }:
        bad_signals += 1
    if isinstance(cost, dict) and str(cost.get("status") or cost.get("result") or "").upper() in {
        "FAIL",
        "DESTROYED",
        "VIOLATION",
    }:
        bad_signals += 1
    if isinstance(data_q, dict) and str(data_q.get("status") or data_q.get("result") or "").upper() in {
        "FAIL",
        "STALE",
        "INVALID",
    }:
        bad_signals += 1
    if entry in {"FAIL", "VIOLATION", "NONCOMPLIANT"}:
        bad_signals += 1
    if exit_c in {"FAIL", "VIOLATION", "NONCOMPLIANT"}:
        bad_signals += 1

    if bad_signals > 0:
        return "BAD"
    if entry in {"PASS", "COMPLIANT"} and exit_c in {"PASS", "COMPLIANT", ""}:
        return "GOOD"
    if entry or exit_c or risk or cost or data_q:
        return "GOOD"
    return "UNDETERMINED"


def classify_completed_trade(*, pnl: float | None, process_evidence: dict[str, Any] | None) -> str:
    quality = derive_process_quality(process_evidence)
    if quality == "UNDETERMINED" or pnl is None:
        return "UNDETERMINED"
    win = pnl > 0
    loss = pnl < 0
    if quality == "GOOD":
        if win:
            return "GOOD_PROCESS_WIN"
        if loss:
            return "GOOD_PROCESS_LOSS"
        return "UNDETERMINED"
    if quality == "BAD":
        if win:
            return "BAD_PROCESS_WIN"
        if loss:
            return "BAD_PROCESS_LOSS"
        return "UNDETERMINED"
    return "UNDETERMINED"


def control_fixture_process_evidence(*, bad: bool | None = None, undetermined: bool = False) -> dict[str, Any]:
    """Deterministic evidence injector for harness control fixtures only."""
    if undetermined:
        return {"note": "insufficient_process_evidence"}
    if bad:
        return {
            "rule_violation_ids": ["ENTRY_WITHOUT_COST_GATE"],
            "missing_evidence_ids": [],
            "risk_gate_results": {"status": "PASS"},
            "cost_gate_results": {"status": "FAIL", "result": "DESTROYED"},
            "data_quality_results": {"status": "PASS"},
            "prohibited_action_results": [],
            "entry_rule_compliance": "FAIL",
            "exit_rule_compliance": "PASS",
        }
    return {
        "rule_violation_ids": [],
        "missing_evidence_ids": [],
        "risk_gate_results": {"status": "PASS"},
        "cost_gate_results": {"status": "PASS"},
        "data_quality_results": {"status": "PASS"},
        "prohibited_action_results": [],
        "entry_rule_compliance": "PASS",
        "exit_rule_compliance": "PASS",
    }
