import { useCallback, useEffect, useState } from "react";
import type { MarketCandidate } from "../market/scannerApi";
import { useMarketScannerOverview } from "../market/useMarketScanner";
import type {
  LiveRankEvent,
  LiveRankingRow,
  LiveRankingSnapshot,
  RankingTab,
} from "../market/liveMarketRanking";
import {
  fetchPublicRadar,
  fetchPublicRadarEvents,
  type PublicRadarSnapshot,
} from "../market/publicRadarApi";

const POLL_MS = 12_000;

const EMPTY_SNAPSHOT: LiveRankingSnapshot = {
  updated_at: 0,
  universe_size: 0,
  scanner_visible_count: 0,
  radar_eligible_count: 0,
  trade_eligible_count: 0,
  active_count: 0,
  qualified_count: 0,
  rows: [],
  radar: [],
  closest_watch: [],
  qualified: [],
  events: [],
  fixed_symbol_dependency_count: 0,
  radar_eligibility_contract: "RADAR_ELIGIBILITY_CONTRACT_V1",
  rank_score_semantics: "normalized_0_100_nex_rank_score_v1",
  rank_persistence: "server_jsonl_prev_v1_hysteresis",
};

function toSnapshot(body: PublicRadarSnapshot): LiveRankingSnapshot & {
  rank_authority: "SERVER";
  ranking_history_authority: "SERVER";
  frontend_local_rank_authority: false;
  frontend_candidate_fetch_limit_affects_rank: false;
  evaluated_count: number;
  monitored_count: number;
  excluded_count: number;
  full_ranking_before_pagination: boolean;
  server_rank_events: boolean;
  rank_restart_persistence: boolean;
  two_clients_same_snapshot: boolean;
  snapshot_id?: string;
  universe_blocker?: string | null;
} {
  return {
    updated_at: body.updated_at || Date.now(),
    universe_size: body.universe_size ?? 0,
    scanner_visible_count: body.scanner_visible_count ?? 0,
    radar_eligible_count: body.radar_eligible_count ?? 0,
    trade_eligible_count: body.trade_eligible_count ?? 0,
    active_count: body.active_count ?? body.radar_eligible_count ?? 0,
    qualified_count: body.qualified_count ?? 0,
    rows: (body.rows || []) as LiveRankingRow[],
    radar: (body.radar || body.rows || []) as LiveRankingRow[],
    closest_watch: (body.closest_watch || []) as LiveRankingRow[],
    qualified: (body.qualified || []) as LiveRankingRow[],
    events: (body.events || []) as LiveRankEvent[],
    fixed_symbol_dependency_count: 0,
    radar_eligibility_contract: "RADAR_ELIGIBILITY_CONTRACT_V1",
    rank_score_semantics: "normalized_0_100_nex_rank_score_v1",
    rank_persistence: "server_jsonl_prev_v1_hysteresis",
    rank_authority: "SERVER",
    ranking_history_authority: "SERVER",
    frontend_local_rank_authority: false,
    frontend_candidate_fetch_limit_affects_rank: false,
    evaluated_count: body.evaluated_count ?? body.scanner_visible_count ?? 0,
    monitored_count: body.monitored_count ?? body.evaluated_count ?? 0,
    excluded_count: body.excluded_count ?? 0,
    full_ranking_before_pagination: body.full_ranking_before_pagination !== false,
    server_rank_events: body.server_rank_events !== false,
    rank_restart_persistence: Boolean(body.rank_restart_persistence),
    two_clients_same_snapshot: body.two_clients_same_snapshot !== false,
    snapshot_id: body.snapshot_id,
    universe_blocker: body.universe_blocker,
  };
}

/**
 * Server-authoritative Live Radar snapshot consumer (V18.2.16).
 * Does NOT fetch scanner candidates or build ranks in the browser.
 * Pages may re-filter tab locally; ranking order is already server-authoritative.
 */
export function useLiveMarketRanking(_tab?: RankingTab, limit = 120) {
  const { status } = useMarketScannerOverview();
  const [snapshot, setSnapshot] = useState(() => ({
    ...EMPTY_SNAPSHOT,
    rank_authority: "SERVER" as const,
    ranking_history_authority: "SERVER" as const,
    frontend_local_rank_authority: false as const,
    frontend_candidate_fetch_limit_affects_rank: false as const,
    evaluated_count: 0,
    monitored_count: 0,
    excluded_count: 0,
    full_ranking_before_pagination: true,
    server_rank_events: true,
    rank_restart_persistence: true,
    two_clients_same_snapshot: true,
  }));
  const [events, setEvents] = useState<LiveRankEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [radar, evBody] = await Promise.all([
        fetchPublicRadar({ limit, tab: "ALL" }),
        fetchPublicRadarEvents(80),
      ]);
      if (!radar.ok && radar.error) {
        setError(radar.error);
      } else {
        setError(null);
      }
      setSnapshot(toSnapshot(radar));
      setEvents((evBody.events || []) as LiveRankEvent[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ranking_unavailable");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  return {
    ...snapshot,
    events: events.length ? events : snapshot.events,
    candidates: [] as MarketCandidate[],
    status,
    loading,
    error,
    refresh,
    rank_authority: "SERVER" as const,
    ranking_history_authority: "SERVER" as const,
    frontend_local_rank_authority: false as const,
  };
}
