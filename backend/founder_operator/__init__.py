"""Founder Private Operator UI — read-only private operational surface.

Fail-closed. Never part of the public member product session.
No exchange writes. No Demo/Shadow/mainnet order paths.
"""
from __future__ import annotations

from backend.founder_operator.snapshot import (
    OPERATOR_PANEL_IDS,
    build_founder_operator_snapshot,
)

__all__ = [
    "OPERATOR_PANEL_IDS",
    "build_founder_operator_snapshot",
]
