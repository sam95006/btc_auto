/** Public-safe true market series contract (V18.2.18). Official OHLCV only. */

export const MARKET_SERIES_CONTRACT = "MARKET_SERIES_CONTRACT_V1" as const;

export type MarketSeriesPoint = {
  timestamp: number;
  o: number;
  h: number;
  l: number;
  c: number;
  volume?: number;
};

export type MarketSeries = {
  ok: boolean;
  contract?: string;
  symbol: string;
  interval: string;
  window_label?: string | null;
  window_start?: number | null;
  window_end?: number | null;
  source?: string;
  freshness?: string;
  point_count?: number;
  insufficient?: boolean;
  fabricated?: boolean;
  invented_candles?: boolean;
  equal_space_ticks?: boolean;
  interval_ms?: number;
  points: MarketSeriesPoint[];
  error?: string | null;
};

export type MarketSeriesPreset = "pulse_24h" | "radar_4h" | "watchlist_24h" | "terminal";

export const SERIES_PRESETS: Record<
  MarketSeriesPreset,
  { interval: string; limit: number; window: string; expectedIntervalMs: number }
> = {
  pulse_24h: { interval: "15m", limit: 96, window: "24h", expectedIntervalMs: 15 * 60_000 },
  radar_4h: { interval: "5m", limit: 48, window: "4h", expectedIntervalMs: 5 * 60_000 },
  watchlist_24h: { interval: "15m", limit: 96, window: "24h", expectedIntervalMs: 15 * 60_000 },
  terminal: { interval: "15m", limit: 200, window: "full", expectedIntervalMs: 15 * 60_000 },
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`series_http_${res.status}`);
  return (await res.json()) as T;
}

function normalizeSeries(raw: Partial<MarketSeries> & { symbol?: string }): MarketSeries {
  const points = Array.isArray(raw.points)
    ? raw.points.filter(
        (p): p is MarketSeriesPoint =>
          p != null &&
          Number.isFinite(p.timestamp) &&
          Number.isFinite(p.c) &&
          Number.isFinite(p.o) &&
          Number.isFinite(p.h) &&
          Number.isFinite(p.l),
      )
    : [];
  const insufficient = points.length < 2;
  return {
    ok: Boolean(raw.ok) && !insufficient,
    contract: raw.contract || MARKET_SERIES_CONTRACT,
    symbol: String(raw.symbol || "").toUpperCase(),
    interval: String(raw.interval || ""),
    window_label: raw.window_label,
    window_start: raw.window_start ?? (points[0]?.timestamp ?? null),
    window_end: raw.window_end ?? (points[points.length - 1]?.timestamp ?? null),
    source: raw.source,
    freshness: raw.freshness || (insufficient ? "NO_DATA" : "LIVE"),
    point_count: points.length,
    insufficient,
    fabricated: false,
    invented_candles: false,
    equal_space_ticks: false,
    interval_ms: raw.interval_ms,
    points,
    error: insufficient ? raw.error || "NO_DATA" : raw.error,
  };
}

export async function fetchMarketSeries(
  symbol: string,
  preset: MarketSeriesPreset = "pulse_24h",
): Promise<MarketSeries> {
  const cfg = SERIES_PRESETS[preset];
  const qs = new URLSearchParams({
    interval: cfg.interval,
    limit: String(cfg.limit),
    window: cfg.window,
  });
  try {
    const body = await getJson<Partial<MarketSeries>>(
      `/api/nexus/markets/${encodeURIComponent(symbol)}/series?${qs}`,
    );
    return normalizeSeries({ ...body, symbol });
  } catch (e) {
    return normalizeSeries({
      ok: false,
      symbol,
      interval: cfg.interval,
      points: [],
      insufficient: true,
      error: e instanceof Error ? e.message : "fetch_failed",
    });
  }
}

export async function fetchMarketSeriesBatch(
  symbols: string[],
  preset: MarketSeriesPreset = "radar_4h",
): Promise<Record<string, MarketSeries>> {
  const uniq = [...new Set(symbols.map((s) => s.toUpperCase()).filter(Boolean))].slice(0, 24);
  if (!uniq.length) return {};
  const cfg = SERIES_PRESETS[preset];
  const qs = new URLSearchParams({
    symbols: uniq.join(","),
    interval: cfg.interval,
    limit: String(cfg.limit),
    window: cfg.window,
    max: String(uniq.length),
  });
  try {
    const body = await getJson<{ series?: Record<string, Partial<MarketSeries>> }>(
      `/api/nexus/markets/series?${qs}`,
    );
    const out: Record<string, MarketSeries> = {};
    for (const sym of uniq) {
      out[sym] = normalizeSeries({ ...(body.series?.[sym] || {}), symbol: sym });
    }
    return out;
  } catch {
    // Fall back to per-symbol (still official history; never invent)
    const entries = await Promise.all(uniq.map(async (sym) => [sym, await fetchMarketSeries(sym, preset)] as const));
    return Object.fromEntries(entries);
  }
}

/** Closes for spark rendering; gaps handled by MetricSpark via timestamps. */
export function seriesCloseValues(series: MarketSeries | null | undefined): number[] {
  if (!series?.ok || !series.points?.length) return [];
  return series.points.map((p) => p.c);
}

export function seriesSparkPoints(
  series: MarketSeries | null | undefined,
): Array<{ timestamp: number; value: number }> {
  if (!series?.ok || !series.points?.length) return [];
  return series.points.map((p) => ({ timestamp: p.timestamp, value: p.c }));
}
