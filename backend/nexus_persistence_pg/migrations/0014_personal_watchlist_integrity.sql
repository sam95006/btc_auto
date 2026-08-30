-- 0014_personal_watchlist_integrity.sql
-- PERSONAL-2: durable single-active-watchlist integrity for Personal accounts.
--
-- Additive and non-destructive: it never drops or deletes rows. Pre-existing
-- duplicate active watchlists are ARCHIVED (archived_at set) rather than
-- removed, preserving all data, so the partial unique index can be created
-- safely. Watchlist capacity itself is enforced atomically in the repository
-- (SELECT ... FOR UPDATE), not by this schema.

-- 1) Archive any extra active watchlists per account, keeping the earliest
--    created active one. Rows are preserved (archived), not deleted.
UPDATE nexus.watchlists w
SET archived_at = NOW(), updated_at = NOW()
WHERE w.archived_at IS NULL
  AND w.watchlist_id NOT IN (
    SELECT DISTINCT ON (account_id) watchlist_id
    FROM nexus.watchlists
    WHERE archived_at IS NULL
    ORDER BY account_id, created_at ASC
  );

-- 2) Enforce at most one active (non-archived) watchlist per account durably.
CREATE UNIQUE INDEX IF NOT EXISTS ux_watchlists_one_active_per_account
  ON nexus.watchlists (account_id)
  WHERE archived_at IS NULL;
