/**
 * PUB18-B Decision Detail + Learning Transparency model.
 * Twelve member-visible fields only. Never renders private graph / thresholds /
 * strategy weights / Founder entry-exit / prompts / raw CoT / account data.
 */

export type AiPosture = "LONG" | "SHORT" | "WAIT" | "ABSTAIN";

export type DetailAvailability =
  | "AVAILABLE"
  | "PROVIDER_REQUIRED"
  | "UNAVAILABLE"
  | "BLOCKED"
  | "DEMO_DATA"
  | "FIXTURE"
  | "LIVE_READ_ONLY"
  | "STALE"
  | "empty"
  | "FRESH"
  | "DEGRADED";

export type DecisionDetailFieldId =
  | "decision_timeline"
  | "market_regime"
  | "data_trust"
  | "strategy_expert_label"
  | "evidence"
  | "counter_evidence"
  | "risk_reason"
  | "why_wait_abstain"
  | "historical_similarity_aggregate"
  | "shadow_outcome"
  | "process_classification_aggregate"
  | "delayed_learning_summary";

export const DETAIL_FIELD_IDS: readonly DecisionDetailFieldId[] = [
  "decision_timeline",
  "market_regime",
  "data_trust",
  "strategy_expert_label",
  "evidence",
  "counter_evidence",
  "risk_reason",
  "why_wait_abstain",
  "historical_similarity_aggregate",
  "shadow_outcome",
  "process_classification_aggregate",
  "delayed_learning_summary",
] as const;

export const DETAIL_FIELD_LABELS: Record<DecisionDetailFieldId, string> = {
  decision_timeline: "Decision timeline",
  market_regime: "Market Regime",
  data_trust: "Data Trust",
  strategy_expert_label: "Strategy Expert label",
  evidence: "Evidence",
  counter_evidence: "Counter Evidence",
  risk_reason: "Risk reason",
  why_wait_abstain: "Why WAIT / ABSTAIN",
  historical_similarity_aggregate: "Historical similarity aggregate",
  shadow_outcome: "Shadow outcome",
  process_classification_aggregate: "Process classification aggregate",
  delayed_learning_summary: "Delayed learning summary",
};

export type TimelineStage = { stage: string; at: string };

export type DetailField = {
  id: DecisionDetailFieldId;
  label: string;
  answer: string;
  detail: string;
  state: DetailAvailability | string;
  stages?: TimelineStage[];
  items?: Array<{ summary: string; polarity?: string; freshness?: string }>;
  regime_label?: string;
  trust_band?: string;
  expert_label?: string;
  posture?: string;
  sample_count?: number | null;
  shadow_status?: string;
  learning_status?: string;
  private_lesson_memory?: boolean;
};

export type DecisionDetailModel = {
  caseId: string;
  decisionId: string;
  mode: string;
  chromeLabel: string;
  fields: DetailField[];
  aiPosture: AiPosture;
  dataFreshness: string;
  note: string;
};

/** Honest display: never show fabricated Live zero for missing providers. */
export function honestDisplay(
  value: string | number | null | undefined,
  state: string,
): string {
  const s = (state || "").toUpperCase();
  if (s === "PROVIDER_REQUIRED") return "PROVIDER_REQUIRED";
  if (s === "UNAVAILABLE" || s === "BLOCKED") return "UNAVAILABLE";
  if (s === "EMPTY") return "none in scope";
  if (s === "STALE") return value ? String(value) : "STALE";
  if (value === null || value === undefined || value === "") {
    return s === "DEMO_DATA" || s === "FIXTURE" ? s : "UNAVAILABLE";
  }
  return String(value);
}

