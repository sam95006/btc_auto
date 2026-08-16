-- Staging-only product registration and one-time Founder initialization.
-- Forward-only; contains no trading, exchange, or Runtime authority.

ALTER TABLE nexus.organization_memberships
    ADD COLUMN IF NOT EXISTS organization_role TEXT NOT NULL DEFAULT 'MEMBER';

CREATE TABLE IF NOT EXISTS nexus.founder_claim_state (
    claim_key TEXT PRIMARY KEY,
    founder_claimed BOOLEAN NOT NULL DEFAULT FALSE,
    founder_account_id TEXT REFERENCES nexus.accounts(account_id),
    claimed_at TIMESTAMPTZ,
    CHECK (
        (founder_claimed = FALSE AND founder_account_id IS NULL AND claimed_at IS NULL)
        OR (founder_claimed = TRUE AND founder_account_id IS NOT NULL AND claimed_at IS NOT NULL)
    )
);

INSERT INTO nexus.founder_claim_state (claim_key)
VALUES ('staging_founder')
ON CONFLICT (claim_key) DO NOTHING;

INSERT INTO nexus.organizations (org_id, name)
VALUES ('org_staging_founder', 'NEXUS Staging Founder Organization')
ON CONFLICT (org_id) DO NOTHING;

INSERT INTO nexus.rbac_roles (role_id, name, description)
VALUES ('role_founder', 'founder', 'Staging product founder; no trading authority')
ON CONFLICT (role_id) DO NOTHING;

INSERT INTO nexus.role_permissions (permission_id, role_id, permission_code)
VALUES
    ('perm_founder_product_view', 'role_founder', 'product.view'),
    ('perm_founder_org_owner', 'role_founder', 'org.owner'),
    ('perm_founder_operator_read', 'role_founder', 'founder.operator.read'),
    ('perm_founder_diagnostics_read', 'role_founder', 'founder.diagnostics.read'),
    ('perm_founder_live_ops_read', 'role_founder', 'founder.live_ops.read')
ON CONFLICT (permission_id) DO NOTHING;
