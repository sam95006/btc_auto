import { useEffect, useRef, useState } from "react";
import { getLiveMarketSnapshot, type LiveMarketTicker } from "../services/stagingApi";

const POLL_MS = 8_000;

export type LiveTickerView = {
  symbol: string;
  price: number;
  change24hPct: number;
  freshness: LiveMarketTicker["freshness"];
  dataDelayed: boolean;
  high24h: number | null;
  low24h: number | null;
  volume24h: number | null;
};

/**
 * Bounded polling for dashboard pulse.tickers only.
 * Opportunities / rankings / AI / Shadow remain mock or runtime-required.
 */
export function useLiveMarketTickers() {
  const [tickers, setTickers] = useState<LiveTickerView[]>([]);
  const [delayed, setDelayed] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const lastGood = useRef<LiveTickerView[]>([]);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const snapshot = await getLiveMarketSnapshot();
        if (!active) return;
        const next = snapshot.symbols
          .filter((row) => row.current_price != null && row.change_24h_percent != null)
          .map((row) => ({
            symbol: row.symbol,
            price: row.current_price as number,
            change24hPct: row.change_24h_percent as number,
            freshness: row.freshness,
            dataDelayed: row.data_delayed || snapshot.fallback !== "none",
            high24h: row.high_24h,
            low24h: row.low_24h,
            volume24h: row.volume_24h,
          }));
        if (next.length) {
          lastGood.current = next;
          setTickers(next);
          setDelayed(next.some((row) => row.dataDelayed));
          setUpdatedAt(snapshot.server_timestamp);
        }
      } catch {
        if (!active) return;
        if (lastGood.current.length) {
          setTickers(lastGood.current);
          setDelayed(true);
        }
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return { tickers, delayed, updatedAt };
}
