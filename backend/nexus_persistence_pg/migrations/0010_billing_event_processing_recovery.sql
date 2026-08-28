-- NEXUS BILLING-4 — billing event processing crash-recovery metadata.
-- Forward-only, additive migration. No destructive drops, no ALTER ... DROP.
-- Adds attempt/recovery bookkeeping so a 'received'/'processing' event whose
-- worker crashed is NOT permanently treated as processed and can be retried.
-- Only 'processed' / 'rejected' are terminal states.

ALTER TABLE nexus.billing_events
    ADD COLUMN IF NOT EXISTS processing_started_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS processing_attempts    INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_attempt_at        TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error_at          TIMESTAMPTZ;
