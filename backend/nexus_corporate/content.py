"""Default published CMS content for the Corporate site.

This is BUSINESS COPY owned by the backend (owner-editable via the admin CMS).
It contains NO live market numbers, prices-as-market-data, or private data —
market values are served separately from the live public market source, and any
figure that is truly dynamic is never hard-coded here.
"""

from __future__ import annotations

from typing import Any

# Section slugs the CMS manages. Public site reads only PUBLISHED bodies.
SLUGS = (
    "site", "home", "products", "products/personal", "products/enterprise",
    "pricing", "security", "about", "showcase", "seo",
)

BRAND_PLACEHOLDER = "NEXUS"  # technical placeholder; backend-configurable, not final brand.

DEFAULT_CONTENT: dict[str, dict[str, Any]] = {
    "site": {
        "brand": {"name": BRAND_PLACEHOLDER, "tagline": "Market Intelligence Platform", "final_brand": False},
        "nav": [
            {"label": "產品", "to": "/products"},
            {"label": "個人版", "to": "/personal"},
            {"label": "企業版", "to": "/enterprise"},
            {"label": "安全", "to": "/security"},
            {"label": "關於", "to": "/about"},
        ],
        "cta": {"personal": {"label": "個人登入", "href": "/personal.html"},
                "enterprise": {"label": "企業登入", "href": "/enterprise.html"}},
        "footer": {
            "note": "唯讀市場情報平台 · 非投資建議 · Read-only market intelligence",
            "columns": [
                {"title": "Product", "links": [{"label": "Personal", "to": "/personal"},
                                                {"label": "Enterprise", "to": "/enterprise"}]},
                {"title": "Company", "links": [{"label": "About", "to": "/about"},
                                                {"label": "Security", "to": "/security"}]},
            ],
        },
    },
    "home": {
        "scenes": [
            {"id": "hero", "kicker": "即時市場情報", "title": "市場很多資料，你不需要全部自己看。",
             "subtitle": "NEXUS 把即時行情、波動、結構與風險，整理成一個可以直接判讀的市場情報層。",
             "primary_cta": {"label": "進入個人版", "to": "/personal"}},
            {"id": "surface", "title": "價格只是表層",
             "body": "Every market shows a price. We render the structure beneath it — flow, context, risk and regime."},
            {"id": "structure", "title": "揭開更深的市場結構",
             "body": "Order-book depth, volatility bands, regime shifts — surfaced as a living intelligence field."},
            {"id": "network", "title": "Live Intelligence Network",
             "body": "A connected graph of instruments, signals and risk, animated from real backend state."},
            {"id": "flow", "title": "Data → Context → Risk → Intelligence",
             "body": "Raw public market data is contextualized, risk-scored, and turned into member-safe intelligence."},
            {"id": "showcase", "title": "Live Market Intelligence",
             "body": "Real BTC / ETH / SOL public data with source, freshness and provenance on every value."},
            {"id": "signal", "title": "Signal · Anomaly · Risk",
             "body": "Member-safe summaries — never private execution, never Founder positions."},
            {"id": "ai", "title": "Intelligence, explained",
             "body": "Deterministic, member-safe analysis. No fabricated numbers, ever."},
            {"id": "personal", "title": "Personal Market Intelligence",
             "body": "The individual member SaaS — watchlists, analysis, history and risk.",
             "cta": {"label": "了解個人版", "to": "/personal"}},
            {"id": "enterprise", "title": "Enterprise Intelligence Workspace",
             "body": "A separate enterprise product for teams and organizations.",
             "cta": {"label": "了解企業版", "to": "/enterprise"}},
            {"id": "security", "title": "Security · Trust · Provenance",
             "body": "Backend is the source of truth. Every live datum shows source and freshness.",
             "cta": {"label": "安全說明", "to": "/security"}},
            {"id": "vision", "title": "A global intelligence platform",
             "body": "Built to scale across markets, surfaces and teams.",
             "primary_cta": {"label": "開始使用", "to": "/products"}},
        ],
    },
    "products": {"title": "產品 / Products", "intro": "One intelligence core, delivered through separate products.",
                 "items": [
                     {"key": "personal", "title": "Personal Market Intelligence",
                      "summary": "The individual member SaaS — research, watchlists, history and risk context.",
                      "to": "/personal", "availability": "available",
                      "features": [
                          {"label": "Real public market data", "state": "available"},
                          {"label": "Member-safe deterministic analysis", "state": "available"},
                          {"label": "Watchlists with plan capacity", "state": "available"},
                          {"label": "Bounded history & risk context", "state": "available"},
                      ]},
                     {"key": "enterprise", "title": "Enterprise Intelligence Workspace",
                      "summary": "A separate product for teams and organizations.",
                      "to": "/enterprise", "availability": "planned",
                      "features": [
                          {"label": "Organization workspace", "state": "planned"},
                          {"label": "Team RBAC & audit", "state": "planned"},
                          {"label": "Shared intelligence", "state": "planned"},
                          {"label": "Integrations", "state": "contact"},
                      ]},
                 ]},
    "products/personal": {"title": "Personal Market Intelligence",
                          "summary": "Member-safe market analysis, watchlists, history and risk.",
                          "features": ["Real public market data", "Deterministic member-safe analysis",
                                       "Watchlists with plan capacity", "Bounded history", "Risk context"],
                          "cta": {"label": "前往個人 App", "href": "/personal.html"}},
    "products/enterprise": {"title": "Enterprise Intelligence Workspace",
                            "summary": "A separate enterprise product.",
                            "features": ["Organization workspace", "Team access", "Enterprise controls"],
                            "cta": {"label": "前往企業 App", "href": "/enterprise.html"}},
    "pricing": {"title": "方案 / Pricing", "note": "Plans are managed in the backend and may change.",
                "tiers": [
                    {"code": "starter", "name": "Starter", "price_display": "—", "period": "mo",
                     "features": ["Core market data", "Basic analysis"]},
                    {"code": "pro", "name": "Pro", "price_display": "—", "period": "mo",
                     "features": ["Advanced analysis", "Reports", "Larger watchlists"]},
                    {"code": "advanced", "name": "Advanced", "price_display": "—", "period": "mo",
                     "features": ["Extended history", "Priority intelligence"]},
                ]},
    "security": {"title": "安全與信任 / Security & Trust",
                 "points": [
                     {"title": "Backend source of truth", "body": "The site renders backend data; it never invents business or market numbers."},
                     {"title": "Provenance & freshness", "body": "Every live value shows its source and last-updated time."},
                     {"title": "No fabricated metrics", "body": "Unavailable data is shown as unavailable — never filled with placeholder numbers."},
                     {"title": "Strict product separation", "body": "Personal, Enterprise and private trading are separate products with separate boundaries."},
                     {"title": "Private trading isolation", "body": "Private execution is never exposed, imported, or reachable through this website."},
                     {"title": "Least-privilege administration", "body": "Owner/admin access is backend-enforced, scoped, and fully audited."},
                     {"title": "Read-only public intelligence", "body": "Public members receive analysis and context — never autonomous trading."},
                     {"title": "Auditability", "body": "Content changes and admin actions are recorded in an append-only audit log."},
                 ]},
    "about": {"title": "關於 / About",
              "vision": "To make hidden market structure legible — safely, transparently, at global scale.",
              "body": "A research and intelligence platform. Read-only. Not investment advice."},
    "showcase": {"symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "history_interval": "1h", "history_limit": 48},
    "seo": {"default": {"title": "NEXUS · Market Intelligence Platform",
                        "description": "A cinematic, real-data market intelligence platform.",
                        "og_type": "website", "robots": "index,follow"}},
}


def default_published(slug: str) -> dict[str, Any] | None:
    return DEFAULT_CONTENT.get(slug)
