/** Server-side Full-Market Live Radar client (V18.2.16). */

import type { LiveRankEvent, LiveRankingRow, RankingTab } from "./liveMarketRanking";

export type PublicRadarSnapshot = {
  ok?: boolean;
  error?: string;
  updated_at: number;
  snapshot_id?: string;
  snapshot_version?: string;
  rank_authority: "SERVER";
  ranking_history_authority: "SERVER";
  frontend_local_rank_authority: boolean;
  frontend_candidate_fetch_limit_affects_rank: boolean;
  full_ranking_before_pagination: boolean;
  full_ranked_count?: number;
  server_rank_events: boolean;
  rank_restart_persistence: boolean;
  two_clients_same_snapshot: boolean;
  fixed_symbol_dependency_count: number;
  radar_eligibility_contract: string;
  rank_score_semantics: string;
  rank_persistence: string;
  universe_size: number;
  evaluated_count: number;
  monitored_count: number;
  excluded_count: number;
  scanner_visible_count: number;
  radar_eligible_count: number;
  trade_eligible_count: number;
  active_count: number;
  qualified_count: number;
  rows: LiveRankingRow[];
  radar: LiveRankingRow[];
  closest_watch: LiveRankingRow[];
  qualified: LiveRankingRow[];
  events: LiveRankEvent[];
  total_ranked?: number;
  returned?: number;
  tab?: string;
  limit?: number;
  universe_blocker?: string | null;
  member_execution?: number;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`radar_http_${res.status}`);
  return (await res.json()) as T;
}

export function fetchPublicRadar(opts?: { limit?: number; tab?: RankingTab; force?: boolean }) {
  const qs = new URLSearchParams();
  qs.set("limit", String(opts?.limit ?? 40));
  qs.set("tab", String(opts?.tab ?? "ALL"));
  if (opts?.force) qs.set("force", "1");
  return getJson<PublicRadarSnapshot>(`/api/nexus/public/radar?${qs}`);
}

export function fetchPublicRadarEvents(limit = 50, symbol?: string) {
  const qs = new URLSearchParams();
  qs.set("limit", String(limit));
  if (symbol) qs.set("symbol", symbol);
  return getJson<{ ok: boolean; events: LiveRankEvent[]; ranking_history_authority?: string }>(
    `/api/nexus/public/radar/events?${qs}`,
  );
}

export function fetchPublicRadarSymbol(symbol: string) {
  return getJson<{
    ok: boolean;
    symbol: string;
    row?: LiveRankingRow | null;
    closest_watch?: LiveRankingRow | null;
    events?: LiveRankEvent[];
    in_radar?: boolean;
    error?: string;
  }>(`/api/nexus/public/radar/${encodeURIComponent(symbol)}`);
}

/** Build rank step points from SERVER events (ascending time). No localStorage. */
export function rankStepPointsFromEvents(
  events: LiveRankEvent[],
  symbol: string,
): { timestamp: number; value: number }[] {
  const sym = symbol.toUpperCase();
  return [...events]
    .filter((e) => e.symbol === sym && e.rank != null && Number.isFinite(e.timestamp))
    .sort((a, b) => a.timestamp - b.timestamp)
    .map((e) => ({ timestamp: e.timestamp, value: e.rank as number }));
}
