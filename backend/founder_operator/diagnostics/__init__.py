"""UX-C Founder Operator Diagnostics — V16 research observe panels.

Founder-only. Observe / authorize research only.
Never mainnet, never real-trade shortcuts, never member-accessible.
"""
from __future__ import annotations

from backend.founder_operator.diagnostics.panels import (
    DIAGNOSTIC_PANEL_IDS,
    assert_no_forbidden_keys,
    build_founder_diagnostics_snapshot,
)
from backend.founder_operator.diagnostics.research_auth import (
    authorize_research_observe,
)
from backend.founder_operator.diagnostics.three_pass import run_three_passes

__all__ = [
    "DIAGNOSTIC_PANEL_IDS",
    "assert_no_forbidden_keys",
    "authorize_research_observe",
    "build_founder_diagnostics_snapshot",
    "run_three_passes",
]
