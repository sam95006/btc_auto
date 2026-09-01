"""Logical data-domain + service-boundary map (NEXUS-EXPERIENCE-1A).

Defines the logical domains (implemented as schemas/tables inside the existing
SaaS PostgreSQL where appropriate — NOT one physical DB per domain today), which
surfaces may read each domain, the Founder-Private physical/security boundary,
and the Social→Founder HARD BAN. These constants are enforced by the boundary
checks + CI tests in nexus_platform/checks.
"""
from __future__ import annotations

# The four separate products/surfaces.
SURFACES = ("corporate", "personal", "enterprise", "founder_private")

# Logical data domains (SaaS PostgreSQL schemas/tables; timeseries may later move
# to Timescale/ClickHouse only when justified).
DOMAINS = (
    "identity", "billing", "entitlements", "corporate", "personal", "market",
    "derivatives", "onchain", "news_social", "reputation", "historical_reaction",
    "enterprise", "audit",
)

# Which SaaS surfaces may read each domain (Founder-Private is a SEPARATE DB).
DOMAIN_READERS = {
    "identity": ("corporate", "personal", "enterprise"),
    "billing": ("corporate", "personal", "enterprise"),
    "entitlements": ("corporate", "personal", "enterprise"),
    "corporate": ("corporate",),
    "personal": ("personal",),
    "market": ("corporate", "personal", "enterprise"),
    "derivatives": ("personal", "enterprise"),
    "onchain": ("personal", "enterprise"),
    "news_social": ("personal", "enterprise"),   # NEVER founder_private
    "reputation": ("personal", "enterprise"),     # NEVER founder_private
    "historical_reaction": ("personal", "enterprise"),
    "enterprise": ("enterprise",),
    "audit": ("corporate", "personal", "enterprise"),
}

# Founder-Private is a separate physical/security boundary. The SaaS surfaces
# never access it; it stores orders/positions/PnL/ledger/lessons/private AI.
FOUNDER_PRIVATE_ISOLATED = True

# Backend packages that make up the Founder private-trading runtime. These MUST
# NOT import Personal news/social/reputation modules (Social→Founder hard ban),
# and the SaaS surfaces must not import these.
FOUNDER_RUNTIME_PACKAGES = (
    "founder_operator", "nexus_execution", "nexus_demo_execution",
    "nexus_bybit_demo_readiness", "nexus_founder_demo_monitor",
    "nexus_mechanism_execution_compiler", "nexus_private_cert",
    "nexus_private_control", "nexus_private_core_redteam",
)

# Namespaces/terms the Founder runtime must NEVER consume (Personal social/KOL
# intelligence). Enforced at code-import level by the boundary checker.
SOCIAL_BANNED_IMPORT_TERMS = (
    "news_social", "social_intel", "kol", "creator_score", "creator_track",
    "social_sentiment", "social_hype", "lunarcrush", "kaito",
)

# Domains a Founder runtime import must never touch.
FOUNDER_BANNED_DOMAINS = ("news_social", "reputation")


def readers_for(domain: str) -> tuple[str, ...]:
    return DOMAIN_READERS.get(domain, ())


def founder_may_read(domain: str) -> bool:
    """The Founder-Private boundary never reads SaaS domains, and NEVER
    news_social/reputation regardless."""
    return False
