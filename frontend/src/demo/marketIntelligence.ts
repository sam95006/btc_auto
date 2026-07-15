/**
 * Sanitized static Market Intelligence fixtures (MVP-17).
 * READ ONLY · NOT INVESTMENT ADVICE · no /data · no secrets · no trading controls
 */

export type FleetIntel = {
  symbol: string;
  stance: string;
  latestIntent: string;
  validWatchCount: number;
  graduationStatus: string;
  confidence: number;
  riskGate: string;
  nextAction: string;
  drillLinks: { label: string; to: string }[];
};

export type CandidateRow = {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT" | "NONE";
  confidence: number | null;
  maeRisk: string;
  entryTrigger: string;
  invalidation: string;
  gateStatus: string;
  evidenceNote: string;
  nextAction: "View Evidence" | "Open Risk Card" | "Ask AI" | "View Gate";
  bucket: "long" | "short" | "waiting";
  links: {
    evidence: string;
    gate: string;
    provider: string;
    risk: string;
  };
};

export type SignalSeverity = "info" | "watch" | "warning" | "blocked";

export type SignalFeedRow = {
  id: string;
  time: string;
  symbol: string;
  provider: string;
  intent: string;
  direction: string;
  confidence: number | null;
  trigger: string;
  gateStatus: string;
  status:
    | "watch"
    | "soft_skip"
    | "hard_skip"
    | "blocked"
    | "confirmation_pending"
    | "graduated";
  severity: SignalSeverity;
  meaning: string;
  nextAction: "View Evidence" | "View Gate" | "View Risk" | "View Provider";
  evidenceHref: string;
  links: {
    evidence: string;
    gate: string;
    provider: string;
    risk: string;
  };
};

export type DecisionRadarCategory =
  | "market"
  | "gate"
  | "provider"
  | "safety"
  | "bullish"
  | "bearish"
  | "risk";

export type AnomalyRow = {
  id: string;
  symbol: string;
  category: DecisionRadarCategory;
  anomalyType: string;
  whatHappened: string;
  whyItMatters: string;
  firstAlert: string;
  latestValue: string;
  change: string;
  riskNote: string;
  evidenceHref: string;
  nextAction: "View Evidence" | "View Gate" | "View Risk" | "View Provider";
  links: {
    evidence: string;
    gate: string;
    provider: string;
    risk: string;
  };
};

export type CopilotPrompt = {
  id: string;
  label: string;
  prompt: string;
};

export type SafetyInvariant = {
  id: string;
  label: string;
  value: string;
  ok: boolean;
};

export type ProviderIntelFact = {
  id: string;
  label: string;
  value: string;
};

export type ValidationFact = {
  id: string;
  label: string;
  value: string;
  tone: "pass" | "wait" | "hold" | "blocked";
};

export const FLEET_INTELLIGENCE: FleetIntel[] = [
  {
    symbol: "BTC",
    stance: "Prior evidence only",
    latestIntent: "None",
    validWatchCount: 0,
    graduationStatus: "prior yes / latest 0",
    confidence: 0,
    riskGate: "HOLD",
    nextAction: "View Evidence",
    drillLinks: [
      { label: "Evidence", to: "/evidence?q=BTC#doc-summary-p2d-r1" },
      { label: "Provider", to: "/provider-shadow#btc-cerebras-first" },
      { label: "Risk", to: "/risk-evidence#checklist-safety-invariants" },
    ],
  },
  {
    symbol: "ETH",
    stance: "Watch condition not reappeared",
    latestIntent: "None",
    validWatchCount: 0,
    graduationStatus: "0",
    confidence: 0,
    riskGate: "WAIT",
    nextAction: "View Gate",
    drillLinks: [
      { label: "Gate", to: "/overview#checklist-eth-watch-reappearance" },
      { label: "Evidence", to: "/evidence?q=ETH&unresolved=true#doc-summary-p2f" },
      { label: "Risk", to: "/risk-evidence#checklist-safety-invariants" },
    ],
  },
  {
    symbol: "SOL",
    stance: "Skip / waiting",
    latestIntent: "Skip",
    validWatchCount: 0,
    graduationStatus: "n/a",
    confidence: 0,
    riskGate: "HOLD",
    nextAction: "Ask AI",
    drillLinks: [
      { label: "Evidence", to: "/evidence#doc-summaries" },
      { label: "Gate", to: "/overview#gate-checklist" },
    ],
  },
  {
    symbol: "PEPE",
    stance: "Skip / waiting",
    latestIntent: "Skip",
    validWatchCount: 0,
    graduationStatus: "n/a",
    confidence: 0,
    riskGate: "HOLD",
    nextAction: "Open Risk Card",
    drillLinks: [
      { label: "Risk", to: "/risk-evidence#checklist-safety-invariants" },
      { label: "Evidence", to: "/evidence#doc-summaries" },
    ],
  },
];

