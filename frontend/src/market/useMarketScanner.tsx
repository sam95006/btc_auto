import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  fetchScannerCandidates,
  fetchScannerCharts,
  fetchScannerEvents,
  fetchScannerStatus,
  type MarketCandidate,
  type ScannerCharts,
  type ScannerEvent,
  type ScannerStatus,
} from "./scannerApi";

const POLL_MS = 12_000;

type OverviewCtx = {
  status: ScannerStatus | null;
  longs: MarketCandidate[];
  shorts: MarketCandidate[];
  events: ScannerEvent[];
  charts: ScannerCharts | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
};

const Ctx = createContext<OverviewCtx | null>(null);

/**
 * Shared scanner overview polling — one interval for top bar + overview + event center.
 * Does not replace ScannerPage board polling (different payload).
 */
export function MarketScannerProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<ScannerStatus | null>(null);
  const [longs, setLongs] = useState<MarketCandidate[]>([]);
  const [shorts, setShorts] = useState<MarketCandidate[]>([]);
  const [events, setEvents] = useState<ScannerEvent[]>([]);
  const [charts, setCharts] = useState<ScannerCharts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const [st, longBody, shortBody, ev, ch] = await Promise.all([
        fetchScannerStatus(),
        fetchScannerCandidates("LONG", 8),
        fetchScannerCandidates("SHORT", 8),
        fetchScannerEvents(24),
        fetchScannerCharts(),
      ]);
      if (!mounted.current) return;
      setStatus(st);
      setLongs((longBody.candidates || []).filter((c) => c.rank != null).slice(0, 5));
      setShorts((shortBody.candidates || []).filter((c) => c.rank != null).slice(0, 5));
      setEvents((ev.events || []).slice(0, 40));
      setCharts(ch);
      setError(null);
    } catch (e) {
      if (!mounted.current) return;
      setError(e instanceof Error ? e.message : "scanner_unavailable");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const id = window.setInterval(() => void refresh(), POLL_MS);
    return () => {
      mounted.current = false;
      window.clearInterval(id);
    };
  }, [refresh]);

  const value = useMemo(
    () => ({ status, longs, shorts, events, charts, error, loading, refresh }),
    [status, longs, shorts, events, charts, error, loading, refresh],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useMarketScannerOverview() {
  const ctx = useContext(Ctx);
  if (!ctx) {
    throw new Error("useMarketScannerOverview requires MarketScannerProvider");
  }
  return ctx;
}

export function useScannerBoard() {
  const [rows, setRows] = useState<MarketCandidate[]>([]);
  const [status, setStatus] = useState<ScannerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [st, body] = await Promise.all([
        fetchScannerStatus(),
        fetchScannerCandidates(undefined, 40),
      ]);
      setStatus(st);
      setRows(body.candidates || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "scanner_unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  return { rows, status, error, loading, refresh };
}
