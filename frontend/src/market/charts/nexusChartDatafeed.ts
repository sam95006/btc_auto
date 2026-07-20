/** NEXUS chart datafeed — Exchange public via NEXUS APIs (no TradingView market data). */

export type OhlcvBar = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  turnover?: number | null;
};

export type OiPoint = { time: number; openInterest: number; openInterestValue?: number | null };

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`chart_http_${res.status}`);
  return (await res.json()) as T;
}

export async function getBars(symbol: string, interval: string, limit = 120) {
  const qs = new URLSearchParams({ symbol, interval, limit: String(limit) });
  // Prefer Phase 6.4 nexus market-data route; fall back to legacy chart route.
  try {
    const primary = await getJson<{
      ok?: boolean;
      bars?: OhlcvBar[];
      candles?: OhlcvBar[];
      freshness?: string;
      source?: string;
      error?: string;
      barLimit?: number;
    }>(`/api/nexus/markets/${encodeURIComponent(symbol)}/candles?interval=${encodeURIComponent(interval)}&limit=${limit}`);
    const bars = primary.bars ?? primary.candles ?? [];
    if (primary.ok !== false && bars.length > 0) {
      return {
        ok: true,
        bars,
        freshness: primary.freshness,
        source: primary.source || "NEXUS_BYBIT_PUBLIC",
        barLimit: primary.barLimit,
      };
    }
  } catch {
    // fall through
  }
  return getJson<{
    ok: boolean;
    bars: OhlcvBar[];
    freshness?: string;
    source?: string;
    error?: string;
    barLimit?: number;
  }>(`/api/market/charts/ohlcv?${qs}`);
}

export async function getOpenInterest(symbol: string, interval = "5m", limit = 100) {
  const qs = new URLSearchParams({ symbol, interval, limit: String(limit) });
  return getJson<{
    ok: boolean;
    points: OiPoint[];
    freshness?: string;
    error?: string;
  }>(`/api/market/charts/open-interest?${qs}`);
}

export async function getFundingSeriesStatus() {
  return getJson<{
    ok: boolean;
    available: boolean;
    reason?: string;
    fabricatedHistory?: boolean;
  }>("/api/market/charts/funding");
}

/** Adapter surface for chart components — NEXUS-owned datafeed. */
export const nexusChartDatafeed = {
  getBars,
  getOpenInterest,
  getFundingSeriesStatus,
  provider: "NEXUS_BYBIT_PUBLIC" as const,
  tradingViewMarketData: false,
};
