import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchMarketSeriesBatch,
  type MarketSeries,
  type MarketSeriesPreset,
} from "../market/marketSeries";

/**
 * Load official market series for a symbol set. Never buffers browser WS ticks as trend.
 */
export function useMarketSeriesBatch(symbols: string[], preset: MarketSeriesPreset, refreshMs = 60_000) {
  const key = useMemo(
    () =>
      [...new Set(symbols.map((s) => s.toUpperCase()).filter(Boolean))]
        .sort()
        .join(","),
    [symbols.join("|")],
  );
  const [seriesBySymbol, setSeriesBySymbol] = useState<Record<string, MarketSeries>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    if (!key) {
      setSeriesBySymbol({});
      setLoading(false);
      return;
    }
    const list = key.split(",").filter(Boolean);
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const map = await fetchMarketSeriesBatch(list, preset);
        if (cancelled || !alive.current) return;
        setSeriesBySymbol(map);
        setError(null);
      } catch (e) {
        if (cancelled || !alive.current) return;
        setError(e instanceof Error ? e.message : "series_failed");
      } finally {
        if (!cancelled && alive.current) setLoading(false);
      }
    };
    void load();
    const id = window.setInterval(() => void load(), refreshMs);
    return () => {
      cancelled = true;
      alive.current = false;
      window.clearInterval(id);
    };
  }, [key, preset, refreshMs]);

  return { seriesBySymbol, loading, error };
}
