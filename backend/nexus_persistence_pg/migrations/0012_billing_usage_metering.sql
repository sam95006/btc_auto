-- NEXUS BILLING-6 — durable usage metering + idempotency.
-- Forward-only, additive migration. No destructive drops. No card/PII storage.
-- usage_counters holds per-window consumption; usage_events enforces per-request
-- idempotency so a client/network retry cannot double-count.

CREATE TABLE IF NOT EXISTS nexus.usage_counters (
    account_id     TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    quota_code     TEXT NOT NULL,
    window_type    TEXT NOT NULL,
    window_start   TIMESTAMPTZ NOT NULL,
    used           INTEGER NOT NULL DEFAULT 0,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (account_id, quota_code, window_type, window_start)
);

CREATE INDEX IF NOT EXISTS ix_usage_counters_account
    ON nexus.usage_counters (account_id, quota_code);

CREATE TABLE IF NOT EXISTS nexus.usage_events (
    usage_event_id  TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    quota_code      TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    amount          INTEGER NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_usage_events_idem
    ON nexus.usage_events (account_id, quota_code, idempotency_key);
