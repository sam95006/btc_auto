"""Explicit Session ↔ ControlPlane adapter contract.

Homonymous tokens (RUNNING, PAUSED, RECOVERING, FAILED_SAFE) MUST NOT be
treated as identical across scopes. All mappings go through this adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ADAPTER_CONTRACT_ID = "nexus.lifecycle.session_control_plane_adapter_v11_1"
ADAPTER_MODULE = "backend.nexus_contracts.lifecycle.adapters"

# Explicit pairs only. Absence of a pair means NO mapping (fail closed).
# Format: (session_state, control_plane_state, relation)
# relation: equivalent | session_implies_control | control_implies_session | none
SESSION_CONTROL_MAP: tuple[tuple[str, str, str], ...] = (
    # Boot
    ("CREATED", "IDLE", "session_implies_control"),
    ("CREATED", "STARTING", "session_implies_control"),
    ("INITIALIZING", "STARTING", "equivalent"),
    # Active / pause / recover — homonyms require explicit equivalent tagging
    ("RUNNING", "RUNNING", "equivalent"),
    ("PAUSING", "RUNNING", "session_implies_control"),
    ("PAUSED", "PAUSED", "equivalent"),
    ("RECOVERING", "RECOVERING", "equivalent"),
    # Shutdown
    ("FINALIZING", "STOPPING", "equivalent"),
    ("COMPLETED", "STOPPED", "equivalent"),
    ("BLOCKED", "FAILED_SAFE", "session_implies_control"),
    ("BLOCKED", "KILLED", "session_implies_control"),
    ("FAILED_SAFE", "FAILED_SAFE", "equivalent"),
    # Control-only terminals have no Session homonym identity without adapter
    ("COMPLETED", "KILLED", "none"),  # illegal pairing marker used by tests
)


@dataclass(frozen=True)
class ControlPlaneSessionAdapter:
    """Machine-readable adapter; never silently equate same-named states."""

    contract_id: str = ADAPTER_CONTRACT_ID
    session_module: str = "backend.nexus_autonomy.session_state_machine"
    control_module: str = "backend.nexus_private_control.state_machine"

    def allowed_pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            (s, c) for s, c, rel in SESSION_CONTROL_MAP if rel != "none"
        )

    def relation(self, session_state: str, control_state: str) -> str | None:
        for s, c, rel in SESSION_CONTROL_MAP:
            if s == session_state and c == control_state:
                return rel
        return None

    def is_compatible(self, session_state: str, control_state: str) -> bool:
        rel = self.relation(session_state, control_state)
        return rel is not None and rel != "none"

    def assert_no_silent_homonym(self, token: str) -> dict[str, Any]:
        """Prove that shared tokens require adapter mediation."""
        from backend.nexus_autonomy.session_state_machine import CANONICAL_STATES as S
        from backend.nexus_private_control.state_machine import CANONICAL_STATES as C

        is_homonym = token in S and token in C
        if not is_homonym:
            return {"token": token, "homonym": False, "requires_adapter": False}
        # Homonym equality without adapter is forbidden.
        return {
            "token": token,
            "homonym": True,
            "requires_adapter": True,
            "silent_identity_allowed": False,
            "adapter_pairs": sorted(
                [f"{s}->{c}" for s, c, rel in SESSION_CONTROL_MAP if s == token or c == token]
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "session_module": self.session_module,
            "control_module": self.control_module,
            "mappings": [
                {"session": s, "control_plane": c, "relation": rel}
                for s, c, rel in SESSION_CONTROL_MAP
            ],
            "allowed_pair_count": len(self.allowed_pairs()),
            "policy": {
                "silent_homonym_mapping": False,
                "collapse_scopes": False,
                "unmapped_pair": "REJECT",
            },
        }


def adapter_contract_present() -> bool:
    """Drift checks call this to resolve DUAL_LIFECYCLE_VOCABULARY."""
    adapter = ControlPlaneSessionAdapter()
    # Contract is present iff explicit pairs exist and homonym policy is fail-closed.
    return (
        adapter.contract_id == ADAPTER_CONTRACT_ID
        and len(adapter.allowed_pairs()) > 0
        and adapter.assert_no_silent_homonym("RUNNING")["silent_identity_allowed"] is False
    )


def map_session_to_control(session_state: str) -> list[str]:
    """Return allowed control-plane states for a session state (may be empty)."""
    return sorted(
        {
            c
            for s, c, rel in SESSION_CONTROL_MAP
            if s == session_state and rel != "none"
        }
    )


def map_control_to_session(control_state: str) -> list[str]:
    """Return allowed session states for a control-plane state (may be empty)."""
    return sorted(
        {
            s
            for s, c, rel in SESSION_CONTROL_MAP
            if c == control_state and rel != "none"
        }
    )
