/**
 * PUB18-A Live Funnel + Market Pulse first-screen models.
 * Honest LIVE_READ_ONLY / STALE / UNAVAILABLE / FIXTURE — never bare LIVE zeros.
 * No Founder positions, leverage, private thresholds, order IDs, Lessons, or trade buttons.
 */

export type AiPosture = "LONG" | "SHORT" | "WAIT" | "ABSTAIN";

export type DataClassLabel = "LIVE_READ_ONLY" | "STALE" | "UNAVAILABLE" | "FIXTURE";

export type PulseAnswerId =
  | "global_market_state"
  | "crypto_derivatives_risk"
  | "top_3_opportunities"
  | "ai_posture"
  | "supporting_evidence"
  | "counter_evidence"
  | "invalidation"
  | "data_freshness"
  | "data_class_label";

export const PULSE_ANSWER_IDS: readonly PulseAnswerId[] = [
  "global_market_state",
  "crypto_derivatives_risk",
  "top_3_opportunities",
  "ai_posture",
  "supporting_evidence",
  "counter_evidence",
  "invalidation",
  "data_freshness",
  "data_class_label",
] as const;

export const PULSE_QUESTIONS: Record<PulseAnswerId, string> = {
  global_market_state: "Global Market State",
  crypto_derivatives_risk: "Crypto Derivatives Risk",
  top_3_opportunities: "Top 3 Opportunities",
  ai_posture: "AI posture",
  supporting_evidence: "Supporting Evidence",
  counter_evidence: "Counter Evidence",
  invalidation: "Invalidation",
  data_freshness: "Data Freshness",
  data_class_label: "Shadow / Live / Fixture label",
};

export const FUNNEL_STAGE_DEFS = [
  { id: "scanned", label: "Scanned" },
  { id: "data_available", label: "Data available" },
  { id: "liquidity", label: "Liquidity" },
  { id: "data_trust", label: "Data Trust" },
  { id: "candidate", label: "Candidate" },
  { id: "ai_review", label: "AI Review" },
  { id: "cost_blocked", label: "Cost Blocked" },
  { id: "risk_blocked", label: "Risk Blocked" },
  { id: "shadow_decisions", label: "Shadow Decisions" },
] as const;

export type FunnelStage = {
  id: string;
  label: string;
  count: number | null;
  available: boolean;
  display: string;
};

export type TopOpportunity = {
  rank: number;
  market: string;
  contract: string;
  side_hint: AiPosture | string;
  note: string;
};

export type PulseAnswer = {
  id: PulseAnswerId;
  question: string;
  answer: string;
  detail: string;
  state: string;
  markets?: TopOpportunity[];
  items?: Array<{ summary: string; polarity?: string }>;
  metrics?: Array<{
    key: string;
    display: string;
    available: boolean;
    provider_required?: boolean;
  }>;
  actually_traded?: boolean;
};

export type LiveFunnelFirstScreenModel = {
  caseId: string;
  dataClass: DataClassLabel | string;
  chromeLabel: string;
  answers: PulseAnswer[];
  aiPosture: AiPosture;
  dataFreshness: string;
  funnel: { stages: FunnelStage[]; summary: string };
  note: string;
  tradeButtons: false;
};

/** Honest display: never show fabricated Live zero for missing / unavailable. */
export function honestDisplay(
  value: string | number | null | undefined,
  state: string,
): string {
  const s = (state || "").toUpperCase();
  if (s === "UNAVAILABLE" || s === "BLOCKED") return "UNAVAILABLE";
  if (s === "STALE") return "STALE";
  if (s === "FIXTURE") {
    if (value === null || value === undefined || value === "") return "FIXTURE";
  }
  if (s === "EMPTY") return "none in scope";
  if (value === null || value === undefined || value === "") {
    return s === "LIVE_READ_ONLY" ? "UNAVAILABLE" : s || "UNAVAILABLE";
  }
  return String(value);
}

export function formatFunnelCount(
  count: number | null | undefined,
  available: boolean,
  dataClass: string,
): string {
  if (!available) {
    const dc = (dataClass || "").toUpperCase();
    if (dc === "STALE") return "STALE";
    return "UNAVAILABLE";
  }
  if (count == null || Number.isNaN(count)) return "UNAVAILABLE";
  return String(count);
}

