/**
 * MVP-21 product UX copy — plain language for operators.
 * READ ONLY · NOT INVESTMENT ADVICE · no trading controls
 */

export type DecisionCard = {
  id: string;
  title: string;
  value: string;
  detail: string;
  tone: "hold" | "wait" | "blocked" | "pass";
};

export type LookFirstCard = {
  id: string;
  title: string;
  why: string;
  actionLabel: "View Gate" | "View Evidence" | "View Runbook";
  to: string;
};

export type CandidateMeaning = {
  symbol: string;
  status: string;
  meaning: string;
  nextLabel: "View Evidence" | "View Gate" | "Open Risk Card";
  nextTo: string;
};

export type GuidedPrompt = {
  id: string;
  labelZh: string;
  question: string;
  willExplain: string;
  relatedPage: string;
  relatedTo: string;
  answer: string;
};

export type FeatureMapItem = {
  id: string;
  label: string;
  bucket: "completed" | "waiting" | "future";
  note: string;
};

export type WhySafeItem = {
  id: string;
  label: string;
  explanation: string;
};

export type ProviderExplainItem = {
  id: string;
  title: string;
  meaning: string;
};

export const HOLD_HEADLINE =
  "NEXUS is in HOLD. ETH watch conditions have not reappeared. No regression should run now.";

export const DECISION_CARDS: DecisionCard[] = [
  {
    id: "backend",
    title: "Backend State",
    value: "HOLD",
    detail: "Waiting for ETH watch condition to reappear.",
    tone: "hold",
  },
  {
    id: "market",
    title: "Market Readiness",
    value: "ETH not ready",
    detail: "BTC: prior evidence exists · ETH: not ready · SOL / PEPE: waiting.",
    tone: "wait",
  },
  {
    id: "regression",
    title: "Regression Gate",
    value: "NO now",
    detail: "Short regression: NO · 60m: NO · Stage 4.19: BLOCKED.",
    tone: "blocked",
  },
  {
    id: "next",
    title: "Next Action",
    value: "Wait",
    detail: "Watch ETH gate · Review Evidence · No trading action.",
    tone: "hold",
  },
];

export const LOOK_FIRST_CARDS: LookFirstCard[] = [
  {
    id: "eth-gate",
    title: "ETH Watch Gate",
    why: "ETH is the missing graduation side before any next regression.",
    actionLabel: "View Gate",
    to: "/overview#checklist-eth-watch-reappearance",
  },
  {
    id: "s419",
    title: "Stage 4.19 Blocker",
    why: "Stage 4.19 cannot start without actual BTC + ETH graduation.",
    actionLabel: "View Gate",
    to: "/overview#checklist-stage-419-dossier",
  },
  {
    id: "evidence",
    title: "Evidence Center",
    why: "Every HOLD decision must stay traceable to a report or runbook.",
    actionLabel: "View Evidence",
    to: "/evidence#start-here",
  },
];

export const CANDIDATE_MEANINGS: CandidateMeaning[] = [
  {
    symbol: "BTC",
    status: "Evidence exists; latest regression not confirmed",
    meaning: "BTC is not the current blocker.",
    nextLabel: "View Evidence",
    nextTo: "/evidence?q=BTC#doc-summary-p2d-r1",
  },
  {
    symbol: "ETH",
    status: "Waiting for watch condition",
    meaning: "ETH is the blocker before the next regression.",
    nextLabel: "View Gate",
    nextTo: "/overview#checklist-eth-watch-reappearance",
  },
  {
    symbol: "SOL",
    status: "Monitoring only",
    meaning: "Not part of the current graduation gate.",
    nextLabel: "Open Risk Card",
    nextTo: "/risk-evidence#why-safe",
  },
  {
    symbol: "PEPE",
    status: "Monitoring only",
    meaning: "Not part of the current graduation gate.",
    nextLabel: "View Evidence",
    nextTo: "/evidence#doc-summaries",
  },
];

export const GUIDED_PROMPTS: GuidedPrompt[] = [
  {
    id: "hold",
    labelZh: "為什麼 HOLD？",
    question: "Why are we in HOLD?",
    willExplain: "Backend pause reason and what must change first.",
    relatedPage: "Overview · ETH Gate",
    relatedTo: "/overview#checklist-eth-watch-reappearance",
    answer:
      "HOLD because ETH watch conditions have not reappeared. No short regression, no 60m, and no Stage 4.19 start. Next = wait and read Evidence.",
  },
  {
    id: "419",
    labelZh: "什麼卡住 4.19？",
    question: "What blocks Stage 4.19?",
    willExplain: "Graduation requirements and dossier blockers.",
    relatedPage: "Stage 4.19 checklist",
    relatedTo: "/overview#checklist-stage-419-dossier",
    answer:
      "Stage 4.19 is BLOCKED until actual non-shadow BTC and ETH graduation exist. Shadow history does not count. There is no start button.",
  },
  {
    id: "first",
    labelZh: "先看什麼？",
    question: "What should I check first?",
    willExplain: "Recommended reading order for this HOLD day.",
    relatedPage: "Look first",
    relatedTo: "/overview#look-first",
    answer:
      "Check ETH Watch Gate first, then Stage 4.19 dossier checklist, then Evidence Center for traceable reports.",
  },
  {
    id: "eth",
    labelZh: "解釋 ETH Gate",
    question: "Explain ETH watch gate.",
    willExplain: "Why ETH blocks regression under HOLD.",
    relatedPage: "ETH checklist",
    relatedTo: "/overview#checklist-eth-watch-reappearance",
    answer:
      "ETH has no valid watch / reappearance condition. Until that returns, regression stays false and operators only navigate Gate / Evidence.",
  },
  {
    id: "evidence",
    labelZh: "證據摘要",
    question: "Summarize latest evidence.",
    willExplain: "P2D → P2H evidence trail in plain language.",
    relatedPage: "Evidence Center",
    relatedTo: "/evidence#start-here",
    answer:
      "Evidence Center holds gate, regression, and release docs. Use Start Here, then Gate Reports, then Release / Runbook. Sanitized metadata only — READ ONLY.",
  },
];

