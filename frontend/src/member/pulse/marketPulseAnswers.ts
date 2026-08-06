/**
 * PUB17-B Market Pulse first-screen model — nine member answers only.
 * Never renders Founder private fields (size, leverage, entry/stop, order id).
 * PROVIDER_REQUIRED / UNAVAILABLE never coerce to Live zeros.
 */

export type AiPosture = "LONG" | "SHORT" | "WAIT" | "ABSTAIN";

export type PulseAvailability =
  | "AVAILABLE"
  | "PROVIDER_REQUIRED"
  | "UNAVAILABLE"
  | "BLOCKED"
  | "DEMO_DATA"
  | "empty"
  | "FRESH"
  | "STALE"
  | "DEGRADED"
  | "ANALYSIS_ONLY"
  | "NOT_ACTUAL_TRADING";

export type PulseAnswerId =
  | "global_market_state"
  | "crypto_derivatives_risk"
  | "top_3_markets_contracts"
  | "ai_posture"
  | "supporting_evidence"
  | "counter_evidence"
  | "invalidation"
  | "data_freshness"
  | "analysis_vs_actual_trading";

export const PULSE_ANSWER_IDS: readonly PulseAnswerId[] = [
  "global_market_state",
  "crypto_derivatives_risk",
  "top_3_markets_contracts",
  "ai_posture",
  "supporting_evidence",
  "counter_evidence",
  "invalidation",
  "data_freshness",
  "analysis_vs_actual_trading",
] as const;

export const PULSE_QUESTIONS: Record<PulseAnswerId, string> = {
  global_market_state: "Global market state",
  crypto_derivatives_risk: "Crypto derivatives risk",
  top_3_markets_contracts: "Top 3 markets / contracts",
  ai_posture: "AI posture",
  supporting_evidence: "Supporting evidence",
  counter_evidence: "Counter-evidence",
  invalidation: "Invalidation",
  data_freshness: "Data freshness",
  analysis_vs_actual_trading: "Analysis vs actual trading",
};

export type TopMarket = {
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
  state: PulseAvailability | string;
  markets?: TopMarket[];
  items?: Array<{ summary: string; polarity?: string; freshness?: string }>;
  metrics?: Array<{
    key: string;
    display: string;
    available: boolean;
    provider_required?: boolean;
  }>;
  flag?: string;
  actually_traded?: boolean;
};

export type MarketPulseFirstScreenModel = {
  caseId: string;
  mode: string;
  chromeLabel: string;
  answers: PulseAnswer[];
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
  if (value === null || value === undefined || value === "") {
    return s === "DEMO_DATA" ? "DEMO_DATA" : "UNAVAILABLE";
  }
  return String(value);
}

