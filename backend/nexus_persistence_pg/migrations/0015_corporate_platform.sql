-- 0015_corporate_platform.sql
-- CORPORATE-1: public company website + backend-driven CMS + owner/admin RBAC.
-- Additive and non-destructive. Isolated from Founder private trading: no
-- trading/execution/credential tables are referenced or modified here.

-- Roles + granular permissions (permissions stored as a JSON array of scopes).
CREATE TABLE IF NOT EXISTS nexus.corporate_roles (
    role TEXT PRIMARY KEY,
    permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Corporate admin/owner accounts (separate from member auth; stronger hashing).
CREATE TABLE IF NOT EXISTS nexus.corporate_admins (
    admin_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_algo TEXT NOT NULL DEFAULT 'pbkdf2_sha256',
    role TEXT NOT NULL REFERENCES nexus.corporate_roles(role),
    mfa_secret TEXT,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    disabled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexus.corporate_sessions (
    session_id TEXT PRIMARY KEY,
    admin_id TEXT NOT NULL REFERENCES nexus.corporate_admins(admin_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    ip TEXT,
    csrf_token TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_corporate_sessions_admin
    ON nexus.corporate_sessions (admin_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS nexus.corporate_audit (
    audit_id TEXT PRIMARY KEY,
    admin_id TEXT,
    action TEXT NOT NULL,
    target TEXT,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_corporate_audit_created ON nexus.corporate_audit (created_at DESC);

-- CMS content: one row per slug with draft + published bodies and version.
CREATE TABLE IF NOT EXISTS nexus.corporate_content (
    slug TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'section',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    draft_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_json JSONB,
    published_version INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS nexus.corporate_content_versions (
    version_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL REFERENCES nexus.corporate_content(slug) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    json JSONB NOT NULL,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_corporate_content_versions_slug
    ON nexus.corporate_content_versions (slug, version DESC);

-- Key/value settings (bootstrap state, site config, SEO, showcase config).
CREATE TABLE IF NOT EXISTS nexus.corporate_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexus.corporate_leads (
    lead_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL,
    company TEXT,
    message TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'contact',
    status TEXT NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_corporate_leads_created ON nexus.corporate_leads (created_at DESC);

-- Seed the OWNER role with the full corporate business permission set. Note:
-- these are BUSINESS/website scopes only — they intentionally exclude any
-- Founder private-trading / execution / credential access.
INSERT INTO nexus.corporate_roles (role, permissions) VALUES (
    'OWNER',
    '["website.read","website.write","content.read","content.write","content.publish",
      "products.read","products.write","pricing.read","pricing.write","showcase.read",
      "showcase.write","users.read","users.write","members.read","members.write",
      "enterprise.read","enterprise.write","leads.read","leads.write","contacts.read",
      "analytics.read","audit.read","admins.read","admins.write","settings.read",
      "settings.write","security.read","status.read","seo.read","seo.write"]'::jsonb
) ON CONFLICT (role) DO NOTHING;

INSERT INTO nexus.corporate_roles (role, permissions) VALUES (
    'EDITOR',
    '["website.read","content.read","content.write","showcase.read","leads.read",
      "contacts.read","analytics.read","status.read","seo.read"]'::jsonb
) ON CONFLICT (role) DO NOTHING;
