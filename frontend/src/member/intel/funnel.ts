/** Honest funnel formatting for Member Intelligence (UX-B). */

export const UNAVAILABLE = "UNAVAILABLE" as const;

export const FUNNEL_STAGE_DEFS = [
  { key: "markets_scanned", label: "Markets scanned" },
  { key: "liquidity", label: "Liquidity" },
  { key: "data_quality", label: "Data quality" },
  { key: "ai_analysis", label: "AI analysis" },
  { key: "cost_blocked", label: "Cost blocked" },
  { key: "risk_blocked", label: "Risk blocked" },
] as const;

export type FunnelStageKey = (typeof FUNNEL_STAGE_DEFS)[number]["key"];

export type FunnelStageInput = {
  key: string;
  label: string;
  count: number | null | undefined;
  available: boolean;
};

export type FunnelStageDisplay = {
  key: string;
  label: string;
  count: number | null;
  available: boolean;
  display: string;
};

/** Never substitute unavailable with 0. */
export function formatFunnelCount(
  count: number | null | undefined,
  available: boolean,
): string {
  if (!available) return UNAVAILABLE;
  if (count == null || Number.isNaN(count)) return UNAVAILABLE;
  return String(count);
}

export function buildFunnelStages(stages: FunnelStageInput[]): FunnelStageDisplay[] {
  return stages.map((s) => ({
    key: s.key,
    label: s.label,
    count: s.available ? (s.count ?? null) : null,
    available: s.available,
    display: formatFunnelCount(s.count, s.available),
  }));
}

export function funnelSummary(stages: FunnelStageDisplay[]): string {
  return stages.map((s) => `${s.label}: ${s.display}`).join(" → ");
}
