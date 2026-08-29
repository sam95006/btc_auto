-- NEXUS PLATFORM-1 — window-aware usage idempotency.
-- Forward-only, additive schema change. No data loss (only an index is
-- reshaped; DROP INDEX is not data-destructive).
--
-- Fixes a correctness gap: with UNIQUE(account_id, quota_code, idempotency_key)
-- a client key reused in a LATER window was mistaken for a duplicate and the new
-- window was not incremented (free usage). The identity is now window-aware.

ALTER TABLE nexus.usage_events
    ADD COLUMN IF NOT EXISTS window_start TIMESTAMPTZ;

DROP INDEX IF EXISTS nexus.ux_usage_events_idem;

CREATE UNIQUE INDEX IF NOT EXISTS ux_usage_events_idem_window
    ON nexus.usage_events (account_id, quota_code, window_start, idempotency_key);
