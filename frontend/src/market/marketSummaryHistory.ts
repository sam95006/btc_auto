/** Public Market Summary History client (V18.2.19). Real snapshots only. */

export type MarketSummaryPoint = {
  timestamp: number;
  rising: number;
  neutral: number;
  falling: number;
  insufficient?: number;
  regime: string;
  market_risk: number | null;
  scanner_count: number;
  radar_count: number;
  trade_count: number;
  qualified_count: number;
  radar_eligible_count: number;
  events_new: number;
  events_up: number;
  events_down: number;
  events_out: number;
  fabricated?: boolean;
};

export type MarketSummaryHistoryResponse = {
  ok?: boolean;
  contract?: string;
  interval_ms?: number;
  retention_ms?: number;
  hours?: number;
  count: number;
  points: MarketSummaryPoint[];
  fabricated_visual_count: number;
  history_authority?: string;
  store_mode?: string;
  member_execution?: number;
  error?: string;
};

export async function fetchMarketSummaryHistory(opts?: {
  hours?: number;
  limit?: number;
}): Promise<MarketSummaryHistoryResponse> {
  const qs = new URLSearchParams();
  qs.set("hours", String(opts?.hours ?? 24));
  qs.set("limit", String(opts?.limit ?? 400));
  const res = await fetch(`/api/nexus/public/market-summary/history?${qs}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`market_summary_http_${res.status}`);
  const body = (await res.json()) as MarketSummaryHistoryResponse;
  return {
    ...body,
    points: Array.isArray(body.points) ? body.points.filter((p) => !p.fabricated) : [],
    fabricated_visual_count: body.fabricated_visual_count ?? 0,
    count: Array.isArray(body.points) ? body.points.length : 0,
  };
}
