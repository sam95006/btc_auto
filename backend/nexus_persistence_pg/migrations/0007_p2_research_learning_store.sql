-- Forward-only P2 research learning store.
-- Candidate lessons only. Does not enable live policy, mainnet, or exchange writes.

CREATE TABLE IF NOT EXISTS nexus.p2_research_lessons (
    lesson_id TEXT PRIMARY KEY,
    source_trade_id TEXT NOT NULL,
    source_decision_id TEXT NOT NULL,
    source_evidence_hash TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    mistake_labels JSONB NOT NULL DEFAULT '[]'::jsonb,
    primary_mistake TEXT NOT NULL,
    lesson_rule TEXT NOT NULL,
    support_count INTEGER NOT NULL DEFAULT 1,
    confidence NUMERIC,
    status TEXT NOT NULL DEFAULT 'candidate_only',
    policy_truth BOOLEAN NOT NULL DEFAULT FALSE,
    revalidation_required BOOLEAN NOT NULL DEFAULT TRUE,
    ttl_trades INTEGER,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT p2_research_lessons_source_hash_uk UNIQUE (source_evidence_hash),
    CONSTRAINT p2_research_lessons_status_chk
        CHECK (status IN ('candidate_only', 'research_export', 'qualified_offline', 'rejected')),
    CONSTRAINT p2_research_lessons_policy_truth_chk
        CHECK (policy_truth = FALSE OR support_count >= 3)
);

CREATE INDEX IF NOT EXISTS ix_p2_research_lessons_campaign
    ON nexus.p2_research_lessons (campaign_id, primary_mistake);

COMMENT ON TABLE nexus.p2_research_lessons IS
    'Research-only P2 lesson candidates. One durable Run8 lifecycle yields at most one candidate. Not live execution policy.';
