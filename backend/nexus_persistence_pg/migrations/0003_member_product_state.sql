-- NEXUS V18.3.8 — member state for the staging-only product surface.
-- Forward-only. No exchange account, credential, order, or Runtime data.

CREATE TABLE IF NOT EXISTS nexus.account_profiles (
    account_id TEXT PRIMARY KEY REFERENCES nexus.accounts(account_id),
    display_name TEXT NOT NULL DEFAULT '',
    avatar_uri TEXT,
    locale TEXT NOT NULL DEFAULT 'zh-TW',
    timezone TEXT NOT NULL DEFAULT 'Asia/Taipei',
    privacy_preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS nexus.member_preferences (
    account_id TEXT PRIMARY KEY REFERENCES nexus.accounts(account_id),
    preferences_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_viewed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS nexus.watchlists (
    watchlist_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    name TEXT NOT NULL DEFAULT '我的觀察',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_watchlists_account_active
    ON nexus.watchlists (account_id, updated_at DESC) WHERE archived_at IS NULL;

CREATE TABLE IF NOT EXISTS nexus.watchlist_items (
    watchlist_id TEXT NOT NULL REFERENCES nexus.watchlists(watchlist_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL DEFAULT 'binance_usdm',
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (watchlist_id, venue, symbol)
);

CREATE TABLE IF NOT EXISTS nexus.notification_preferences (
    account_id TEXT PRIMARY KEY REFERENCES nexus.accounts(account_id),
    in_app_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    market_alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    email_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    muted_symbols JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS nexus.alert_rules (
    rule_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    symbol TEXT NOT NULL,
    condition_type TEXT NOT NULL CHECK (condition_type IN ('price_change_24h', 'volume_24h')),
    condition_json JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_alert_rules_account_enabled
    ON nexus.alert_rules (account_id, enabled);

CREATE TABLE IF NOT EXISTS nexus.notifications (
    notification_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    category TEXT NOT NULL CHECK (category IN ('market', 'watchlist')),
    symbol TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_notifications_account_unread
    ON nexus.notifications (account_id, created_at DESC) WHERE read_at IS NULL;
