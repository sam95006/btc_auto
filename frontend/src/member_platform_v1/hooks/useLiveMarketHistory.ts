import { useEffect, useRef, useState } from "react";
import { getLiveMarketHistory, type LiveMarketCandle } from "../services/stagingApi";

const POLL_MS = 15_000;

export type ChartCandle = { o: number; h: number; l: number; c: number; v?: number };

/** Bounded read-only history with last-safe-chart fallback. */
export function useLiveMarketHistory(symbol: string, interval: string) {
  const [candles, setCandles] = useState<ChartCandle[]>([]);
  const [state, setState] = useState<"LOADING" | "LIVE" | "STALE" | "UNAVAILABLE">("LOADING");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const lastGood = useRef<ChartCandle[]>([]);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await getLiveMarketHistory(
          symbol,
          interval.toLowerCase(),
          60
        );
        if (!active) return;
        const next = response.candles.map((row: LiveMarketCandle) => ({
          o: row.open,
          h: row.high,
          l: row.low,
          c: row.close,
          v: row.volume,
        }));
        if (next.length) {
          lastGood.current = next;
          setCandles(next);
          setState(response.data_delayed || response.fallback !== "none" ? "STALE" : "LIVE");
          setUpdatedAt(response.server_timestamp);
          return;
        }
        setState(lastGood.current.length ? "STALE" : "UNAVAILABLE");
      } catch {
        if (!active) return;
        if (lastGood.current.length) {
          setCandles(lastGood.current);
          setState("STALE");
        } else {
          setState("UNAVAILABLE");
        }
      }
    };
    setState("LOADING");
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [symbol, interval]);

  return { candles, state, updatedAt };
}
