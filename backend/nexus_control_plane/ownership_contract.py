"""Single Execution Owner contract."""
from __future__ import annotations

from typing import Any

from backend.nexus_control_plane import EXECUTION_OWNER_DEMO_VALIDATION, LEGACY_STAGE3_LABELS
from backend.nexus_control_plane.service_registry import ServiceRegistry


def validate_execution_ownership(registry: ServiceRegistry | None = None) -> dict[str, Any]:
    reg = registry or ServiceRegistry.from_env()
    owners = [r for r in reg.records.values() if r.execution_owner]
    owner_count = len(owners)
    stage3 = reg.get("market_intelligence")
    control = reg.get("control_plane")
    learning = reg.get("learning_engine")

    conflict = owner_count != 1
    owner_name = owners[0].service_name if owner_count == 1 else None
    owner_ok = owner_name is not None and EXECUTION_OWNER_DEMO_VALIDATION in {
        EXECUTION_OWNER_DEMO_VALIDATION,
        "DEMO_VALIDATION_SERVICE",
    }

    # Explicit role capabilities
    stage3_exec = bool(stage3 and stage3.execution_owner)
    stage3_write = bool(stage3 and stage3.exchange_write_capability)
    cp_exec = bool(control and control.execution_owner)
    cp_write = bool(control and control.exchange_write_capability)
    learn_exec = bool(learning and learning.execution_owner)

    degraded = conflict or stage3_exec or stage3_write or cp_exec or cp_write or learn_exec

    return {
        "execution_owner": EXECUTION_OWNER_DEMO_VALIDATION,
        "execution_owner_count": owner_count,
        "execution_owner_service": owner_name,
        "stage3": {
            "execution_capability": False,
            "exchange_write": False,
            "auto_send": False,
            "labels": sorted(LEGACY_STAGE3_LABELS),
            "observed_execution_owner_flag": stage3_exec,
            "observed_exchange_write_flag": stage3_write,
        },
        "control_plane": {
            "execution_capability": False,
            "exchange_write": False,
            "observed_execution_owner_flag": cp_exec,
            "observed_exchange_write_flag": cp_write,
        },
        "learning": {
            "execution_capability": False,
            "observed_execution_owner_flag": learn_exec,
        },
        "ok": not degraded and owner_ok and owner_count == 1,
        "error": "EXECUTION_OWNERSHIP_CONFLICT" if conflict else ("CONTROL_PLANE_DEGRADED" if degraded else ""),
        "deploy_gate": "DEPLOY_GATE_BLOCKED" if degraded or conflict else "OK",
    }
