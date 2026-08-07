"""Central Market Universe eligibility for NEXUS read-only scanner (Phase 1).

Bybit Mainnet Public Linear only · no private API · no trading coupling.
"""
from __future__ import annotations

# Hard cap for Phase 1 scanner pool
SYMBOL_LIMIT = 80

# Eligibility thresholds (USDT linear)
MIN_TURNOVER_24H_USDT = 5_000_000.0
MIN_OI_VALUE_USDT = 1_000_000.0
MAX_SPREAD_BPS = 25.0
MIN_LISTING_AGE_MS = 7 * 24 * 60 * 60 * 1000  # 7 days when launchTime available

SNAPSHOT_INTERVAL_SEC = 20.0
HISTORY_CAPACITY_PER_SYMBOL = 72  # ~24 min at 20s — reliable 15m window with interval drift
CANDIDATE_CAPACITY = 40
EVENT_CAPACITY = 80

# Score knobs (0–100)
FUNDING_CROWD_ABS = 0.0005  # 0.05%
OVEREXTEND_5M_PCT = 2.5
MIN_CONFIRM_PERSIST_SEC = 40.0
RANK_STABILITY_BAND = 3.0

BLACKLIST_SYMBOLS = frozenset(
    {
        # reserved for unsupported / known-bad instruments
    }
)

# Bybit linear symbolType — empty/"innovation" are crypto; stock/commodity are cross-asset.
# Equity/ETF perps (e.g. SOXLUSDT, SPCXUSDT) must not enter crypto Opportunities ranking.
NON_CRYPTO_SYMBOL_TYPES = frozenset({"stock", "commodity"})
CRYPTO_OPPORTUNITY_SYMBOL_TYPES = frozenset({"", "innovation"})
CROSS_ASSET_DISPOSITION = "CROSS_ASSET_CONTEXT_ONLY"
CRYPTO_OPPORTUNITY_DISPOSITION = "CRYPTO_OPPORTUNITY_ELIGIBLE"
