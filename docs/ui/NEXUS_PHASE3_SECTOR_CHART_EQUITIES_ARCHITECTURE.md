# NEXUS Phase 3 — Sector / Chart / Equities Architecture

## Layers

| Layer | Count (approx.) | Role |
|-------|-----------------|------|
| Market Breadth | ~742 Bybit Linear USDT | 24h change, turnover, funding PIT, sector membership, sector breadth |
| Deep Intelligence | ~80 scanner symbols | 1m/5m/15m windows, candidates, anomalies, Price/OI quadrant |

## Sector pipeline

```
Bybit public tickers + Scanner deep snapshot + NEXUS taxonomy
  → SectorService (server, ~30s cache)
  → /api/market/sectors*
  → UI (/crypto/sectors*)
```

- Multi-membership curated taxonomy (`backend/market/sectors/taxonomy.py`)
- No runtime LLM classification
- Unclassified markets stay unclassified (not forced into Other)

## Chart pipeline

```
Bybit public kline / open-interest
  → /api/market/charts/*
  → nexusChartDatafeed
  → NexusOhlcvChart (SVG)
```

- TradingView is UX reference only — not a market data backend
- Funding historical series: honest `available: false` until a reliable public history path exists

## Equities foundation

- Provider interfaces in `frontend/src/market/equities/providers.ts`
- Pending providers return empty / unavailable — **no fake prices**
- Routes: `/equities/tokenized`, `/equities/analysis`

## Safety

- Sector state ≠ recommendation / trading trigger
- Chart data ≠ order routing
- Read-only · public crypto data · no private API / keys in UI path
