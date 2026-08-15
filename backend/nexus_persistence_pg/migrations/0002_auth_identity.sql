-- NEXUS V18.3.3 Track B — auth identity, sessions, MFA, org membership, product audit
-- Forward-only migration. No destructive drops.

CREATE TABLE IF NOT EXISTS nexus.email_identities (
    identity_id   TEXT PRIMARY KEY,
    account_id    TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    email         TEXT NOT NULL UNIQUE,
    verified      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexus.password_credentials (
    account_id       TEXT PRIMARY KEY REFERENCES nexus.accounts(account_id),
    password_hash    TEXT NOT NULL,
    hash_algorithm   TEXT NOT NULL DEFAULT 'argon2',
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexus.auth_sessions (
    session_id       TEXT PRIMARY KEY,
    account_id       TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ NOT NULL,
    revoked_at       TIMESTAMPTZ,
    ip_address       INET,
    user_agent       TEXT,
    metadata_json    JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_auth_sessions_account
    ON nexus.auth_sessions (account_id, expires_at);

CREATE TABLE IF NOT EXISTS nexus.one_time_tokens (
    token_id         TEXT PRIMARY KEY,
    account_id       TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    purpose          TEXT NOT NULL,
    token_hash       TEXT NOT NULL,
    expires_at       TIMESTAMPTZ NOT NULL,
    consumed_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_one_time_tokens_hash
    ON nexus.one_time_tokens (token_hash, purpose);

CREATE TABLE IF NOT EXISTS nexus.mfa_factors (
    factor_id        TEXT PRIMARY KEY,
    account_id       TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    factor_type      TEXT NOT NULL,
    secret_encrypted TEXT,
    enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS nexus.organization_memberships (
    membership_id    TEXT PRIMARY KEY,
    org_id           TEXT NOT NULL REFERENCES nexus.organizations(org_id),
    account_id       TEXT NOT NULL REFERENCES nexus.accounts(account_id),
    seat_status      TEXT NOT NULL DEFAULT 'active',
    joined_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, account_id)
);

CREATE TABLE IF NOT EXISTS nexus.role_permissions (
    permission_id    TEXT PRIMARY KEY,
    role_id          TEXT NOT NULL REFERENCES nexus.rbac_roles(role_id),
    permission_code  TEXT NOT NULL,
    UNIQUE (role_id, permission_code)
);

CREATE TABLE IF NOT EXISTS nexus.product_audit_events (
    event_id         TEXT PRIMARY KEY,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_account_id TEXT,
    org_id           TEXT,
    action           TEXT NOT NULL,
    resource_type    TEXT,
    resource_id      TEXT,
    detail_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    prev_hash        TEXT,
    content_hash     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_product_audit_events_actor
    ON nexus.product_audit_events (actor_account_id, occurred_at DESC);

-- Seed baseline RBAC roles (idempotent)
INSERT INTO nexus.rbac_roles (role_id, name, description)
VALUES
    ('role_visitor', 'visitor', 'Unauthenticated visitor'),
    ('role_member', 'member', 'Standard org member'),
    ('role_admin', 'admin', 'Organization administrator')
ON CONFLICT (role_id) DO NOTHING;

INSERT INTO nexus.role_permissions (permission_id, role_id, permission_code)
VALUES
    ('perm_admin_manage_members', 'role_admin', 'org.manage_members'),
    ('perm_admin_view_audit', 'role_admin', 'org.view_audit'),
    ('perm_member_view_product', 'role_member', 'product.view')
ON CONFLICT (permission_id) DO NOTHING;
