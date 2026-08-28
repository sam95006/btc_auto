-- NEXUS BILLING-1 — subscription & plan foundation.
-- Forward-only, additive migration. No destructive drops. No provider linkage.
-- Plans are defined in code (backend/nexus_billing/plans.py); only subscription
-- state is persisted here. One subscription row per account.

CREATE TABLE IF NOT EXISTS nexus.subscriptions (
    subscription_id           TEXT PRIMARY KEY,
    account_id                TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    plan_code                 TEXT NOT NULL DEFAULT 'free',
    status                    TEXT NOT NULL DEFAULT 'inactive',
    provider                  TEXT,
    provider_customer_id      TEXT,
    provider_subscription_id  TEXT,
    started_at                TIMESTAMPTZ,
    current_period_start      TIMESTAMPTZ,
    current_period_end        TIMESTAMPTZ,
    cancel_at                 TIMESTAMPTZ,
    canceled_at               TIMESTAMPTZ,
    ended_at                  TIMESTAMPTZ,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_subscriptions_account
    ON nexus.subscriptions (account_id);

CREATE INDEX IF NOT EXISTS ix_subscriptions_status
    ON nexus.subscriptions (status);
