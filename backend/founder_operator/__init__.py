"""Founder Private Operator UI — read-only private operational surface.

Fail-closed. Never part of the public member product session.
No exchange writes. No Demo/Shadow/mainnet order paths.
PUB2-D: panels bind to real/simulated operational surfaces.
"""
from __future__ import annotations

from backend.founder_operator.live_bindings import (
    SURFACE_IDS,
    bind_all_operator_surfaces,
    bind_operator_surface,
)
from backend.founder_operator.snapshot import (
    OPERATOR_PANEL_IDS,
    assert_no_forbidden_keys,
    build_founder_operator_snapshot,
)

__all__ = [
    "OPERATOR_PANEL_IDS",
    "SURFACE_IDS",
    "assert_no_forbidden_keys",
    "bind_all_operator_surfaces",
    "bind_operator_surface",
    "build_founder_operator_snapshot",
]
