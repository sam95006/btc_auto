-- Bybit Demo execution ledger.  This migration never enables writes or mainnet.

CREATE TABLE IF NOT EXISTS nexus.bybit_demo_order_intents (
    order_intent_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    order_link_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('Buy', 'Sell')),
    position_idx INTEGER NOT NULL DEFAULT 0,
    order_type TEXT NOT NULL,
    requested_qty NUMERIC NOT NULL,
    requested_price NUMERIC,
    reduce_only BOOLEAN NOT NULL DEFAULT FALSE,
    state TEXT NOT NULL,
    bybit_order_id TEXT UNIQUE,
    exchange_status TEXT,
    filled_qty NUMERIC NOT NULL DEFAULT 0,
    remaining_qty NUMERIC,
    avg_fill_price NUMERIC,
    fees NUMERIC,
    reject_reason TEXT,
    last_reconciled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (state IN (
      'INTENT_CREATED','SUBMITTING','SUBMIT_UNKNOWN','ACCEPTED','NEW',
      'PARTIALLY_FILLED','FILLED','CANCEL_REQUESTED','CANCELLED','REJECTED',
      'CLOSE_PENDING','CLOSED','RECONCILIATION_REQUIRED'
    ))
);

CREATE TABLE IF NOT EXISTS nexus.bybit_demo_order_state_history (
    transition_id TEXT PRIMARY KEY,
    order_intent_id TEXT NOT NULL REFERENCES nexus.bybit_demo_order_intents(order_intent_id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    source TEXT NOT NULL,
    detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_bybit_demo_order_unfinished
    ON nexus.bybit_demo_order_intents (state, updated_at)
    WHERE state NOT IN ('CLOSED', 'CANCELLED', 'REJECTED');