export const FEATURE_MAP: FeatureMapItem[] = [
  {
    id: "mi",
    label: "Market Intelligence layout",
    bucket: "completed",
    note: "MVP-17–20 live on Zeabur",
  },
  {
    id: "evidence-filter",
    label: "Evidence search / filter",
    bucket: "completed",
    note: "URL state + presets",
  },
  {
    id: "report-viewer",
    label: "Report viewer",
    bucket: "completed",
    note: "Sanitized summaries",
  },
  {
    id: "runbook",
    label: "Runbook viewer",
    bucket: "completed",
    note: "P2H-OPS deep links",
  },
  {
    id: "provider",
    label: "Provider Intelligence",
    bucket: "completed",
    note: "Charts + posture (read-only)",
  },
  {
    id: "risk",
    label: "Risk Center",
    bucket: "completed",
    note: "Safety invariants",
  },
  {
    id: "release",
    label: "Release health badge",
    bucket: "completed",
    note: "P2H checkpoint",
  },
  {
    id: "presets",
    label: "Workspace presets / pins",
    bucket: "completed",
    note: "MVP-19 URL-only",
  },
  {
    id: "eth-watch",
    label: "ETH watch reappearance",
    bucket: "waiting",
    note: "Gate false under HOLD",
  },
  {
    id: "prompt-runtime",
    label: "Runtime validation of prompt repair",
    bucket: "waiting",
    note: "No 30m / 60m while HOLD",
  },
  {
    id: "dossier",
    label: "Stage 4.19 dossier",
    bucket: "waiting",
    note: "Blocked until BTC+ETH graduation",
  },
  {
    id: "saas",
    label: "Public SaaS",
    bucket: "future",
    note: "NOT IMPLEMENTED",
  },
  {
    id: "academy",
    label: "Academy",
    bucket: "future",
    note: "NOT IMPLEMENTED",
  },
  {
    id: "membership",
    label: "Membership",
    bucket: "future",
    note: "NOT IMPLEMENTED",
  },
  {
    id: "billing",
    label: "Billing",
    bucket: "future",
    note: "NOT IMPLEMENTED",
  },
  {
    id: "accounts",
    label: "Customer accounts",
    bucket: "future",
    note: "NOT IMPLEMENTED",
  },
  {
    id: "apikeys",
    label: "API key collection",
    bucket: "future",
    note: "NOT IMPLEMENTED",
  },
  {
    id: "live-trading",
    label: "Live trading",
    bucket: "future",
    note: "NOT IMPLEMENTED",
  },
];

export const WHY_SAFE_ITEMS: WhySafeItem[] = [
  {
    id: "orders",
    label: "No orders",
    explanation: "This console never submits exchange orders.",
  },
  {
    id: "live",
    label: "No live trading",
    explanation: "HOLD keeps the product in research / observation mode.",
  },
  {
    id: "keys",
    label: "No API keys",
    explanation: "Operators do not paste exchange secrets into this UI.",
  },
  {
    id: "arm",
    label: "No ARM",
    explanation: "No arm / disarm controls are exposed here.",
  },
  {
    id: "production",
    label: "No production mode",
    explanation: "Promotion to production trading stays blocked.",
  },
  {
    id: "s419",
    label: "Stage 4.19 blocked",
    explanation: "Graduation dossier incomplete; there is no start button.",
  },
  {
    id: "readonly",
    label: "Read-only navigation only",
    explanation: "Actions open Evidence, Gate, Risk, Provider, or Runbook.",
  },
];

export const PROVIDER_EXPLAIN: ProviderExplainItem[] = [
  {
    id: "gvc",
    title: "What is Groq vs Cerebras history?",
    meaning:
      "A research timeline of provider outputs used for review, not for live routing changes.",
  },
  {
    id: "cerebras",
    title: "Why is BTC Cerebras-first only an experiment?",
    meaning:
      "It was a bounded research posture. It does not authorize permanent provider routing.",
  },
  {
    id: "perm",
    title: "Why permanent routing = false?",
    meaning:
      "Routing editors and auto-promotion are disabled. Future changes need operator approval.",
  },
  {
    id: "shadow",
    title: "Why shadow cannot count as graduation?",
    meaning:
      "Shadow helps learning review. Graduation still needs actual non-shadow evidence on both BTC and ETH.",
  },
];

export type EvidenceZoneId = "start-here" | "gate-reports" | "evidence-regression" | "release-runbook";

export const EVIDENCE_ZONES: {
  id: EvidenceZoneId;
  label: string;
  blurb: string;
}[] = [
  {
    id: "start-here",
    label: "Start Here",
    blurb: "Top unresolved gates and recommended reports.",
  },
  {
    id: "gate-reports",
    label: "Gate Reports",
    blurb: "P2F / P2G / P2H gate-focused summaries.",
  },
  {
    id: "evidence-regression",
    label: "Evidence & Regression",
    blurb: "P2D / P2D-R1 / P2E regression evidence.",
  },
  {
    id: "release-runbook",
    label: "Release / Runbook",
    blurb: "P2H-QA / P2H-REL / P2H-OPS release docs.",
  },
];
