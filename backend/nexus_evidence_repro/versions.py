"""Resolve pinned versions bound into reproducibility envelopes."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from backend.nexus_checkpoint.constants import (
    AUTHORITY_ID as CHECKPOINT_AUTHORITY_ID,
    ENVELOPE_SCHEMA,
    ENVELOPE_SCHEMA_VERSION,
)
from backend.nexus_decision.decision_object import SCHEMA_VERSION as DECISION_SCHEMA_VERSION
from backend.nexus_evidence_repro.constants import RISK_GATES_AUTHORITY, RISK_GATES_VERSION
from backend.nexus_execution.cost_model import COST_MODEL_VERSION
from backend.nexus_execution.risk_gates import (
    FORBIDDEN_ACTIONS,
    FORBIDDEN_LEVERAGE_VALUES,
    MAX_LEVERAGE_CEILING,
)


def _git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def risk_gates_fingerprint() -> str:
    """Stable digest of immutable risk-gate invariants (not a profitability metric)."""
    payload = {
        "authority": RISK_GATES_AUTHORITY,
        "version": RISK_GATES_VERSION,
        "max_leverage_ceiling": MAX_LEVERAGE_CEILING,
        "forbidden_leverage_values": sorted(FORBIDDEN_LEVERAGE_VALUES),
        "forbidden_actions": sorted(FORBIDDEN_ACTIONS),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def resolve_version_pins(root: Path | str | None = None) -> dict[str, Any]:
    """Collect code/cost/risk/checkpoint version pins for envelope binding."""
    repo = Path(root) if root else Path(__file__).resolve().parents[2]
    return {
        "code_version": _git_head(repo),
        "decision_schema_version": DECISION_SCHEMA_VERSION,
        "cost_version": COST_MODEL_VERSION,
        "risk_version": RISK_GATES_VERSION,
        "risk_authority": RISK_GATES_AUTHORITY,
        "risk_gates_fingerprint": risk_gates_fingerprint(),
        "checkpoint_version": {
            "schema": ENVELOPE_SCHEMA,
            "schema_version": ENVELOPE_SCHEMA_VERSION,
            "authority_id": CHECKPOINT_AUTHORITY_ID,
        },
        "checkpoint_version_id": f"{ENVELOPE_SCHEMA}:{ENVELOPE_SCHEMA_VERSION}",
    }
