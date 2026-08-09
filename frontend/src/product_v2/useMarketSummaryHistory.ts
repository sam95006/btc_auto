import { useCallback, useEffect, useState } from "react";
import {
  fetchMarketSummaryHistory,
  type MarketSummaryHistoryResponse,
  type MarketSummaryPoint,
} from "../market/marketSummaryHistory";

const POLL_MS = 60_000;

const EMPTY: MarketSummaryHistoryResponse = {
  ok: true,
  count: 0,
  points: [],
  fabricated_visual_count: 0,
};

export function useMarketSummaryHistory(hours = 24) {
  const [body, setBody] = useState<MarketSummaryHistoryResponse>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchMarketSummaryHistory({ hours, limit: 400 });
      setBody(next);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "history_unavailable");
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  return {
    points: body.points as MarketSummaryPoint[],
    count: body.count,
    fabricated_visual_count: body.fabricated_visual_count ?? 0,
    history_authority: body.history_authority,
    loading,
    error,
    refresh,
  };
}
