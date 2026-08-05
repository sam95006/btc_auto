"""CI trap: Decision must not mint decorative Intent/Position IDs; bridge required."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORCH = ROOT / "backend" / "nexus_decision" / "orchestrator.py"
BRIDGE = ROOT / "backend" / "nexus_decision" / "execution_bridge.py"
COST_SEM = ROOT / "backend" / "nexus_strategy_engine" / "cost_semantics.py"
COST_MODEL = ROOT / "backend" / "nexus_execution" / "cost_model.py"
STATE = ROOT / "backend" / "nexus_decision" / "state_machine.py"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    findings: list[dict] = []
    orch = ORCH.read_text(encoding="utf-8") if ORCH.is_file() else ""
    if re.search(r'intent_id\s*=\s*.*f["\']intent_|intent_id\s*=\s*.*["\']intent_|intent_\{', orch):
        findings.append({"id": "AUTH_DECISION_MINTS_INTENT_ID", "status": "REMAINING"})
    if re.search(r'position_id\s*=\s*.*f["\']pos_|position_id\s*=\s*.*["\']pos_|pos_\{', orch):
        findings.append({"id": "AUTH_DECISION_MINTS_POSITION_ID", "status": "REMAINING"})
    if not BRIDGE.is_file():
        findings.append({"id": "AUTH_NO_DECISION_EXECUTION_BRIDGE", "status": "REMAINING"})
    if "evaluate_risk" not in orch and "evaluate_intent" not in orch:
        findings.append({"id": "AUTH_DECISION_RISK_BYPASS", "status": "REMAINING"})
    if "COST_MODEL_VERSION" not in orch and "cost_model" not in orch:
        findings.append({"id": "AUTH_DECISION_NO_COST_VERSION_BIND", "status": "REMAINING"})
    if COST_SEM.is_file() and COST_MODEL.is_file():
        sem = COST_SEM.read_text(encoding="utf-8")
        cm = COST_MODEL.read_text(encoding="utf-8")
        m_cm = re.search(r'COST_MODEL_VERSION\s*=\s*"([^"]+)"', cm)
        # cost_semantics must import canonical, not assign a divergent literal.
        if m_cm and re.search(r'COST_MODEL_VERSION\s*=\s*"(?!founder-conservative)', sem):
            if 'COST_MODEL_VERSION = "' in sem and "from backend.nexus_execution.cost_model import" not in sem:
                findings.append({"id": "AUTH_COST_MODEL_VERSION_MISMATCH", "status": "REMAINING"})
    sm = STATE.read_text(encoding="utf-8") if STATE.is_file() else ""
    if re.search(r'"MONITORING":\s*frozenset\(\{[^}]*UNDER_REVIEW', sm):
        findings.append({"id": "VOCAB_MONITORING_SKIP_EXIT", "status": "REMAINING"})

    status = "PASS" if not findings else "FAIL"
    payload = {
        "schema": "v11_1_r1_ab_ci_gate_decision_execution_bridge",
        "created_at": _utc(),
        "status": status,
        "remaining": findings,
        "checks": [
            "no_decorative_intent_mint",
            "no_decorative_position_mint",
            "bridge_module_present",
            "risk_gate_invoked",
            "cost_model_bound",
            "monitoring_requires_exit",
        ],
    }
    out = ROOT / "artifacts" / "readiness" / "immutable" / "v11_1_r1_ab_remediation"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ci_gate.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
