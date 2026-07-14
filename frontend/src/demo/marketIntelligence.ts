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
  evidenceHref: string;
  links: {
    evidence: string;
    gate: string;
    provider: string;
    risk: string;
  };
};

export type AnomalyRow = {
  id: string;
  symbol: string;
  category: "bullish" | "bearish" | "risk" | "provider" | "gate";
  anomalyType: string;
  firstAlert: string;
  latestValue: string;
  change: string;
  riskNote: string;
  evidenceHref: string;
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
    stance: "HOLD / prior evidence",
    latestIntent: "NONE (latest regen)",
    validWatchCount: 0,
    graduationStatus: "prior exists · latest=0",
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
    stance: "wait for watch",
    latestIntent: "NONE",
    validWatchCount: 0,
    graduationStatus: "0 · repair pending runtime",
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
    stance: "waiting / skip",
    latestIntent: "SKIP",
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
    stance: "waiting / skip",
    latestIntent: "SKIP",
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
    symbol: "SOL",
    provider: "demo",
    intent: "SKIP",
    direction: "NONE",
    confidence: null,
    trigger: "—",
    gateStatus: "HOLD",
    status: "hard_skip",
    evidenceHref: "/risk-evidence",
    links: {
      evidence: "/evidence#doc-summaries",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#provider-routing-posture",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
];

export const ANOMALY_ROWS: AnomalyRow[] = [
  {
    id: "a1",
    symbol: "BTC",
    category: "provider",
    anomalyType: "Provider divergence history",
    firstAlert: "P1 shadow era",
    latestValue: "permanent routing=false",
    change: "experiment only",
    riskNote: "Shadow not used for graduation",
    evidenceHref: "/provider-shadow#btc-cerebras-first",
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
    firstAlert: "P2D-R1 / P2F",
    latestValue: "vw=0",
    change: "not reappeared",
    riskNote: "Next = wait · no 60m",
    evidenceHref: "/overview#unresolved-gate",
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
    firstAlert: "product gate",
    latestValue: "blocked",
    change: "unchanged",
    riskNote: "Needs actual BTC+ETH graduation",
    evidenceHref: "/overview#checklist-stage-419-dossier",
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
    category: "risk",
    anomalyType: "No 60m recommended",
    firstAlert: "P2G / P2H",
    latestValue: "60m=false",
    change: "HOLD",
    riskNote: "Auto-run=false",
    evidenceHref: "/overview#gate-checklist",
    links: {
      evidence: "/evidence?q=HOLD",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#provider-routing-posture",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
  {
    id: "a5",
    symbol: "SYS",
    category: "risk",
    anomalyType: "Routing permanent=false",
    firstAlert: "P1C / P2G",
    latestValue: "false",
    change: "policy hold",
    riskNote: "Operator approval required",
    evidenceHref: "/provider-shadow#provider-routing-posture",
    links: {
      evidence: "/evidence?category=routing",
      gate: "/overview#gate-checklist",
      provider: "/provider-shadow#provider-routing-posture",
      risk: "/risk-evidence#checklist-safety-invariants",
    },
  },
];

export const COPILOT_PROMPTS: CopilotPrompt[] = [
  {
    id: "page",
    label: "問目前頁",
    prompt: "Summarize this Market Command page under HOLD (sanitized, no orders).",
  },
  {
    id: "risk",
    label: "找風險",
    prompt: "List top risk / gate blockers: ETH watch, Stage 4.19, no auto-run.",
  },
  {
    id: "opp",
    label: "找機會",
    prompt: "What candidates exist under Waiting/Blocked? Do not suggest execution.",
  },
  {
    id: "brief",
    label: "今日簡報",
    prompt: "Generate a HOLD-day brief: wait for ETH watch, Stage 4.19 blocked.",
  },
  {
    id: "evidence",
    label: "解釋 Evidence",
    prompt: "Explain P2D→P2H-REL doc summaries and next action = wait.",
  },
  {
    id: "419",
    label: "解釋 Stage 4.19 blocked",
    prompt: "Why is Stage 4.19 blocked? Actual non-shadow BTC+ETH required.",
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