export function buildDemoMarketPulseScreen(
  variant: "demo_wait" | "provider_required" | "unavailable" | "demo_long" = "demo_wait",
): MarketPulseFirstScreenModel {
  if (variant === "provider_required") {
    return {
      caseId: "pulse_provider_required",
      mode: "PROVIDER_REQUIRED",
      chromeLabel: "PROVIDER_REQUIRED",
      aiPosture: "ABSTAIN",
      dataFreshness: "PROVIDER_REQUIRED",
      note: "PROVIDER_REQUIRED · READ ONLY · NOT INVESTMENT ADVICE · no exchange orders",
      answers: PULSE_ANSWER_IDS.map((id) => ({
        id,
        question: PULSE_QUESTIONS[id],
        answer:
          id === "ai_posture"
            ? "ABSTAIN"
            : id === "analysis_vs_actual_trading"
              ? "PROVIDER_REQUIRED"
              : "PROVIDER_REQUIRED",
        detail:
          id === "analysis_vs_actual_trading"
            ? "Member surface is analysis-only · exchange write disabled"
            : "No legal provider bound — not fabricated",
        state: "PROVIDER_REQUIRED",
        actually_traded: false,
        markets: [],
        items: [],
        metrics:
          id === "crypto_derivatives_risk"
            ? [
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
              ]
            : undefined,
      })),
    };
  }

  if (variant === "unavailable") {
    return {
      caseId: "pulse_unavailable",
      mode: "UNAVAILABLE",
      chromeLabel: "UNAVAILABLE",
      aiPosture: "ABSTAIN",
      dataFreshness: "UNAVAILABLE",
      note: "UNAVAILABLE · READ ONLY · NOT INVESTMENT ADVICE · no exchange orders",
      answers: PULSE_ANSWER_IDS.map((id) => ({
        id,
        question: PULSE_QUESTIONS[id],
        answer:
          id === "ai_posture"
            ? "ABSTAIN"
            : id === "counter_evidence"
              ? "none in scope"
              : id === "analysis_vs_actual_trading"
                ? "UNAVAILABLE"
                : "UNAVAILABLE",
        detail: "Unavailable — not shown as zero",
        state: "UNAVAILABLE",
        actually_traded: false,
      })),
    };
  }

  const top3: TopMarket[] =
    variant === "demo_long"
      ? [
          {
            rank: 1,
            market: "BTCUSDT",
            contract: "BTCUSDT.PERP",
            side_hint: "LONG",
            note: "Public suggestion only — analysis, not a fill",
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
            note: "Structure observatory — not an order",
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

  const posture: AiPosture = variant === "demo_long" ? "LONG" : "WAIT";

  const answers: PulseAnswer[] = [
    {
      id: "global_market_state",
      question: PULSE_QUESTIONS.global_market_state,
      answer:
        variant === "demo_long"
          ? "Constructive crypto bias · equity risk-on soft"
          : "Mixed risk appetite · crypto leading breadth soft",
      detail: variant === "demo_long" ? "regime=RISK_ON_SOFT" : "regime=MIXED",
      state: "DEMO_DATA",
    },
    {
      id: "crypto_derivatives_risk",
      question: PULSE_QUESTIONS.crypto_derivatives_risk,
      answer:
        variant === "demo_long"
          ? "Crowding moderate · basis stable (fixture)"
          : "Funding elevated · OI divergence watch",
      detail: variant === "demo_long" ? "risk_band=MODERATE" : "risk_band=ELEVATED",
      state: "DEMO_DATA",
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
      id: "top_3_markets_contracts",
      question: PULSE_QUESTIONS.top_3_markets_contracts,
      answer: top3.map((t) => `${t.market} (${t.side_hint})`).join(" · "),
      detail: "Public markets/contracts only · no position size / leverage / entry",
      state: "DEMO_DATA",
      markets: top3,
    },
    {
      id: "ai_posture",
      question: PULSE_QUESTIONS.ai_posture,
      answer: posture,
      detail: "Suggestion / research posture only — not an order",
      state: "DEMO_DATA",
    },
    {
      id: "supporting_evidence",
      question: PULSE_QUESTIONS.supporting_evidence,
      answer:
        variant === "demo_long"
          ? "Higher-high structure intact on public timeframe"
          : "Breadth not confirming breakout; Volatility expansion risk flagged",
      detail: "fixture evidence",
      state: "DEMO_DATA",
      items: [
        {
          summary:
            variant === "demo_long"
              ? "Higher-high structure intact on public timeframe"
              : "Breadth not confirming breakout",
          polarity: "SUPPORTING",
          freshness: "DEMO_DATA",
        },
      ],
    },
    {
      id: "counter_evidence",
      question: PULSE_QUESTIONS.counter_evidence,
      answer:
        variant === "demo_long"
          ? "Derivatives provider still required for funding confirmation"
          : "Short-term momentum still positive",
      detail: "counter fixture",
      state: "DEMO_DATA",
      items: [
        {
          summary:
            variant === "demo_long"
              ? "Derivatives provider still required for funding confirmation"
              : "Short-term momentum still positive",
          polarity: "CONTRADICTING",
          freshness: variant === "demo_long" ? "PROVIDER_REQUIRED" : "DEMO_DATA",
        },
      ],
    },
    {
      id: "invalidation",
      question: PULSE_QUESTIONS.invalidation,
      answer:
        variant === "demo_long"
          ? "Invalidate LONG bias if structure breaks and risk band rises"
          : "Invalidate WAIT if breadth confirms with fresh derivatives feed",
      detail: "status=INTACT",
      state: "DEMO_DATA",
    },
    {
      id: "data_freshness",
      question: PULSE_QUESTIONS.data_freshness,
      answer: "DEMO_DATA",
      detail: "Never treat DEMO_DATA / PROVIDER_REQUIRED as LIVE",
      state: "DEMO_DATA",
    },
    {
      id: "analysis_vs_actual_trading",
      question: PULSE_QUESTIONS.analysis_vs_actual_trading,
      answer: "ANALYSIS_ONLY · NOT ACTUAL TRADING",
      detail: "Member surface is analysis-only · exchange write disabled",
      state: variant === "demo_long" ? "NOT_ACTUAL_TRADING" : "ANALYSIS_ONLY",
      flag: variant === "demo_long" ? "NOT_ACTUAL_TRADING" : "ANALYSIS_ONLY",
      actually_traded: false,
    },
  ];

  return {
    caseId: variant === "demo_long" ? "pulse_demo_long_observe" : "pulse_demo_wait",
    mode: "DEMO_DATA",
    chromeLabel: "DEMO_DATA",
    aiPosture: posture,
    dataFreshness: "DEMO_DATA",
    note: "DEMO_DATA · READ ONLY · NOT INVESTMENT ADVICE · no exchange orders",
    answers,
  };
}

/** Banned Founder private field names — must never appear as rendered keys. */
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
  "strategy_source",
  "private_strategy_source",
] as const;
