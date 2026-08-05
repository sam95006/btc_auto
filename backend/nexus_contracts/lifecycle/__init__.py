"""Canonical multi-scope lifecycle vocabulary (V11.1 Founder C2).

Does NOT collapse Decision / Session / Intent / Order / Position / Reflection
into one state machine. Each scope remains independent; this package owns:

* ontology (states, terminals, owners)
* explicit Session↔ControlPlane adapter (never silent name identity)
* cross-lifecycle invariants + terminal compatibility
* BLOCKED / BLOCKED_AMBIGUOUS semantics
* snapshot validation used by CI
"""
from __future__ import annotations

from backend.nexus_contracts.lifecycle.transitions import (
    CROSS_SCOPE_TRANSITIONS,
    transition_mapping_report,
)
from backend.nexus_contracts.lifecycle.adapters import (
    ADAPTER_CONTRACT_ID,
    ControlPlaneSessionAdapter,
    adapter_contract_present,
    map_control_to_session,
    map_session_to_control,
)
from backend.nexus_contracts.lifecycle.blocked_ambiguous import (
    BLOCKED_AMBIGUOUS_SCOPES,
    blocked_ambiguous_policy,
)
from backend.nexus_contracts.lifecycle.compatibility import (
    TERMINAL_COMPATIBILITY_TABLE,
    terminal_pair_status,
)
from backend.nexus_contracts.lifecycle.invariants import (
    CROSS_LIFECYCLE_INVARIANTS,
    validate_snapshot,
)
from backend.nexus_contracts.lifecycle.ontology import (
    LIFECYCLE_SCOPES,
    ONTOLOGY_SCHEMA,
    ONTOLOGY_VERSION,
    LifecycleScope,
    build_ontology,
)

__all__ = [
    "ADAPTER_CONTRACT_ID",
    "BLOCKED_AMBIGUOUS_SCOPES",
    "CROSS_LIFECYCLE_INVARIANTS",
    "CROSS_SCOPE_TRANSITIONS",
    "ControlPlaneSessionAdapter",
    "LIFECYCLE_SCOPES",
    "ONTOLOGY_SCHEMA",
    "ONTOLOGY_VERSION",
    "TERMINAL_COMPATIBILITY_TABLE",
    "LifecycleScope",
    "adapter_contract_present",
    "blocked_ambiguous_policy",
    "build_ontology",
    "map_control_to_session",
    "map_session_to_control",
    "terminal_pair_status",
    "transition_mapping_report",
    "validate_snapshot",
]
