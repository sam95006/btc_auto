import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchScannerCandidates,
  type MarketCandidate,
} from "../market/scannerApi";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import {
  buildLiveRanking,
  rankingEventsFromScanner,
  type LiveRankEvent,
  type LiveRankingSnapshot,
} from "../market/liveMarketRanking";

const POLL_MS = 12_000;

/**
 * Full-market live ranking from scanner candidates (not a fixed symbol list).
 */
export function useLiveMarketRanking() {
  const { events: scannerEvents, status } = useMarketScannerOverview();
  const [candidates, setCandidates] = useState<MarketCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const body = await fetchScannerCandidates(undefined, 40);
      setCandidates(body.candidates || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ranking_unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const snapshot: LiveRankingSnapshot = useMemo(
    () => buildLiveRanking(candidates, { persist: true }),
    [candidates],
  );

  const mergedEvents: LiveRankEvent[] = useMemo(() => {
    const fromScanner = rankingEventsFromScanner(scannerEvents);
    const ids = new Set(snapshot.events.map((e) => e.id));
    const extra = fromScanner.filter((e) => !ids.has(e.id));
    return [...snapshot.events, ...extra].sort((a, b) => b.timestamp - a.timestamp);
  }, [snapshot.events, scannerEvents]);

  return {
    ...snapshot,
    events: mergedEvents,
    candidates,
    status,
    loading,
    error,
    refresh,
  };
}
