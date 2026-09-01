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


# ---------------------------------------------------------------------------
# Localization. DEFAULT_CONTENT is the site default locale (zh-TW). Per-locale
# overrides below localize the homepage-critical slugs (home hero, products,
# security) plus English for the main pages. Missing (slug, locale) pairs fall
# back to the site default locale — never a mixed-language render is forced by
# code; the OWNER can add any (slug, locale) via the CMS.
# ---------------------------------------------------------------------------
SUPPORTED_LOCALES = ("zh-TW", "en-US", "ja-JP", "ko-KR")
DEFAULT_LOCALE = "zh-TW"

LOCALE_OVERRIDES: dict[str, dict[str, dict[str, Any]]] = {
    "en-US": {
        "home": {"scenes": [
            {"id": "hero", "kicker": "Live market intelligence",
             "title": "You don't need to watch every market data point.",
             "subtitle": "NEXUS turns live prices, volatility, structure and risk into a market intelligence layer you can read at a glance.",
             "primary_cta": {"label": "Get started", "to": "/personal"}},
        ]},
        "products": {"title": "Products", "intro": "One intelligence core, delivered as separate products.",
            "items": [
                {"key": "personal", "title": "Personal Market Intelligence", "to": "/personal", "availability": "available",
                 "summary": "The individual member product — research, watchlists, history and risk context.",
                 "features": [{"label": "Real public market data", "state": "available"},
                              {"label": "Member-safe analysis", "state": "available"},
                              {"label": "Watchlists & history", "state": "available"},
                              {"label": "Risk context", "state": "available"}]},
                {"key": "enterprise", "title": "Enterprise Intelligence Workspace", "to": "/enterprise", "availability": "planned",
                 "summary": "A separate product for teams and organizations.",
                 "features": [{"label": "Organization workspace", "state": "planned"},
                              {"label": "Team RBAC & audit", "state": "planned"},
                              {"label": "Shared intelligence", "state": "planned"},
                              {"label": "Integrations", "state": "contact"}]},
            ]},
        "security": {"title": "Security & Trust", "points": [
            {"title": "Backend source of truth", "body": "The site renders backend data; it never invents business or market numbers."},
            {"title": "Provenance & freshness", "body": "Every live value shows its source and last-updated time."},
            {"title": "No fabricated metrics", "body": "Unavailable data is shown as unavailable — never placeholder numbers."},
            {"title": "Private trading isolation", "body": "Private execution is never exposed or reachable through this website."},
        ]},
        "about": {"title": "About", "vision": "To make hidden market structure legible — safely and transparently.",
                  "body": "A research and intelligence platform. Read-only. Not investment advice."},
        "pricing": {"title": "Pricing", "note": "Plans are managed in the backend and may change.",
                    "tiers": [{"code": "starter", "name": "Starter", "price_display": "—", "period": "mo", "features": ["Core market data", "Basic analysis"]},
                              {"code": "pro", "name": "Pro", "price_display": "—", "period": "mo", "features": ["Advanced analysis", "Reports"]},
                              {"code": "advanced", "name": "Advanced", "price_display": "—", "period": "mo", "features": ["Extended history", "Priority intelligence"]}]},
        "seo": {"default": {"title": "NEXUS · Market Intelligence Platform",
                            "description": "Live prices, volatility, structure and risk — turned into readable market intelligence.",
                            "og_type": "website", "robots": "index,follow"}},
    },
    "ja-JP": {
        "home": {"scenes": [
            {"id": "hero", "kicker": "リアルタイム市場インテリジェンス",
             "title": "市場のすべてを自分で追う必要はありません。",
             "subtitle": "NEXUS はリアルタイムの価格・ボラティリティ・構造・リスクを、ひと目で読める市場インテリジェンスにまとめます。",
             "primary_cta": {"label": "利用を開始", "to": "/personal"}},
        ]},
        "products": {"title": "製品", "intro": "ひとつのインテリジェンス基盤を、別々の製品として提供。",
            "items": [
                {"key": "personal", "title": "パーソナル市場インテリジェンス", "to": "/personal", "availability": "available",
                 "summary": "個人向け製品 — リサーチ、ウォッチリスト、履歴、リスク。",
                 "features": [{"label": "リアルタイム公開市場データ", "state": "available"},
                              {"label": "メンバー向け安全な分析", "state": "available"},
                              {"label": "ウォッチリストと履歴", "state": "available"},
                              {"label": "リスクコンテキスト", "state": "available"}]},
                {"key": "enterprise", "title": "エンタープライズ・ワークスペース", "to": "/enterprise", "availability": "planned",
                 "summary": "チーム・組織向けの別製品。",
                 "features": [{"label": "組織ワークスペース", "state": "planned"},
                              {"label": "チーム RBAC・監査", "state": "planned"},
                              {"label": "共有インテリジェンス", "state": "planned"},
                              {"label": "連携", "state": "contact"}]},
            ]},
        "security": {"title": "セキュリティと信頼", "points": [
            {"title": "バックエンドが真実の源", "body": "サイトはバックエンドのデータを表示し、数値を捏造しません。"},
            {"title": "来歴と鮮度", "body": "すべてのライブ値に出典と更新時刻を表示。"},
            {"title": "捏造しない", "body": "利用不可のデータは利用不可と表示します。"},
            {"title": "プライベート取引の分離", "body": "プライベート実行はこのサイトから一切到達できません。"},
        ]},
    },
    "ko-KR": {
        "home": {"scenes": [
            {"id": "hero", "kicker": "실시간 시장 인텔리전스",
             "title": "시장의 모든 데이터를 직접 볼 필요는 없습니다.",
             "subtitle": "NEXUS는 실시간 가격·변동성·구조·리스크를 한눈에 읽을 수 있는 시장 인텔리전스로 정리합니다.",
             "primary_cta": {"label": "시작하기", "to": "/personal"}},
        ]},
        "products": {"title": "제품", "intro": "하나의 인텔리전스 코어를 별도의 제품으로 제공합니다.",
            "items": [
                {"key": "personal", "title": "퍼스널 시장 인텔리전스", "to": "/personal", "availability": "available",
                 "summary": "개인용 제품 — 리서치, 관심목록, 기록, 리스크.",
                 "features": [{"label": "실시간 공개 시장 데이터", "state": "available"},
                              {"label": "회원 안전 분석", "state": "available"},
                              {"label": "관심목록과 기록", "state": "available"},
                              {"label": "리스크 컨텍스트", "state": "available"}]},
                {"key": "enterprise", "title": "엔터프라이즈 워크스페이스", "to": "/enterprise", "availability": "planned",
                 "summary": "팀·조직을 위한 별도 제품.",
                 "features": [{"label": "조직 워크스페이스", "state": "planned"},
                              {"label": "팀 RBAC·감사", "state": "planned"},
                              {"label": "공유 인텔리전스", "state": "planned"},
                              {"label": "연동", "state": "contact"}]},
            ]},
        "security": {"title": "보안과 신뢰", "points": [
            {"title": "백엔드가 진실의 원천", "body": "사이트는 백엔드 데이터를 표시하며 수치를 만들어내지 않습니다."},
            {"title": "출처와 신선도", "body": "모든 실시간 값에 출처와 갱신 시각을 표시합니다."},
            {"title": "조작 없음", "body": "사용 불가 데이터는 사용 불가로 표시합니다."},
            {"title": "프라이빗 트레이딩 분리", "body": "프라이빗 실행은 이 웹사이트에서 접근할 수 없습니다."},
        ]},
    },
}


def normalize_locale(locale: str | None) -> str:
    loc = (locale or "").strip()
    return loc if loc in SUPPORTED_LOCALES else DEFAULT_LOCALE


def default_published(slug: str, locale: str | None = None) -> dict[str, Any] | None:
    loc = normalize_locale(locale)
    if loc != DEFAULT_LOCALE:
        override = LOCALE_OVERRIDES.get(loc, {}).get(slug)
        if override is not None:
            return override
    return DEFAULT_CONTENT.get(slug)
