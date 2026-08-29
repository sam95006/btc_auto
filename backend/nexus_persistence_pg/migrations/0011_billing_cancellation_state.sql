-- NEXUS BILLING-5 — subscription cancellation-requested state.
-- Forward-only, additive migration. No destructive drops.
-- Records that a member requested cancellation (default: at period end). The
-- authoritative canceled/expired lifecycle still arrives via a verified
-- provider webhook; this flag only drives the "cancellation pending" UI.

ALTER TABLE nexus.subscriptions
    ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE;
