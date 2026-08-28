-- NEXUS BILLING-3 — durable billing event idempotency ledger.
-- Forward-only, additive migration. No destructive drops. No card/PII storage.
-- The UNIQUE (provider, provider_event_id) constraint is the durable,
-- concurrency-safe idempotency mechanism: a provider event is applied at most
-- once regardless of duplicate delivery.

CREATE TABLE IF NOT EXISTS nexus.billing_events (
    billing_event_id          TEXT PRIMARY KEY,
    provider                  TEXT NOT NULL,
    provider_event_id         TEXT NOT NULL,
    event_type                TEXT NOT NULL,
    account_id                TEXT REFERENCES nexus.accounts(account_id),
    provider_customer_id      TEXT,
    provider_subscription_id  TEXT,
    target_plan_code          TEXT,
    processing_status         TEXT NOT NULL DEFAULT 'received',
    error_class               TEXT,
    payload_hash              TEXT,
    received_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at              TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_billing_events_provider_event
    ON nexus.billing_events (provider, provider_event_id);

CREATE INDEX IF NOT EXISTS ix_billing_events_account
    ON nexus.billing_events (account_id);

CREATE INDEX IF NOT EXISTS ix_billing_events_status
    ON nexus.billing_events (processing_status);
