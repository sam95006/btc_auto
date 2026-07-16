import { createContext, createElement, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { detectAllAnomalies } from "./anomalyEngine";
import { sharedAnomalyStore } from "./anomalyStore";
import type { MarketAnomaly } from "./anomalyTypes";
import { getLiveMarketFeed } from "./LiveMarketFeed";
import { useLiveMarketFeed } from "./useLiveMarketFeed";

const AnomalyContext = createContext<MarketAnomaly[]>([]);

export function MarketAnomalyProvider({ children }: { children: ReactNode }) {
  const snap = useLiveMarketFeed();
  const [rows, setRows] = useState<MarketAnomaly[]>([]);
  const lastRun = useRef(0);

  useEffect(() => {
    const now = Date.now();
    if (now - lastRun.current < 1_500) return;
    lastRun.current = now;
    sharedAnomalyStore.process(detectAllAnomalies(snap.bySymbol, now), now);
    setRows(sharedAnomalyStore.listVisible(now));
  }, [snap]);

  useEffect(() => {
    const tick = setInterval(() => {
      const s = getLiveMarketFeed().snapshot();
      const now = Date.now();
      sharedAnomalyStore.process(detectAllAnomalies(s.bySymbol, now), now);
      setRows(sharedAnomalyStore.listVisible(now));
    }, 2_000);
    return () => clearInterval(tick);
  }, []);

  const value = useMemo(() => rows, [rows]);
  return createElement(AnomalyContext.Provider, { value }, children);
}

export function useMarketAnomalies(): MarketAnomaly[] {
  return useContext(AnomalyContext);
}

export function useTopMarketAnomalies(limit = 3): MarketAnomaly[] {
  const rows = useMarketAnomalies();
  return useMemo(
    () =>
      rows
        .filter((a) => a.status === "NEW" || a.status === "ACTIVE" || a.status === "COOLING")
        .slice(0, limit),
    [rows, limit],
  );
}
