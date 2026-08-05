import type { LifecycleState, MemberPosture } from "./lifecycleStates";

/** UX-A compatible nested intelligence shape (public-safe). */
export type CompatibleIntelligenceDto = {
  schema_version: string;
  symbol: string;
  decision_id: string;
  regime_probabilities: Record<string, number | string | boolean | null>;
  regime_label: string;
  ai_recommendation_state: string;
  ai_recommendation_message: string;
  supporting_evidence: EvidenceItem[];
  contradicting_evidence: EvidenceItem[];
  uncertainty: number | null;
  uncertainty_band: string;
  abstention_reason: string | null;
  strategy_expert_label: string;
  lesson_applied_label: string;
  similar_case_summary: SimilarCaseStats;
  data_freshness: string;
  decision_lifecycle_status: string;
  private_core_import_count: number;
  raw_memory_graph: boolean;
};

export type EvidenceItem = {
  evidence_summary: string;
  evidence_polarity: string;
  evidence_freshness: string;
  source_label: string;
  as_of?: string | null;
};

export type SimilarCaseStats = {
  similar_case_summary: string;
  similar_case_count: number | null;
  similar_case_overlap_band: string;
  win_rate: number | null;
  available: boolean;
  guarantee_claimed: boolean;
  display_count?: string;
};

export type FunnelStage = {
  key: string;
  label: string;
  count: number | null;
  available: boolean;
  display: string;
};

export type MemberIntelExperience = {
  case_id: string;
  symbol: string;
  decision_id: string;
  lifecycle_state: LifecycleState;
  posture: MemberPosture;
  mode: string;
  chrome_label: string;
  data_freshness: string;
  regime_label: string;
  funnel: {
    stages: FunnelStage[];
    summary: string;
    source_mode: string;
  };
  why_suggested: string[];
  contradicting_evidence: EvidenceItem[];
  supporting_evidence: EvidenceItem[];
  similar_case_stats: SimilarCaseStats;
  actually_ordered: boolean | null;
  actually_ordered_display: string;
  order_fill_claimed: boolean;
  suggestion_only: boolean;
  intelligence: CompatibleIntelligenceDto;
};