export const FORBIDDEN_FOUNDER_FIELD_NAMES = [
  "position_size",
  "leverage",
  "exact_entry",
  "exact_stop",
  "entry_price",
  "stop_loss",
  "order_id",
  "private_threshold",
  "private_thresholds",
  "lesson_memory",
  "private_lesson",
  "place_order",
  "trade_now",
  "execution_controls",
] as const;

function baseUnavailable(
  caseId: string,
  dataClass: DataClassLabel,
  posture: AiPosture = "ABSTAIN",
): LiveFunnelFirstScreenModel {
  const stages: FunnelStage[] = FUNNEL_STAGE_DEFS.map((s) => ({
    id: s.id,
    label: s.label,
    count: null,
    available: false,
    display: formatFunnelCount(null, false, dataClass),
  }));
  return {
    caseId,
    dataClass,
    chromeLabel: dataClass,
    aiPosture: posture,
    dataFreshness: dataClass,
    tradeButtons: false,
    note: `${dataClass} · READ ONLY · Shadow Decisions only · no trade buttons`,
    funnel: {
      stages,
      summary: stages.map((s) => `${s.label}: ${s.display}`).join(" → "),
    },
    answers: PULSE_ANSWER_IDS.map((id) => ({
      id,
      question: PULSE_QUESTIONS[id],
      answer:
        id === "ai_posture"
          ? posture
          : id === "data_class_label"
            ? dataClass
            : id === "counter_evidence"
              ? "none in scope"
              : dataClass,
      detail: "Honest label — not fabricated Live zero",
      state: dataClass,
      actually_traded: false,
    })),
  };
}

