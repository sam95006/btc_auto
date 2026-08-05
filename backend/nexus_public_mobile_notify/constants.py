"""PUB-K Mobile Notification & Widget Foundation — constants and hard bans."""

from __future__ import annotations

PACKAGE = "NEXUS_PUBLIC_MOBILE_NOTIFICATION_WIDGET_V1"
SCHEMA = "public_v1_mobile_notification_widget"
LANE = "PUB-K"
LANE_NAME = "MOBILE_NOTIFICATIONS_AND_WIDGET_FOUNDATION"
BRANCH = "feature/public-v1-mobile-notification-widget"
BASE_COMMIT = "39e6b1ae1a40698d02c4cb8de4d80fc412309cfc"

HARD_BANS = frozenset(
    {
        "no_production_notification_credentials",
        "no_apns_production_key",
        "no_fcm_production_server_key",
        "no_app_store_submission",
        "no_google_play_submission",
        "no_live_public_deployment",
        "no_live_billing",
        "no_private_core_import",
        "no_exchange_write",
        "no_mainnet",
        "no_real_money",
        "no_demo_orders",
        "no_shadow_orders",
        "no_copy_trading",
        "no_automated_customer_trading",
        "no_custodial_wallet",
        "no_shared_private_jwt_issuer",
        "no_private_field_in_notification_payload",
        "no_fabricated_live_alert",
        "no_lane_status_json",
        "no_pr26_merge",
        "no_pr27_merge",
    }
)

# Alert kinds exposed to members (public-safe).
ALERT_KINDS = frozenset(
    {
        "DECISION_STATUS",
        "RISK",
        "DATA_STALE",
        "THESIS_INVALIDATED",
        "MARKET_ANOMALY",
    }
)

ALERT_PRIORITIES = frozenset({"LOW", "NORMAL", "HIGH", "CRITICAL"})

# Deep-link route catalog (member surfaces only).
DEEP_LINK_ROUTES = frozenset(
    {
        "home",
        "markets",
        "decisions",
        "decision_detail",
        "evidence",
        "risks",
        "alerts",
        "decision_memory",
        "outcome_review",
        "nex_ai",
        "membership",
        "account",
        "privacy",
        "notification_settings",
        "thesis_monitor",
    }
)

# Fields that must never appear in push / widget / live-activity payloads.
PRIVATE_FIELD_DENYLIST = frozenset(
    {
        "strategy_id",
        "strategy_parameters",
        "private_lesson_id",
        "lesson_id",
        "private_prompt",
        "provider_prompt",
        "order_id",
        "orders",
        "position_id",
        "positions",
        "wallet",
        "wallet_address",
        "account_balance",
        "exchange_credential",
        "api_key",
        "api_secret",
        "execution_route",
        "private_risk_internal",
        "founder_authorization",
        "checkpoint_path",
        "reflection_checkpoint",
        "jwt_private_issuer",
    }
)

# Credential material markers refused in config / env / payload.
PRODUCTION_CREDENTIAL_MARKERS = frozenset(
    {
        "APNS_PRODUCTION_KEY",
        "APNS_PRODUCTION_CERT",
        "APNS_KEY_ID",
        "APNS_TEAM_ID",
        "FCM_SERVER_KEY",
        "FCM_PRODUCTION_SERVER_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS_PRODUCTION",
        "PUSH_PRODUCTION_SECRET",
        "FIREBASE_PRODUCTION_PRIVATE_KEY",
    }
)

PUSH_PROVIDER_MODES = frozenset(
    {
        "STUB",
        "MOCK_IN_MEMORY",
        "LOCAL_FILE_SINK",
        # Production modes exist only as refused tokens.
        "PRODUCTION_APNS_REFUSED",
        "PRODUCTION_FCM_REFUSED",
    }
)

ALLOWED_PUSH_PROVIDER_MODES = frozenset(
    {
        "STUB",
        "MOCK_IN_MEMORY",
        "LOCAL_FILE_SINK",
    }
)

WIDGET_KINDS = frozenset(
    {
        "IOS_HOME_SCREEN",
        "IOS_LOCK_SCREEN",
        "IOS_LIVE_ACTIVITY",
        "ANDROID_HOME_SCREEN",
        "ANDROID_LOCK_SCREEN_GLANCE",
    }
)

OWNED_PATHS = [
    "backend/nexus_public_mobile_notify/",
    "mobile/nexus_notify_prototypes/",
    "tests/public_mobile_notify/",
    "docs/mobile/",
]

SCHEMA_VERSION = "1.0.0"
DEEP_LINK_SCHEME = "nexus"
DEEP_LINK_HOST = "app"