export function buildDemoDecisionDetail(
  variant:
    | "demo_wait"
    | "demo_abstain"
    | "provider_required"
    | "stale"
    | "unavailable" = "demo_wait",
): DecisionDetailModel {
  if (variant === "provider_required") {
    return {
      caseId: "detail_provider_required",
      decisionId: "dec_pub18_provider_required",
      mode: "PROVIDER_REQUIRED",
      chromeLabel: "PROVIDER_REQUIRED",
      aiPosture: "ABSTAIN",
      dataFreshness: "PROVIDER_REQUIRED",
      note: "PROVIDER_REQUIRED · READ ONLY · no private graph / thresholds / weights / prompts / CoT",
      fields: DETAIL_FIELD_IDS.map((id) => ({
        id,
        label: DETAIL_FIELD_LABELS[id],
        answer:
          id === "why_wait_abstain"
            ? "ABSTAIN · provider binding required before suggestion"
            : id === "strategy_expert_label"
              ? "UNAVAILABLE"
              : "PROVIDER_REQUIRED",
        detail: "No legal provider bound — not fabricated",
        state: "PROVIDER_REQUIRED",
        private_lesson_memory: false,
      })),
    };
  }

  if (variant === "unavailable") {
    return {
      caseId: "detail_unavailable",
      decisionId: "dec_pub18_unavailable",
      mode: "UNAVAILABLE",
      chromeLabel: "UNAVAILABLE",
      aiPosture: "ABSTAIN",
      dataFreshness: "UNAVAILABLE",
      note: "UNAVAILABLE · READ ONLY · learning transparency withheld",
      fields: DETAIL_FIELD_IDS.map((id) => ({
        id,
        label: DETAIL_FIELD_LABELS[id],
        answer:
          id === "why_wait_abstain"
            ? "ABSTAIN · decision detail unavailable"
            : id === "counter_evidence" || id === "evidence"
              ? "none in scope"
              : "UNAVAILABLE",
        detail: "Unavailable — not shown as zero",
        state: "UNAVAILABLE",
        private_lesson_memory: false,
      })),
    };
  }

  if (variant === "demo_abstain") {
    return {
      caseId: "detail_demo_abstain",
      decisionId: "dec_pub18_abstain_001",
      mode: "DEMO_DATA",
      chromeLabel: "FIXTURE",
      aiPosture: "ABSTAIN",
      dataFreshness: "FIXTURE",
      note: "FIXTURE · READ ONLY · aggregates only · no private lesson memory",
      fields: [
        {
          id: "decision_timeline",
          label: DETAIL_FIELD_LABELS.decision_timeline,
          answer: "OBSERVING → RISK_REVIEW → ABSTAIN",
          detail: "stages=3",
          state: "FIXTURE",
          stages: [
            { stage: "OBSERVING", at: "2026-08-06T01:10:00Z" },
            { stage: "RISK_REVIEW", at: "2026-08-06T01:20:00Z" },
            { stage: "ABSTAIN", at: "2026-08-06T01:25:00Z" },
          ],
        },
        {
          id: "market_regime",
          label: DETAIL_FIELD_LABELS.market_regime,
          answer: "STRESS",
          detail: "Stress regime · elevated uncertainty",
          state: "FIXTURE",
          regime_label: "STRESS",
        },
        {
          id: "data_trust",
          label: DETAIL_FIELD_LABELS.data_trust,
          answer: "DEGRADED",
          detail: "Data trust degraded under stress fixture",
          state: "FIXTURE",
          trust_band: "DEGRADED",
        },
        {
          id: "strategy_expert_label",
          label: DETAIL_FIELD_LABELS.strategy_expert_label,
          answer: "DEFENSIVE_NO_TRADE",
          detail: "Public expert label only — no private weights",
          state: "FIXTURE",
          expert_label: "DEFENSIVE_NO_TRADE",
        },
        {
          id: "evidence",
          label: DETAIL_FIELD_LABELS.evidence,
          answer: "Liquidity thin across public venues (fixture)",
          detail: "1 item(s)",
          state: "FIXTURE",
          items: [
            {
              summary: "Liquidity thin across public venues (fixture)",
              polarity: "SUPPORTING",
              freshness: "FIXTURE",
            },
          ],
        },
        {
          id: "counter_evidence",
          label: DETAIL_FIELD_LABELS.counter_evidence,
          answer: "none in scope",
          detail: "0 item(s)",
          state: "empty",
          items: [],
        },
        {
          id: "risk_reason",
          label: DETAIL_FIELD_LABELS.risk_reason,
          answer: "Risk governor advisory: abstain under stress band",
          detail: "Advisory risk reason only — no override controls",
          state: "FIXTURE",
        },
        {
          id: "why_wait_abstain",
          label: DETAIL_FIELD_LABELS.why_wait_abstain,
          answer: "ABSTAIN because risk and data-trust gates blocked suggestion",
          detail: "posture=ABSTAIN",
          state: "FIXTURE",
          posture: "ABSTAIN",
        },
        {
          id: "historical_similarity_aggregate",
          label: DETAIL_FIELD_LABELS.historical_similarity_aggregate,
          answer: "8 similar public stress cases · 6 ABSTAIN · 2 WAIT",
          detail: "Aggregate counts only — never exact proprietary thresholds",
          state: "FIXTURE",
          sample_count: 8,
        },
        {
          id: "shadow_outcome",
          label: DETAIL_FIELD_LABELS.shadow_outcome,
          answer: "CLOSED_NO_FILL",
          detail: "Shadow closed without fill · process classified as risk_block",
          state: "FIXTURE",
          shadow_status: "CLOSED_NO_FILL",
        },
        {
          id: "process_classification_aggregate",
          label: DETAIL_FIELD_LABELS.process_classification_aggregate,
          answer: "Process: risk_block 62% · evidence_gap 25% · cost_block 13%",
          detail: "Public process aggregate — no private raw graph",
          state: "FIXTURE",
        },
        {
          id: "delayed_learning_summary",
          label: DETAIL_FIELD_LABELS.delayed_learning_summary,
          answer: "Delayed learning: public process note recorded · no private lesson",
          detail: "status=RECORDED_PUBLIC · no private lesson memory",
          state: "FIXTURE",
          learning_status: "RECORDED_PUBLIC",
          private_lesson_memory: false,
        },
      ],
    };
  }

  if (variant === "stale") {
    const wait = buildDemoDecisionDetail("demo_wait");
    return {
      ...wait,
      caseId: "detail_stale",
      decisionId: "dec_pub18_stale_001",
      chromeLabel: "STALE",
      dataFreshness: "STALE",
      note: "STALE · READ ONLY · do not treat as LIVE · refresh required",
      fields: wait.fields.map((f) => ({
        ...f,
        state: "STALE",
        detail: `${f.detail} · STALE`,
      })),
    };
  }

  return {
    caseId: "detail_demo_wait",
    decisionId: "dec_pub18_wait_001",
    mode: "DEMO_DATA",
    chromeLabel: "DEMO_DATA",
    aiPosture: "WAIT",
    dataFreshness: "DEMO_DATA",
    note: "DEMO_DATA · READ ONLY · learning transparency aggregates only",
    fields: [
      {
        id: "decision_timeline",
        label: DETAIL_FIELD_LABELS.decision_timeline,
        answer: "OBSERVING → AI_ANALYZING → AI_SUGGESTION → WAIT",
        detail: "stages=4",
        state: "DEMO_DATA",
        stages: [
          { stage: "OBSERVING", at: "2026-08-06T02:40:00Z" },
          { stage: "AI_ANALYZING", at: "2026-08-06T02:45:00Z" },
          { stage: "AI_SUGGESTION", at: "2026-08-06T02:50:00Z" },
          { stage: "WAIT", at: "2026-08-06T02:55:00Z" },
        ],
      },
      {
        id: "market_regime",
        label: DETAIL_FIELD_LABELS.market_regime,
        answer: "MIXED",
        detail: "Mixed regime · no dominant trend confirmation",
        state: "DEMO_DATA",
        regime_label: "MIXED",
      },
      {
        id: "data_trust",
        label: DETAIL_FIELD_LABELS.data_trust,
        answer: "MODERATE",
        detail: "Core public feeds present · derivatives provider still required",
        state: "DEMO_DATA",
        trust_band: "MODERATE",
      },
      {
        id: "strategy_expert_label",
        label: DETAIL_FIELD_LABELS.strategy_expert_label,
        answer: "DEFENSIVE_NO_TRADE",
        detail: "Public expert label only — no private weights",
        state: "DEMO_DATA",
        expert_label: "DEFENSIVE_NO_TRADE",
      },
      {
        id: "evidence",
        label: DETAIL_FIELD_LABELS.evidence,
        answer: "Breadth not confirming breakout; Volatility expansion risk flagged",
        detail: "2 item(s)",
        state: "DEMO_DATA",
        items: [
          {
            summary: "Breadth not confirming breakout",
            polarity: "SUPPORTING",
            freshness: "DEMO_DATA",
          },
          {
            summary: "Volatility expansion risk flagged",
            polarity: "SUPPORTING",
            freshness: "DEMO_DATA",
          },
        ],
      },
      {
        id: "counter_evidence",
        label: DETAIL_FIELD_LABELS.counter_evidence,
        answer: "Short-term momentum still positive",
        detail: "1 item(s)",
        state: "DEMO_DATA",
        items: [
          {
            summary: "Short-term momentum still positive",
            polarity: "CONTRADICTING",
            freshness: "DEMO_DATA",
          },
        ],
      },
      {
        id: "risk_reason",
        label: DETAIL_FIELD_LABELS.risk_reason,
        answer: "Cost / uncertainty band elevated for directional entry",
        detail: "Advisory risk reason only — no override controls",
        state: "DEMO_DATA",
      },
      {
        id: "why_wait_abstain",
        label: DETAIL_FIELD_LABELS.why_wait_abstain,
        answer: "WAIT because confirmation and data-trust gates incomplete",
        detail: "posture=WAIT",
        state: "DEMO_DATA",
        posture: "WAIT",
      },
      {
        id: "historical_similarity_aggregate",
        label: DETAIL_FIELD_LABELS.historical_similarity_aggregate,
        answer: "12 similar public cases · 7 WAIT · 3 ABSTAIN · 2 LONG",
        detail: "Aggregate counts only — never exact proprietary thresholds",
        state: "DEMO_DATA",
        sample_count: 12,
      },
      {
        id: "shadow_outcome",
        label: DETAIL_FIELD_LABELS.shadow_outcome,
        answer: "OPEN_SHADOW",
        detail: "Shadow decision open · no live fill · analysis only",
        state: "DEMO_DATA",
        shadow_status: "OPEN_SHADOW",
      },
      {
        id: "process_classification_aggregate",
        label: DETAIL_FIELD_LABELS.process_classification_aggregate,
        answer: "Process: evidence_gap 42% · risk_block 33% · cost_block 25%",
        detail: "Public process aggregate — no private raw graph",
        state: "DEMO_DATA",
      },
      {
        id: "delayed_learning_summary",
        label: DETAIL_FIELD_LABELS.delayed_learning_summary,
        answer: "Delayed learning pending shadow close · public summary only",
        detail: "status=PENDING · no private lesson memory",
        state: "DEMO_DATA",
        learning_status: "PENDING",
        private_lesson_memory: false,
      },
    ],
  };
}

/** Banned private field names — must never appear as rendered keys. */
export const FORBIDDEN_PRIVATE_FIELD_NAMES = [
  "private_raw_graph",
  "raw_graph",
  "proprietary_threshold",
  "private_threshold",
  "strategy_weights",
  "founder_entry",
  "founder_exit",
  "exact_entry",
  "exact_exit",
  "internal_prompt",
  "system_prompt",
  "raw_cot",
  "chain_of_thought",
  "account_data",
  "account_balance",
  "leverage",
  "position_size",
  "order_id",
] as const;
