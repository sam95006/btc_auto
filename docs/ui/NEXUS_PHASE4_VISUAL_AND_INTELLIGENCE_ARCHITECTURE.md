# NEXUS Phase 4 — Visual Reduction & Market Intelligence Backend

## Tracks (isolated)

| Track | Scope | Not in scope |
|-------|--------|--------------|
| A Visual | Overview reduction, collecting UX, nav, footer, scroll | New product pages, equity providers |
| B Intelligence | Public WS deep-scan, history/timeline/outcomes, funding history, status API | Trading, private API, ARM, Stage 4.19, scoring changes |

## Deep-scan fast lane

```
REST tickers bootstrap
  → Bybit public WS (≤80 deep symbols)
  → delta merge (keep-last / OOO / dedupe)
  → throttled candidate recompute (~20s)
  → REST reconciliation / fallback
```

## Persistence honesty

- Prefer `NEXUS_DATA_DIR` when writable
- Otherwise memory-only with explicit `storage_mode`
- Never treat 24h snapshots as 5m history restore

## Safety

- Candidate formula unchanged
- Sector / chart / WS data ≠ trading triggers
- Backend HOLD / Stage 4.19 remain System Status only
