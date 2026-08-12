"""Constants for V13-A Microstructure 14-day Capture Operations."""
from __future__ import annotations

SCHEMA = "microstructure_operations_v13_a"
LANE = "V13-A"
CAMPAIGN_ID = "ms_accum_v13_integrity_14d"
PREVIOUS_CAMPAIGN_ID = "ms_accum_v7_bounded_24h"

GIB = 1024**3
# Storage floor: refuse new capture when free disk < 100 GiB.
STORAGE_FLOOR_BYTES = 100 * GIB
# Hard campaign storage cap: 40 GiB.
HARD_CAP_BYTES = 40 * GIB
# Soft warn threshold (80% of hard).
SOFT_CAP_BYTES = int(HARD_CAP_BYTES * 0.8)

TARGET_CALENDAR_DAYS = 14
MIN_SYMBOL_COUNT = 25
FAMILIES = ("AGGRESSIVE_TRADE_FLOW", "LIQUIDATION_EVENTS")
HOURLY_ROTATION = True
DAILY_INTEGRITY_SEAL = True

EVENT_STUDY_MUST_REMAIN = "NOT_READY"

# Frozen forensic counts from prior campaign (read-only; never mutate raw).
RETAINED_CLASSIFICATION_COUNTS = {
    "ACTUAL_DATA_CORRUPTION": 0,
    "EXPECTED_OPEN_TAIL": 113,
    "MIGRATION_ARTIFACT": 113,
    "MANIFEST_BUG": 43,
    "FINALIZER_FALSE_POSITIVE": 113,
    "LINKAGE_SEMANTICS_BUG": 113,
    "UNKNOWN_REQUIRES_MORE_EVIDENCE": 0,
}

# Deterministic ≥25-symbol design cohort (from V1.1 CAP25 capacity proof; design-only).
DESIGN_SYMBOLS_25: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "SOXLUSDT",
    "HYPEUSDT",
    "ADAUSDT",
    "XRPUSDT",
    "SNDKUSDT",
    "XAUUSDT",
    "BLESSUSDT",
    "SKHYNIXUSDT",
    "1000RATSUSDT",
    "DOGEUSDT",
    "ZECUSDT",
    "KORUUSDT",
    "SPCXUSDT",
    "ENAUSDT",
    "MUUSDT",
    "SNXXUSDT",
    "SKHYUSDT",
    "CLUSDT",
    "1000PEPEUSDT",
    "UNIUSDT",
    "BEATUSDT",
    "PUMPFUNUSDT",
)

assert len(DESIGN_SYMBOLS_25) >= MIN_SYMBOL_COUNT

# Synthetic logical epoch: 2025-08-04 00:00:00 UTC
SYNTHETIC_BASE_MS = 1_754_265_600_000
