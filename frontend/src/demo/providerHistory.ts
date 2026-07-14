/**
 * Sanitized static provider history for Provider Intelligence charts (MVP-18).
 * READ ONLY · NOT INVESTMENT ADVICE · no /data · no secrets · no routing editor
 */

export type ProviderWatchBar = {
  label: string;
  groq: number;
  cerebras: number;
  note: string;
};

export type DivergenceEvent = {
  id: string;
  stage: string;
  title: string;
  summary: string;
};

export const PROVIDER_WATCH_BARS: ProviderWatchBar[] = [
  {
    label: "BTC shadow era",
    groq: 4,
    cerebras: 3,
    note: "Comparable shadow diagnostics only",
  },
  {
    label: "BTC Cerebras-first experiment",
    groq: 1,
    cerebras: 5,
    note: "experiment only · not permanent",
  },
  {
    label: "ETH watch samples",
    groq: 2,
    cerebras: 2,
    note: "ETH watch conditions later missing (HOLD)",
  },
  {
    label: "Latest HOLD window",
    groq: 0,
    cerebras: 0,
    note: "valid_watch=0 under HOLD · no soak",
  },
];

export const PROVIDER_DIVERGENCE_TIMELINE: DivergenceEvent[] = [
  {
    id: "p1",
    stage: "P1 / shadow",
    title: "Groq vs Cerebras history reviewed",
    summary: "Shadow divergence captured · not used for graduation",
  },
  {
    id: "btc-exp",
    stage: "BTC Cerebras-first",
    title: "Experiment-only routing probe",
    summary: "BTC Cerebras-first was experiment only · permanent routing=false",
  },
  {
    id: "eth-hist",
    stage: "ETH Cerebras watch",
    title: "ETH Cerebras watch history",
    summary: "Historical watches existed · current gate: not reappeared",
  },
  {
    id: "hold",
    stage: "P2H HOLD",
    title: "Routing posture frozen",
    summary: "shadow ≠ graduation · operator approval required for future experiments",
  },
];

export const PROVIDER_ROUTING_POSTURE = {
  cerebrasFirst: "experiment only",
  shadowForGraduation: "not used",
  permanentRoutingChange: false,
  nextAction: "operator approval required before any future routing experiment",
  safetyNote: "No routing editor · Stage 4.19 blocked · READ ONLY · NOT INVESTMENT ADVICE",
} as const;

export const BTC_PROVIDER_DIVERGENCE_SUMMARY =
  "BTC provider divergence stays historical/diagnostic — Cerebras-first experiment does not imply permanent routing.";
