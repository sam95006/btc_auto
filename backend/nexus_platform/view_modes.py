"""View-mode contract (NEXUS-EXPERIENCE-1A).

VIEW MODE is a PRESENTATION preference (information density) and is strictly
SEPARATE from SUBSCRIPTION (authorization). An Advanced subscriber may use Simple
view; a Starter subscriber may see locked Pro features. Frontend view density
MUST NEVER define authorization — backend entitlements do. This module exists so
that separation is asserted in code + tests.
"""
from __future__ import annotations

VIEW_SIMPLE = "simple"
VIEW_STANDARD = "standard"
VIEW_PRO = "pro"

VIEW_MODES = (VIEW_SIMPLE, VIEW_STANDARD, VIEW_PRO)
DEFAULT_VIEW_MODE = VIEW_SIMPLE

# Visual-hierarchy contract per view mode (answer-first everywhere).
VIEW_HIERARCHY = {
    VIEW_SIMPLE: ("answer",),
    VIEW_STANDARD: ("answer", "evidence"),
    VIEW_PRO: ("answer", "evidence", "data", "tools", "controls"),
}


def is_view_mode(value: str | None) -> bool:
    return value in VIEW_MODES


def normalize_view_mode(value: str | None) -> str:
    return value if is_view_mode(value) else DEFAULT_VIEW_MODE


def authorizes(_view_mode: str) -> bool:
    """View mode NEVER authorizes access. Always False — authorization is the
    entitlement service's responsibility. Present so the guarantee is testable."""
    return False
