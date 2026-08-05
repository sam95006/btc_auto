/**
 * Client-side DEMO_DATA catalog for Member Intelligence Experience.
 * Mirrors backend fixtures — never labeled LIVE.
 */
import type { MemberIntelExperience } from "./types";
import { buildFunnelStages, funnelSummary, FUNNEL_STAGE_DEFS } from "./funnel";
import { actuallyOrderedDisplay, chromeLabelForMode } from "./honesty";

function stagesFromCounts(
  counts: Record<string, { count: number | null; available: boolean }>,
) {
  return buildFunnelStages(
    FUNNEL_STAGE_DEFS.map((d) => ({
      key: d.key,
      label: d.label,
      count: counts[d.key]?.count ?? null,
      available: counts[d.key]?.available ?? false,
    })),
  );
}

function build(
  partial: Omit<MemberIntelExperience, "funnel" | "chrome_label" | "actually_ordered_display"> & {
    funnelCounts: Record<string, { count: number | null; available: boolean }>;
  },
): MemberIntelExperience {
  const stages = stagesFromCounts(partial.funnelCounts);
  const { funnelCounts: _, ...rest } = partial;
  return {
    ...rest,
    chrome_label: chromeLabelForMode(partial.mode),
    actually_ordered_display: actuallyOrderedDisplay(partial.actually_ordered),
    funnel: {
      stages,
      summary: funnelSummary(stages),
      source_mode: partial.mode,
    },
  };
}

export const MEMBER_INTEL_FIXTURES: MemberIntelExperience[] = [
  build({
    case_id: "mi_demo_wait_001",
    symbol: "BTCUSDT",
    decision_id: "pub_dec_mi_wait_001",
    lifecycle_state: "AI_SUGGESTION",
    posture: "WAIT",
    mode: "DEMO_DATA",
    data_freshness: "DEMO_DATA",
    regime_label: "MIXED",
    funnelCounts: {
      markets_scanned: { count: 42, available: true },
      liquidity: { count: 18, available: true },
      data_quality: { count: 11, available: true },
      ai_analysis: { count: 7, available: true },
      cost_blocked: { count: 2, available: true },
      risk_blocked: { count: 1, available: true },
    },
    why_suggested: [
      "Public momentum softens into mixed regime",
      "Liquidity ok but event-risk window open",
    ],
    supporting_evidence: [
      {
        evidence_summary: "Short-horizon public momentum still constructive",
        evidence_polarity: "SUPPORTING",
        evidence_freshness: "FRESH",
        source_label: "PUBLIC_MARKET",
      },
    ],
    contradicting_evidence: [
      {
        evidence_summary: "Elevated event-risk calendar cluster",
        evidence_polarity: "CONTRADICTING",
        evidence_freshness: "FRESH",
        source_label: "PUBLIC_CALENDAR",
      },
    ],
    similar_case_stats: {
      similar_case_summary: "4 similar public cases favored WAIT under mixed regime",
      similar_case_count: 4,
      similar_case_overlap_band: "MEDIUM",
      win_rate: null,
      available: true,
      guarantee_claimed: false,
      display_count: "4",
    },
    actually_ordered: false,
    order_fill_claimed: false,
    suggestion_only: true,
    intelligence: {
      schema_version: "public.intelligence.v2",
      symbol: "BTCUSDT",
      decision_id: "pub_dec_mi_wait_001",
      regime_probabilities: { available: true, regime_freshness: "FRESH" },
      regime_label: "MIXED",
      ai_recommendation_state: "WAIT",
      ai_recommendation_message: "Public momentum softens into mixed regime",
      supporting_evidence: [],
      contradicting_evidence: [],
      uncertainty: 0.5,
      uncertainty_band: "MEDIUM",
      abstention_reason: null,
      strategy_expert_label: "DEFENSIVE_NO_TRADE",
      lesson_applied_label: "LESSON_APPLIED",
      similar_case_summary: {
        similar_case_summary: "4 similar public cases favored WAIT",
        similar_case_count: 4,
        similar_case_overlap_band: "MEDIUM",
        win_rate: null,
        available: true,
        guarantee_claimed: false,
      },
      data_freshness: "DEMO_DATA",
      decision_lifecycle_status: "DECIDING",
      private_core_import_count: 0,
      raw_memory_graph: false,
    },
  }),
  build({
    case_id: "mi_unavailable_004",
    symbol: "BNBUSDT",
    decision_id: "pub_dec_mi_unavail_004",
    lifecycle_state: "UNAVAILABLE",
    posture: "WAIT",
    mode: "DEMO_DATA",
    data_freshness: "UNAVAILABLE",
    regime_label: "UNAVAILABLE",
    funnelCounts: {
      markets_scanned: { count: null, available: false },
      liquidity: { count: null, available: false },
      data_quality: { count: null, available: false },
      ai_analysis: { count: null, available: false },
      cost_blocked: { count: null, available: false },
      risk_blocked: { count: null, available: false },
    },
    why_suggested: [],
    supporting_evidence: [],
    contradicting_evidence: [],
    similar_case_stats: {
      similar_case_summary: "UNAVAILABLE",
      similar_case_count: null,
      similar_case_overlap_band: "UNAVAILABLE",
      win_rate: null,
      available: false,
      guarantee_claimed: false,
      display_count: "UNAVAILABLE",
    },
    actually_ordered: null,
    order_fill_claimed: false,
    suggestion_only: true,
    intelligence: {
      schema_version: "public.intelligence.v2",
      symbol: "BNBUSDT",
      decision_id: "pub_dec_mi_unavail_004",
      regime_probabilities: { available: false, regime_freshness: "UNAVAILABLE" },
      regime_label: "UNAVAILABLE",
      ai_recommendation_state: "WAIT",
      ai_recommendation_message: "",
      supporting_evidence: [],
      contradicting_evidence: [],
      uncertainty: null,
      uncertainty_band: "UNAVAILABLE",
      abstention_reason: "Source unavailable — fail closed",
      strategy_expert_label: "UNAVAILABLE",
      lesson_applied_label: "UNAVAILABLE",
      similar_case_summary: {
        similar_case_summary: "UNAVAILABLE",
        similar_case_count: null,
        similar_case_overlap_band: "UNAVAILABLE",
        win_rate: null,
        available: false,
        guarantee_claimed: false,
      },
      data_freshness: "UNAVAILABLE",
      decision_lifecycle_status: "UNAVAILABLE",
      private_core_import_count: 0,
      raw_memory_graph: false,
    },
  }),
];
