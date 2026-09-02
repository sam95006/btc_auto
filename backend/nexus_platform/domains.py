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


# --- Founder / shared-market clarification (1A.1) ---
# Founder-Private NEVER reads a SaaS DB domain directly (physical/security
# boundary). It MAY, where the certified private architecture permits, consume
# separately-authorized, SAFE market-data SERVICE outputs (a service-level feed) —
# which is NOT the same as direct SaaS database access. Social/KOL remains HARD
# BANNED for Founder. No trading-runtime change.
FOUNDER_DIRECT_SAAS_DB_ACCESS = False          # never
# Explicit ALLOWLIST — Founder may consume ONLY separately-authorized safe MARKET
# SERVICE outputs. Every other SaaS domain (identity/billing/entitlements/corporate/
# personal/derivatives/onchain/news_social/reputation/historical_reaction/enterprise/
# audit) and unknown domains are denied by this contract. Social/KOL stays hard-banned.
FOUNDER_SAFE_SERVICE_ALLOWED_DOMAINS = ("market",)


def readers_for(domain: str) -> tuple[str, ...]:
    return DOMAIN_READERS.get(domain, ())


def founder_may_read_saas_db(_domain: str) -> bool:
    """Founder-Private never reads a SaaS DB domain directly. Always False."""
    return False


# Backwards-compatible alias (direct DB access is what this asserts).
founder_may_read = founder_may_read_saas_db


def founder_may_consume_service_market(domain: str) -> bool:
    """Founder may consume ONLY separately-authorized SAFE market-data SERVICE
    outputs (not DB access). Explicit allowlist: only 'market'; every other SaaS
    domain and unknown domains are denied. Social/KOL remains hard-banned."""
    return domain in FOUNDER_SAFE_SERVICE_ALLOWED_DOMAINS
