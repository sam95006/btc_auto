"""Constants for PostgreSQL persistence foundation."""
from __future__ import annotations

SCHEMA = "v18_3_3_persistence_pg_foundation"
SCHEMA_VERSION = 2
PACKAGE = "backend.nexus_persistence_pg"

# Logical PG schema namespace (not live-trading policy).
PG_SCHEMA_NAME = "nexus"

HARD_BANS: tuple[str, ...] = (
    "no_auto_apply_lessons_to_live_policy",
    "no_alter_leverage_via_ai_lesson",
    "no_alter_risk_limits_via_ai_lesson",
    "no_alter_eligibility_gates_via_ai_lesson",
    "no_exchange_write",
    "no_demo_order",
    "no_mainnet",
)
