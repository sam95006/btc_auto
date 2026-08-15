-- NEXUS V18.3.1 Track B — PostgreSQL foundation
-- Synthetic / staging schema only until explicitly activated.
-- Does NOT alter live Shadow campaign directories or trading policy.

CREATE SCHEMA IF NOT EXISTS nexus;

CREATE TABLE IF NOT EXISTS nexus.schema_migrations (
    version       TEXT PRIMARY KEY,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum_sha256 TEXT NOT NULL,
    description   TEXT NOT NULL
);

-- Campaign / runtime evidence (durable identity; JSONL remains source until cutover)
CREATE TABLE IF NOT EXISTS nexus.campaigns (
    campaign_id     TEXT PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL,
    runtime_state   TEXT,
    real_money      BOOLEAN NOT NULL DEFAULT FALSE,
    manifest_sha256 TEXT,
    evidence_root   TEXT,
    metadata_json   JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS nexus.runtime_evidence_events (
    id              BIGSERIAL PRIMARY KEY,
    campaign_id     TEXT NOT NULL REFERENCES nexus.campaigns(campaign_id),
    stream_name     TEXT NOT NULL,
    event_time      TIMESTAMPTZ,
    event_time_ms   BIGINT,
    symbol          TEXT,
    decision_id     TEXT,
    candidate_id    TEXT,
    position_id     TEXT,
    lifecycle_id    TEXT,
    cycle_index     INTEGER,
    payload_json    JSONB NOT NULL,
    content_sha256  TEXT NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_runtime_evidence_content
    ON nexus.runtime_evidence_events (campaign_id, stream_name, content_sha256);

CREATE INDEX IF NOT EXISTS ix_runtime_evidence_campaign_stream
    ON nexus.runtime_evidence_events (campaign_id, stream_name, event_time_ms);

-- User / org / entitlement / RBAC (product foundation)
CREATE TABLE IF NOT EXISTS nexus.organizations (
    org_id      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexus.accounts (
    account_id  TEXT PRIMARY KEY,
    org_id      TEXT REFERENCES nexus.organizations(org_id),
    email       TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexus.entitlements (
    entitlement_id TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    product_code   TEXT NOT NULL,
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    granted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS nexus.rbac_roles (
    role_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS nexus.rbac_bindings (
    binding_id  TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    role_id     TEXT NOT NULL REFERENCES nexus.rbac_roles(role_id),
    org_id      TEXT REFERENCES nexus.organizations(org_id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexus.audit_log (
    audit_id    BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_id    TEXT,
    action      TEXT NOT NULL,
    resource    TEXT,
    detail_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- EATI durable schemas (persistence only — no auto-apply to live policy)
CREATE TABLE IF NOT EXISTS nexus.reflections (
    reflection_id   TEXT PRIMARY KEY,
    campaign_id     TEXT NOT NULL,
    decision_id     TEXT,
    lifecycle_id    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload_json    JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS nexus.counterfactuals (
    counterfactual_id TEXT PRIMARY KEY,
    campaign_id       TEXT NOT NULL,
    decision_id       TEXT,
    lifecycle_id      TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload_json      JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS nexus.lesson_candidates (
    lesson_candidate_id TEXT PRIMARY KEY,
    campaign_id         TEXT NOT NULL,
    decision_id         TEXT,
    lifecycle_id        TEXT,
    status              TEXT NOT NULL DEFAULT 'candidate_only',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload_json        JSONB NOT NULL,
    CONSTRAINT lesson_candidates_no_auto_live
        CHECK (status IN ('candidate_only', 'research_export', 'qualified_offline', 'rejected'))
);

CREATE TABLE IF NOT EXISTS nexus.decision_memory (
    memory_id     TEXT PRIMARY KEY,
    campaign_id   TEXT NOT NULL,
    decision_id   TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload_json  JSONB NOT NULL
);

-- Explicit gate: lessons never write leverage/risk/eligibility/execution policy here.
COMMENT ON TABLE nexus.lesson_candidates IS
    'Offline lesson candidates only. Must pass Replay→WF→OOS→Shadow before any policy mutation.';
