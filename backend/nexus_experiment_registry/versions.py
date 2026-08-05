"""Version pin resolution for experiment registry records."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from backend.nexus_evidence_repro.constants import RISK_GATES_VERSION
from backend.nexus_evidence_repro.versions import risk_gates_fingerprint
from backend.nexus_execution.cost_model import COST_MODEL_VERSION
from backend.nexus_execution.execution_simulator_v1_1 import SIMULATOR_VERSION
from backend.nexus_experiment_registry.constants import FEATURE_VERSION_DEFAULT


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


def resolve_version_pins(root: Path | str | None = None) -> dict[str, Any]:
    """Collect code/feature/cost/risk/execution pins for experiment binding."""
    repo = Path(root) if root else Path(__file__).resolve().parents[2]
    code = _git_head(repo)
    return {
        "code_checksum": code,
        "feature_version": FEATURE_VERSION_DEFAULT,
        "cost_version": COST_MODEL_VERSION,
        "risk_version": RISK_GATES_VERSION,
        "risk_gates_fingerprint": risk_gates_fingerprint(),
        "execution_version": SIMULATOR_VERSION,
    }
