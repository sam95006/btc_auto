"""NEXUS Public Subscription Product Boundary (PUB17-D).

Members buy: Market Data, AI Intelligence, Decision Context, Risk Explanation,
Alerts, Historical Comparisons, Global Market Briefs.

Members do NOT buy: Auto Trading, Copy Trading, Exchange Execution,
Private Strategy, Founder Portfolio Access.

member_execution_control_count MUST remain 0.
"""
from __future__ import annotations

from backend.nexus_public_subscription_boundary.constants import (
    HARD_BANS,
    LANE,
    LANE_NAME,
    MEMBER_BUYABLE_PRODUCT_IDS,
    MEMBER_FORBIDDEN_PRODUCT_IDS,
    PACKAGE,
    SCHEMA_VERSION,
)
from backend.nexus_public_subscription_boundary.execution_control import (
    count_member_execution_controls,
)
from backend.nexus_public_subscription_boundary.routes import (
    create_subscription_boundary_blueprint,
    register_subscription_boundary_routes,
)
from backend.nexus_public_subscription_boundary.service import SubscriptionBoundaryService

__all__ = [
    "HARD_BANS",
    "LANE",
    "LANE_NAME",
    "MEMBER_BUYABLE_PRODUCT_IDS",
    "MEMBER_FORBIDDEN_PRODUCT_IDS",
    "PACKAGE",
    "SCHEMA_VERSION",
    "SubscriptionBoundaryService",
    "count_member_execution_controls",
    "create_subscription_boundary_blueprint",
    "register_subscription_boundary_routes",
]
