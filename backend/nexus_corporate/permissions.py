"""Corporate RBAC scopes. Business/website only — never Founder trading."""

from __future__ import annotations

# Full OWNER business permission set (mirrors migration 0015 seed).
OWNER_PERMISSIONS = frozenset({
    "website.read", "website.write",
    "content.read", "content.write", "content.publish",
    "products.read", "products.write",
    "pricing.read", "pricing.write",
    "showcase.read", "showcase.write",
    "users.read", "users.write",
    "members.read", "members.write",
    "enterprise.read", "enterprise.write",
    "leads.read", "leads.write",
    "contacts.read",
    "analytics.read",
    "audit.read",
    "admins.read", "admins.write",
    "settings.read", "settings.write",
    "security.read", "status.read",
    "seo.read", "seo.write",
})

# Scopes that must NEVER be grantable through Corporate (defensive allow-list
# boundary): Founder private trading / execution / credentials are out of scope.
FORBIDDEN_SCOPES = frozenset({
    "founder", "trading.execute", "bybit", "order.submit", "leverage",
    "private.pnl", "private.lessons", "exchange.write",
})


def role_has(permissions: set[str] | frozenset[str], scope: str) -> bool:
    return scope in permissions
