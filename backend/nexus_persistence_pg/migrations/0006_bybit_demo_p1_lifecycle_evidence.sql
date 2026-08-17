-- Forward-only P1 lifecycle evidence for the Bybit Demo durable order ledger.
-- Does not alter migration 0005. Does not enable writes, mainnet, or autonomy.

ALTER TABLE nexus.bybit_demo_order_intents
    ADD COLUMN IF NOT EXISTS parent_order_intent_id TEXT REFERENCES nexus.bybit_demo_order_intents(order_intent_id);

ALTER TABLE nexus.bybit_demo_order_intents
    ADD COLUMN IF NOT EXISTS actual_entry_price NUMERIC;

ALTER TABLE nexus.bybit_demo_order_intents
    ADD COLUMN IF NOT EXISTS actual_exit_price NUMERIC;

ALTER TABLE nexus.bybit_demo_order_intents
    ADD COLUMN IF NOT EXISTS realized_demo_pnl NUMERIC;

ALTER TABLE nexus.bybit_demo_order_intents
    ADD COLUMN IF NOT EXISTS wallet_delta NUMERIC;

ALTER TABLE nexus.bybit_demo_order_intents
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;

ALTER TABLE nexus.bybit_demo_order_intents
    ADD COLUMN IF NOT EXISTS pnl_provenance TEXT;

ALTER TABLE nexus.bybit_demo_order_intents
    ADD COLUMN IF NOT EXISTS accounting_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS ix_bybit_demo_order_parent
    ON nexus.bybit_demo_order_intents (parent_order_intent_id)
    WHERE parent_order_intent_id IS NOT NULL;