export const CANDIDATE_ROWS: CandidateRow[] = [
  {
    id: "btc-long",
    symbol: "BTC",
    direction: "LONG",
    confidence: null,
    maeRisk: "cap unchanged",
    entryTrigger: "—",
    invalidation: "—",
    gateStatus: "HOLD",
    evidenceNote: "prior graduation evidence exists; latest regen grad=0",
    nextAction: "View Evidence",
    bucket: "waiting",
    links: {
      evidence: "/evidence?q=BTC#p2-r1-btc",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#btc-cerebras-first",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "eth-wait",
    symbol: "ETH",
    direction: "NONE",
    confidence: null,
    maeRisk: "cap unchanged",
    entryTrigger: "watch missing",
    invalidation: "—",
    gateStatus: "WAIT",
    evidenceNote: "ETH watch conditions not reappeared",
    nextAction: "View Gate",
    bucket: "waiting",
    links: {
      evidence: "/evidence?q=ETH#eth-watch-reappearance",
      gate: "/overview#checklist-eth-watch-reappearance",
      provider: "/provider-shadow#provider-history-chart",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "sol-skip",
    symbol: "SOL",
    direction: "NONE",
    confidence: null,
    maeRisk: "n/a",
    entryTrigger: "—",
    invalidation: "—",
    gateStatus: "HOLD",
    evidenceNote: "waiting / skip under HOLD",
    nextAction: "Ask AI",
    bucket: "waiting",
    links: {
      evidence: "/evidence#doc-summaries",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#provider-routing-posture",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "pepe-skip",
    symbol: "PEPE",
    direction: "NONE",
    confidence: null,
    maeRisk: "n/a",
    entryTrigger: "—",
    invalidation: "—",
    gateStatus: "HOLD",
    evidenceNote: "waiting / skip under HOLD",
    nextAction: "Open Risk Card",
    bucket: "waiting",
    links: {
      evidence: "/evidence#doc-summaries",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#provider-routing-posture",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
];

export const SIGNAL_FEED: SignalFeedRow[] = [
  {
    id: "s1",
    time: "2026-07-14 08:00Z",
    symbol: "ETH",
    provider: "demo",
    intent: "NONE",
    direction: "NONE",
    confidence: null,
    trigger: "—",
    gateStatus: "WAIT",
    status: "blocked",
    severity: "blocked",
    meaning: "ETH has no valid watch condition, so regression should not run.",
    nextAction: "View Gate",
    evidenceHref: "/evidence?q=ETH",
    links: {
      evidence: "/evidence?q=ETH#doc-summary-p2f",
      gate: "/overview#checklist-eth-watch-reappearance",
      provider: "/provider-shadow#provider-history-chart",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "s2",
    time: "2026-07-14 07:30Z",
    symbol: "BTC",
    provider: "shadow-hist",
    intent: "WATCH_HIST",
    direction: "LONG",
    confidence: 0.52,
    trigger: "prior",
    gateStatus: "HOLD",
    status: "soft_skip",
    severity: "info",
    meaning: "BTC has prior evidence only; it is not the active blocker today.",
    nextAction: "View Evidence",
    evidenceHref: "/evidence?q=BTC",
    links: {
      evidence: "/evidence?q=BTC#p2-r1-btc",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#btc-cerebras-first",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "s3",
    time: "2026-07-13 22:00Z",
    symbol: "ETH",
    provider: "demo",
    intent: "confirm_pending",
    direction: "NONE",
    confidence: null,
    trigger: "no watch",
    gateStatus: "WAIT",
    status: "confirmation_pending",
    severity: "watch",
    meaning: "ETH confirmation stays pending until watch reappears.",
    nextAction: "View Gate",
    evidenceHref: "/overview#checklist-eth-watch-reappearance",
    links: {
      evidence: "/evidence?q=P2F#p2f-watch-gate",
      gate: "/overview#checklist-eth-watch-reappearance",
      provider: "/provider-shadow#provider-divergence-timeline",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "s4",
    time: "2026-07-12 16:00Z",
    symbol: "SYS",
    provider: "gate",
    intent: "BLOCK_419",
    direction: "NONE",
    confidence: null,
    trigger: "dossier",
    gateStatus: "HOLD",
    status: "blocked",
    severity: "warning",
    meaning: "Stage 4.19 blocked — needs actual BTC + ETH graduation.",
    nextAction: "View Gate",
    evidenceHref: "/overview#checklist-stage-419-dossier",
    links: {
      evidence: "/evidence?q=4.19",
      gate: "/overview#checklist-stage-419-dossier",
      provider: "/provider-shadow#provider-routing-posture",
      risk: "/risk-evidence#why-safe",
    },
  },
];

export const ANOMALY_ROWS: AnomalyRow[] = [
  {
    id: "a1",
    symbol: "BTC",
    category: "provider",
    anomalyType: "Provider divergence history",
    whatHappened: "Groq vs Cerebras history was reviewed under research HOLD.",
    whyItMatters: "Provider history informs reading, not permanent routing.",
    firstAlert: "P1 shadow era",
    latestValue: "permanent routing=false",
    change: "experiment only",
    riskNote: "Shadow not used for graduation",
    evidenceHref: "/provider-shadow#btc-cerebras-first",
    nextAction: "View Provider",
    links: {
      evidence: "/evidence?q=routing",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#btc-cerebras-first",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "a2",
    symbol: "ETH",
    category: "gate",
    anomalyType: "ETH watch condition missing",
    whatHappened: "ETH valid watch has not reappeared.",
    whyItMatters: "This is the primary blocker before any next regression.",
    firstAlert: "P2D-R1 / P2F",
    latestValue: "vw=0",
    change: "not reappeared",
    riskNote: "Next = wait · no 60m",
    evidenceHref: "/overview#unresolved-gate",
    nextAction: "View Gate",
    links: {
      evidence: "/evidence?q=ETH#eth-watch-reappearance",
      gate: "/overview#checklist-eth-watch-reappearance",
      provider: "/provider-shadow#provider-history-chart",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "a3",
    symbol: "SYS",
    category: "gate",
    anomalyType: "Stage 4.19 blocked",
    whatHappened: "Stage 4.19 dossier remains blocked.",
    whyItMatters: "Needs actual BTC + ETH graduation before any start discussion.",
    firstAlert: "product gate",
    latestValue: "blocked",
    change: "unchanged",
    riskNote: "Needs actual BTC+ETH graduation",
    evidenceHref: "/overview#checklist-stage-419-dossier",
    nextAction: "View Gate",
    links: {
      evidence: "/evidence?q=4.19",
      gate: "/overview#checklist-stage-419-dossier",
      provider: "/provider-shadow#provider-routing-posture",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "a4",
    symbol: "SYS",
    category: "safety",
    anomalyType: "No 60m recommended",
    whatHappened: "60m and auto-run stay false under HOLD.",
    whyItMatters: "Operators wait; they do not launch timed regressions from UI.",
    firstAlert: "P2G / P2H",
    latestValue: "60m=false",
    change: "HOLD",
    riskNote: "Auto-run=false",
    evidenceHref: "/overview#gate-checklist",
    nextAction: "View Risk",
    links: {
      evidence: "/evidence?q=HOLD",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#provider-routing-posture",
      risk: "/risk-evidence#why-safe",
    },
  },
  {
    id: "a5",
    symbol: "SYS",
    category: "market",
    anomalyType: "BTC prior evidence only",
    whatHappened: "BTC has prior evidence; latest confirmation is not current.",
    whyItMatters: "Useful history, but ETH remains the readiness blocker.",
    firstAlert: "P2D / P2D-R1",
    latestValue: "prior yes / latest 0",
    change: "observe",
    riskNote: "Not a trade cue",
    evidenceHref: "/evidence?q=BTC",
    nextAction: "View Evidence",
    links: {
      evidence: "/evidence?q=BTC#doc-summary-p2d-r1",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#provider-history-chart",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
];

/** Legacy chip labels kept for strip; guided prompts live in productUx.ts */
export const COPILOT_PROMPTS: CopilotPrompt[] = [
  {
    id: "hold",
    label: "為什麼 HOLD？",
    prompt: "Why are we in HOLD? Explain wait-for-ETH, no trading action.",
  },
  {
    id: "419",
    label: "什麼卡住 4.19？",
    prompt: "What blocks Stage 4.19? Actual BTC+ETH graduation required.",
  },
  {
    id: "first",
    label: "先看什麼？",
    prompt: "What should I check first under HOLD?",
  },
  {
    id: "eth",
    label: "解釋 ETH Gate",
    prompt: "Explain ETH watch gate in plain language.",
  },
  {
    id: "evidence",
    label: "證據摘要",
    prompt: "Summarize latest evidence trail P2D→P2H.",
  },
];

export const SAFETY_INVARIANTS: SafetyInvariant[] = [
  { id: "orders", label: "No order", value: "false", ok: true },
  { id: "mock", label: "No mock", value: "false", ok: true },
  { id: "arm", label: "No ARM", value: "false", ok: true },
  { id: "production", label: "No production", value: "false", ok: true },
  { id: "btc_auto", label: "No btc-auto", value: "false", ok: true },
  { id: "billing", label: "No billing", value: "false", ok: true },
  { id: "accounts", label: "No accounts", value: "false", ok: true },
  { id: "apikeys", label: "No API keys", value: "false", ok: true },
  { id: "s419", label: "Stage 4.19", value: "blocked", ok: true },
  { id: "rg", label: "Risk Governor", value: "unchanged", ok: true },
  { id: "mae", label: "MAE cap", value: "unchanged", ok: true },
  { id: "routing", label: "Routing permanent", value: "false", ok: true },
];

export const PROVIDER_INTEL_FACTS: ProviderIntelFact[] = [
  { id: "gvc", label: "Groq vs Cerebras", value: "history reviewed · shadow era" },
  { id: "cerebras", label: "BTC Cerebras-first", value: "experiment only" },
  { id: "shadow", label: "Shadow for graduation", value: "not used" },
  { id: "perm", label: "Permanent routing change", value: "false" },
  { id: "ops", label: "Operator approval", value: "required for future changes" },
  { id: "gate", label: "Future routing changes", value: "require gate" },
];

export const VALIDATION_FACTS: ValidationFact[] = [
  {
    id: "btc_prior",
    label: "BTC prior actual graduation",
    value: "evidence exists",
    tone: "pass",
  },
  {
    id: "btc_latest",
    label: "Latest BTC regression graduation",
    value: "0",
    tone: "wait",
  },
  {
    id: "eth_prompt",
    label: "ETH prompt repair",
    value: "done",
    tone: "pass",
  },
  {
    id: "eth_runtime",
    label: "ETH runtime validation",
    value: "pending",
    tone: "wait",
  },
  {
    id: "eth_watch",
    label: "ETH watch condition",
    value: "not reappeared",
    tone: "hold",
  },
  {
    id: "short_reg",
    label: "next short regression allowed now",
    value: "false",
    tone: "hold",
  },
  {
    id: "dossier",
    label: "Stage 4.19 dossier allowed",
    value: "false",
    tone: "blocked",
  },
];

export const SYSTEM_GATE_STRIP = {
  backendState: "HOLD",
  releaseCheckpoint: "P2H",
  stage419: "BLOCKED",
  nextAction: "Wait for ETH watch conditions",
  thirtyMNow: false,
  sixtyM: false,
  autoRun: false,
} as const;
