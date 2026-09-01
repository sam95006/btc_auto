-- 0016_platform_foundation.sql
-- NEXUS-EXPERIENCE-1A: product-architecture foundation persistence (DESIGN).
-- Additive and non-destructive. Persists commercial subscriptions + the Starter
-- trial window, the entitlement capability registry, and the data-licensing
-- governance registry. Aligns with backend/nexus_platform/* contracts. Isolated
-- from Founder private trading: no trading/execution/credential tables here.
-- Application is deferred until Workstream B/D needs persisted subscriptions;
-- the code contracts (plans/trial/entitlements) work stateless meanwhile.

-- Extend the existing BILLING-1 subscriptions table (0008) with the Starter-trial
-- window. Additive columns only — the canonical subscription table is reused.
ALTER TABLE nexus.subscriptions ADD COLUMN IF NOT EXISTS billing_interval TEXT;         -- month | year | NULL
ALTER TABLE nexus.subscriptions ADD COLUMN IF NOT EXISTS trial_code TEXT;               -- e.g. STARTER_TRIAL_30D
ALTER TABLE nexus.subscriptions ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ;  -- = account registered_at
ALTER TABLE nexus.subscriptions ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMPTZ;     -- = trial_started_at + 30d
CREATE INDEX IF NOT EXISTS idx_subscriptions_trial_ends ON nexus.subscriptions (trial_ends_at);

-- Entitlement capability registry (admin-inspectable, backend-authoritative).
-- Four independent dimensions so readiness is never binary/inferred from UI code:
-- plan grant, backend service state, product build state, and data-license state.
CREATE TABLE IF NOT EXISTS nexus.entitlement_registry (
    capability_id   TEXT NOT NULL,
    plan_code       TEXT NOT NULL,
    grant_tier      TEXT NOT NULL DEFAULT 'none',        -- full | limited | none
    backend_state   TEXT NOT NULL DEFAULT 'absent',      -- ready | partial | absent
    product_state   TEXT NOT NULL DEFAULT 'coming_soon', -- available | beta | partial | coming_soon
    data_state      TEXT NOT NULL DEFAULT 'unlicensed',  -- licensed | unlicensed
    domain          TEXT NOT NULL DEFAULT 'personal',
    evidence        TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (capability_id, plan_code)
);

-- Data-licensing governance registry (no secrets; governance metadata only).
CREATE TABLE IF NOT EXISTS nexus.data_licenses (
    dataset               TEXT PRIMARY KEY,
    provider              TEXT NOT NULL,                -- canonical publisher identity
    domain                TEXT NOT NULL,
    license_status        TEXT NOT NULL DEFAULT 'not_licensed', -- in_use | evaluating | not_licensed
    commercial_use        BOOLEAN NOT NULL DEFAULT FALSE,
    redistribution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    attribution_required  BOOLEAN NOT NULL DEFAULT TRUE,
    cache_allowed         BOOLEAN NOT NULL DEFAULT FALSE,
    derived_data_allowed  BOOLEAN NOT NULL DEFAULT FALSE,
    retention_limit_days  INTEGER,
    rate_limit_per_min    INTEGER,
    notes                 TEXT NOT NULL DEFAULT '',
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
