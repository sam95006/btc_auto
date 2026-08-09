"""Paid-beta retention constants — no fabricated identity, no production billing."""
from __future__ import annotations

PACKAGE = "NEXUS_PAID_BETA_IDENTITY_V18_2_21"
SCHEMA = "paid_beta_identity_v18_2_21"
MARKER = "PUBLIC_V18_2_21_PAID_BETA_IDENTITY_HEAD"
AUTH_REQUIRED_BLOCKER = "AUTH_REQUIRED_BLOCKER"

ALERT_EVENT_TYPES = (
    "RADAR_NEW",
    "RADAR_UP",
    "RADAR_DOWN",
    "RADAR_OUT",
    "STATE_CHANGE",
    "ACTIVITY_ACCELERATION",
    "OI_CHANGE",
    "FUNDING_EXTREME",
    "RISK_CHANGE",
    "DATA_DEGRADED",
    "WATCHLIST_EVENT",
)

SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")

# Anti-spam defaults (server-side).
DEFAULT_DEDUP_WINDOW_SEC = 900
DEFAULT_COOLDOWN_SEC = 300
DEFAULT_MAX_PER_SYMBOL_HOUR = 6

ONBOARDING_STEPS = (
    {"id": "market_state", "title": "Market State", "href": "/overview"},
    {"id": "live_radar", "title": "Live Radar", "href": "/overview"},
    {"id": "watchlist_alerts", "title": "Watchlist + Alerts", "href": "/watchlist"},
)

WATCHLIST_LIMIT = 30
NOTIFICATION_RETENTION = 200

HARD_BANS = frozenset(
    {
        "no_fake_identity",
        "no_browser_local_canonical_watchlist",
        "no_production_billing_activation",
        "no_frontend_only_paid_authority",
        "no_large_email_vendor",
        "member_execution_0",
    }
)