export function buildLiveFunnelScreen(
  variant:
    | "live_read_only"
    | "fixture_wait"
    | "fixture_long"
    | "stale"
    | "unavailable" = "live_read_only",
): LiveFunnelFirstScreenModel {
  if (variant === "stale") return baseUnavailable("pub18_stale", "STALE");
  if (variant === "unavailable") return baseUnavailable("pub18_unavailable", "UNAVAILABLE");

  if (variant === "live_read_only") {
    const counts: Record<string, number> = {
      scanned: 35,
      data_available: 0,
      liquidity: 0,
      data_trust: 0,
      candidate: 0,
      ai_review: 0,
      cost_blocked: 0,
      risk_blocked: 40,
      shadow_decisions: 0,
    };
    const stages: FunnelStage[] = FUNNEL_STAGE_DEFS.map((s) => ({
      id: s.id,
      label: s.label,
      count: counts[s.id],
      available: true,
      display: formatFunnelCount(counts[s.id], true, "LIVE_READ_ONLY"),
    }));
    const top3: TopOpportunity[] = [
      {
        rank: 1,
        market: "BTCUSDT",
        contract: "BTCUSDT.PERP",
        side_hint: "ABSTAIN",
        note: "Live catalog visible · candidate fail-closed",
      },
      {
        rank: 2,
        market: "ETHUSDT",
        contract: "ETHUSDT.PERP",
        side_hint: "ABSTAIN",
        note: "Data Trust incomplete — observe only",
      },
      {
        rank: 3,
        market: "BNBUSDT",
        contract: "BNBUSDT.PERP",
        side_hint: "WAIT",
        note: "Await data completeness",
      },
    ];
    return {
      caseId: "pub18_live_read_only_bounded",
      dataClass: "LIVE_READ_ONLY",
      chromeLabel: "LIVE_READ_ONLY",
      aiPosture: "ABSTAIN",
      dataFreshness: "LIVE_READ_ONLY",
      tradeButtons: false,
      note: "LIVE_READ_ONLY · READ ONLY · Shadow Decisions only · NOT INVESTMENT ADVICE · no trade buttons",
      funnel: {
        stages,
        summary: stages.map((s) => `${s.label}: ${s.display}`).join(" → "),
      },
      answers: [
        {
          id: "global_market_state",
          question: PULSE_QUESTIONS.global_market_state,
          answer: "Official public catalog read-only · eligibility fail-closed",
          detail: "regime=OBSERVE",
          state: "LIVE_READ_ONLY",
        },
        {
          id: "crypto_derivatives_risk",
          question: PULSE_QUESTIONS.crypto_derivatives_risk,
          answer: "Derivatives metrics incomplete on bounded sample — not fabricated",
          detail: "risk_band=UNAVAILABLE",
          state: "LIVE_READ_ONLY",
          metrics: [
            { key: "funding", display: "UNAVAILABLE", available: false },
            { key: "open_interest", display: "UNAVAILABLE", available: false },
          ],
        },
        {
          id: "top_3_opportunities",
          question: PULSE_QUESTIONS.top_3_opportunities,
          answer: top3.map((t) => `${t.market} (${t.side_hint})`).join(" · "),
          detail: "Public opportunities only · no Founder position / leverage / entry",
          state: "LIVE_READ_ONLY",
          markets: top3,
        },
        {
          id: "ai_posture",
          question: PULSE_QUESTIONS.ai_posture,
          answer: "ABSTAIN",
          detail: "Suggestion / Shadow Decision posture only — not an order",
          state: "LIVE_READ_ONLY",
        },
        {
          id: "supporting_evidence",
          question: PULSE_QUESTIONS.supporting_evidence,
          answer: "Official Bybit/Binance public catalog reachable",
          detail: "1 item(s)",
          state: "LIVE_READ_ONLY",
          items: [
            {
              summary: "Official Bybit/Binance public catalog reachable",
              polarity: "SUPPORTING",
            },
          ],
        },
        {
          id: "counter_evidence",
          question: PULSE_QUESTIONS.counter_evidence,
          answer: "Feature fields missing → eligible=0 fail-closed",
          detail: "1 item(s)",
          state: "LIVE_READ_ONLY",
          items: [
            {
              summary: "Feature fields missing → eligible=0 fail-closed",
              polarity: "CONTRADICTING",
            },
          ],
        },
        {
          id: "invalidation",
          question: PULSE_QUESTIONS.invalidation,
          answer: "Invalidate ABSTAIN only when Data Trust + liquidity gates pass",
          detail: "status=INTACT",
          state: "LIVE_READ_ONLY",
        },
        {
          id: "data_freshness",
          question: PULSE_QUESTIONS.data_freshness,
          answer: "LIVE_READ_ONLY",
          detail: "LIVE_READ_ONLY / STALE / UNAVAILABLE / FIXTURE — never fake Live zeros",
          state: "LIVE_READ_ONLY",
        },
        {
          id: "data_class_label",
          question: PULSE_QUESTIONS.data_class_label,
          answer: "LIVE_READ_ONLY",
          detail: "Honest Shadow / Live / Fixture labeling (LIVE_READ_ONLY not bare LIVE)",
          state: "LIVE_READ_ONLY",
        },
      ],
    };
  }

  const isLong = variant === "fixture_long";
  const posture: AiPosture = isLong ? "LONG" : "WAIT";
  const counts: Record<string, number> = {
    scanned: 22,
    data_available: 17,
    liquidity: 14,
    data_trust: 13,
    candidate: 6,
    ai_review: 4,
    cost_blocked: 1,
    risk_blocked: 3,
    shadow_decisions: 1,
  };
  const stages: FunnelStage[] = FUNNEL_STAGE_DEFS.map((s) => ({
    id: s.id,
    label: s.label,
    count: counts[s.id],
    available: true,
    display: formatFunnelCount(counts[s.id], true, "FIXTURE"),
  }));
  const top3: TopOpportunity[] = isLong
    ? [
        {
          rank: 1,
          market: "BTCUSDT",
          contract: "BTCUSDT.PERP",
          side_hint: "LONG",
          note: "Public suggestion only — Shadow Decision, not a fill",
        },
        {
          rank: 2,
          market: "ETHUSDT",
          contract: "ETHUSDT.PERP",
          side_hint: "WAIT",
          note: "Await confirmation",
        },
        {
          rank: 3,
          market: "BNBUSDT",
          contract: "BNBUSDT.PERP",
          side_hint: "WAIT",
          note: "Secondary watch",
        },
      ]
    : [
        {
          rank: 1,
          market: "BTCUSDT",
          contract: "BTCUSDT.PERP",
          side_hint: "WAIT",
          note: "Shadow observatory — not an order",
        },
        {
          rank: 2,
          market: "ETHUSDT",
          contract: "ETHUSDT.PERP",
          side_hint: "WAIT",
          note: "Derivatives risk elevated vs spot",
        },
        {
          rank: 3,
          market: "SOLUSDT",
          contract: "SOLUSDT.PERP",
          side_hint: "ABSTAIN",
          note: "Insufficient confirmation",
        },
      ];

  return {
    caseId: isLong ? "pub18_fixture_long_observe" : "pub18_fixture_wait",
    dataClass: "FIXTURE",
    chromeLabel: "FIXTURE",
    aiPosture: posture,
    dataFreshness: "FIXTURE",
    tradeButtons: false,
    note: "FIXTURE · READ ONLY · Shadow Decisions only · NOT INVESTMENT ADVICE · no trade buttons",
    funnel: {
      stages,
      summary: stages.map((s) => `${s.label}: ${s.display}`).join(" → "),
    },
    answers: [
      {
        id: "global_market_state",
        question: PULSE_QUESTIONS.global_market_state,
        answer: isLong
          ? "Constructive crypto bias · equity risk-on soft (fixture)"
          : "Mixed risk appetite · crypto breadth soft (fixture)",
        detail: isLong ? "regime=RISK_ON_SOFT" : "regime=MIXED",
        state: "FIXTURE",
      },
      {
        id: "crypto_derivatives_risk",
        question: PULSE_QUESTIONS.crypto_derivatives_risk,
        answer: isLong
          ? "Crowding moderate · basis stable (fixture)"
          : "Funding elevated · OI divergence watch (fixture)",
        detail: isLong ? "risk_band=MODERATE" : "risk_band=ELEVATED",
        state: "FIXTURE",
        metrics: [
          {
            key: "funding",
            display: "PROVIDER_REQUIRED",
            available: false,
            provider_required: true,
          },
          {
            key: "open_interest",
            display: "PROVIDER_REQUIRED",
            available: false,
            provider_required: true,
          },
        ],
      },
      {
        id: "top_3_opportunities",
        question: PULSE_QUESTIONS.top_3_opportunities,
        answer: top3.map((t) => `${t.market} (${t.side_hint})`).join(" · "),
        detail: "Public opportunities only · no Founder position / leverage / entry",
        state: "FIXTURE",
        markets: top3,
      },
      {
        id: "ai_posture",
        question: PULSE_QUESTIONS.ai_posture,
        answer: posture,
        detail: "Suggestion / Shadow Decision posture only — not an order",
        state: "FIXTURE",
      },
      {
        id: "supporting_evidence",
        question: PULSE_QUESTIONS.supporting_evidence,
        answer: isLong
          ? "Higher-high structure intact on public timeframe"
          : "Breadth not confirming breakout; Volatility expansion risk flagged",
        detail: "fixture evidence",
        state: "FIXTURE",
      },
      {
        id: "counter_evidence",
        question: PULSE_QUESTIONS.counter_evidence,
        answer: isLong
          ? "Derivatives provider still required for funding confirmation"
          : "Short-term momentum still positive",
        detail: "counter fixture",
        state: "FIXTURE",
      },
      {
        id: "invalidation",
        question: PULSE_QUESTIONS.invalidation,
        answer: isLong
          ? "Invalidate LONG bias if structure breaks and risk band rises"
          : "Invalidate WAIT if breadth confirms with fresh derivatives feed",
        detail: "status=INTACT",
        state: "FIXTURE",
      },
      {
        id: "data_freshness",
        question: PULSE_QUESTIONS.data_freshness,
        answer: "FIXTURE",
        detail: "Never treat FIXTURE as LIVE",
        state: "FIXTURE",
      },
      {
        id: "data_class_label",
        question: PULSE_QUESTIONS.data_class_label,
        answer: "FIXTURE",
        detail: "Honest Shadow / Live / Fixture labeling",
        state: "FIXTURE",
      },
    ],
  };
}
