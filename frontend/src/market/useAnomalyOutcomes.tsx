import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { sharedOutcomeStore } from "./anomalyOutcomeStore";
import type { AnomalyOutcome } from "./anomalyOutcomeTypes";
import { getLiveMarketFeed } from "./LiveMarketFeed";
import { useLiveMarketFeed } from "./useLiveMarketFeed";
import { useMarketAnomalies } from "./useMarketAnomalies";

const OutcomeContext = createContext<AnomalyOutcome[]>([]);

/** Tracks anomaly → forward outcomes from LiveMarketFeed (research only). */
export function AnomalyOutcomeProvider({ children }: { children: ReactNode }) {
  const anomalies = useMarketAnomalies();
  const snap = useLiveMarketFeed();
  const [rows, setRows] = useState<AnomalyOutcome[]>([]);

  useEffect(() => {
    const now = Date.now();
    for (const a of anomalies) {
      const live = snap.bySymbol[a.symbol]?.lastPrice;
      sharedOutcomeStore.ensureTracking(a, live, now);
    }
    sharedOutcomeStore.onPriceTick(snap.bySymbol, snap.feedStatus, now);
    setRows(sharedOutcomeStore.list());
  }, [anomalies, snap]);

  useEffect(() => {
    const tick = setInterval(() => {
      const s = getLiveMarketFeed().snapshot();
      const now = Date.now();
      sharedOutcomeStore.onPriceTick(s.bySymbol, s.feedStatus, now);
      setRows(sharedOutcomeStore.list());
    }, 2_000);
    return () => clearInterval(tick);
  }, []);

  const value = useMemo(() => rows, [rows]);
  return createElement(OutcomeContext.Provider, { value }, children);
}

export function useAnomalyOutcomes(): AnomalyOutcome[] {
  return useContext(OutcomeContext);
}

export function useAnomalyOutcome(anomalyId: string): AnomalyOutcome | undefined {
  const rows = useAnomalyOutcomes();
  return useMemo(() => rows.find((r) => r.anomalyId === anomalyId), [rows, anomalyId]);
}
