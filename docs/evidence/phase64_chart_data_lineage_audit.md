# CURRENT_CHART_DATA_LINEAGE_AUDIT (Phase 6.4 Gate C)

Verified from code + Live API probes on 2026-07-20. Live OHLCV probe: ok=true source=BYBIT_MAINNET_LINEAR freshness=LIVE.

## 1. Homepage BTC/ETH/SOL ticker
- chart_name: Market top ticker / Simplified dashboard live prices
- frontend_component: MarketTopTicker.tsx, SimplifiedMarketDashboard.tsx
- frontend_route: /overview (via App layout)
- frontend_hook: useMarketScannerOverview (status), useLivePrice("ETH"/symbol)
- internal_api: /api/market/scanner/status (+ live feed hook)
- backend_handler: market_scanner_routes → scanner_service
- provider: Bybit Public Mainnet Linear WS/REST
- data_type: ticker / mark lastPrice snapshot
- timeframe: tick / cycle (~20s)
- historical_source: none (live window only)
- live_update_source: Bybit public WS via scanner
- is_real_data: true
- is_ohlcv: false
- is_ticker_derived: true
- known_gap: NOT_TRUE_OHLCV_CHART for price display chips

## 2. Long/Short boards
- chart_name: Long/Short candidate boards
- frontend_component: DecisionMarketOverview.tsx
- frontend_route: /overview
- frontend_hook: useMarketScannerOverview
- internal_api: /api/market/scanner/overview (or status+candidates)
- backend_handler: scanner_service candidates ranking
- provider: Bybit Public via scanner
- data_type: ranked candidates (score/side/stage)
- is_real_data: true
- is_ohlcv: false
- known_gap: boards are candidate lists, not charts

## 3. Readiness Gauge
- chart_name: NEXUS Market Readiness
- frontend_component: MarketReadinessGauge.tsx
- frontend_route: /overview (SimplifiedMarketDashboard)
- frontend_hook: none (static import)
- internal_api: none
- backend_handler: none
- provider: DEMO constant MARKET_READINESS in demo/marketDashboard.ts
- is_real_data: false
- is_snapshot_only: true
- known_gap: DEMO/static — not live market data

## 4. Candidate mini charts / sparklines
- chart_name: Candidate sparkline / Price-OI trend
- frontend_component: MarketSymbolPage Sparkline, PriceOiTrend; DecisionMarketOverview links
- frontend_hook: fetchScannerSymbol → sparkline array
- internal_api: /api/market/scanner/symbol/{symbol}
- backend_handler: scanner symbol snapshot + short window history
- data_type: price/oi point series from scanner window
- is_real_data: true
- is_ohlcv: false
- is_ticker_derived: true
- known_gap: NOT_TRUE_OHLCV_CHART

## 5. Symbol detail chart (pre-6.4 SVG)
- chart_name: NexusOhlcvChart (SVG candles)
- frontend_component: NexusOhlcvChart.tsx
- frontend_route: /market/:symbol (replaced primary by NexusLiveCandleChart in 6.4)
- frontend_hook: getBars via nexusChartDatafeed
- internal_api: /api/market/charts/ohlcv (legacy) + /api/nexus/markets/{symbol}/candles (6.4 preferred)
- backend_handler: market_chart_routes / nexus_market_data_routes → bybit_public_charts.fetch_ohlcv
- provider: Bybit Public Mainnet Linear
- data_type: OHLCV bars
- timeframes: 1m,5m,15m,1h,4h,1d
- historical_source: Bybit public kline REST
- live_update_source: REST poll (~30s SVG / ~live poll in lightweight chart)
- is_real_data: true
- is_ohlcv: true
- known_gap: no dedicated public WS kline merge on SVG path; funding history incomplete

## 6. Symbol detail chart (Phase 6.4 lightweight-charts)
- chart_name: NexusLiveCandleChart
- frontend_component: NexusLiveCandleChart.tsx
- frontend_route: /market/:symbol
- frontend_hook: fetchCandles → /api/nexus/markets/{symbol}/candles fallback /api/market/charts/ohlcv
- provider: Bybit Public
- is_real_data: true
- is_ohlcv: true
- features: volume histogram, crosshair, zoom/pan via library, loading/stale/empty/error states

## 7. Funding chart
- chart_name: Crypto Funding page / chart funding status
- frontend_component: CryptoFundingPage + getFundingSeriesStatus
- frontend_route: /crypto/funding
- internal_api: /api/market/charts/funding
- backend_handler: market_chart_routes funding
- Live probe: available=true, fabricatedHistory=false
- known_gap: series depth limited; not a full multi-day fabricated history

## 8. Sector chart
- chart_name: Sector breadth / sector pages
- frontend_component: CryptoSectorsPage, DecisionMarketOverview sector rows
- frontend_hook: fetchSectors / fetchSectorsStatus
- internal_api: /api/market/sectors*
- backend_handler: market_sector_routes
- provider: derived from scanner universe
- is_ohlcv: false
- known_gap: sector heat is aggregate, not OHLCV

## 9. Performance chart
- chart_name: Performance summary streams
- frontend_hook: /api/nexus/performance/summary (operator/research)
- backend_handler: nexus research performance
- known_gap: research/paper streams — not market OHLCV; NATURAL vs VALIDATION separation required

## 10. PAPER equity chart
- chart_name: Paper ledger equity
- frontend_route: paper lab / paper status APIs
- internal_api: /api/nexus/paper/status, /api/nexus/paper/ledger
- backend_handler: paper_routes + durable_ledger NEXUS_PAPER_MAIN_V1
- is_real_data: true (simulated ledger)
- is_ohlcv: false
- known_gap: equity history chart UI may be sparse; ledger events currently deposit-only until natural fills

## Summary counts
- existing_true_ohlcv_charts: NexusOhlcvChart, NexusLiveCandleChart (/api/market/charts/ohlcv + /api/nexus/markets/.../candles → Bybit public)
- existing_ticker_derived_charts: sparklines, top ticker chips, readiness DEMO
- known_chart_gaps: Readiness DEMO; sparkline NOT_TRUE_OHLCV; on-chain/social/macro UNAVAILABLE; dedicated OF heatmap EXPERIMENTAL
