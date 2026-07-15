/**
 * MVP-22 simplified market dashboard demo fixtures.
 * READ ONLY · NOT INVESTMENT ADVICE · DEMO DATA · no order controls
 */

export type TickerQuote = {
  symbol: string;
  price: string;
  changePct: number;
};

export type WatchRow = {
  symbol: string;
  price: string;
  aiScore: string;
  changePct: number | null;
  status: "HOLD" | "WAIT" | "MONITOR";
  next: "View Evidence" | "View Gate";
  nextTo: string;
};

export type DecisionAlert = {
  id: string;
  zone: "Confirmed Breakout" | "Waiting for Breakout" | "Gate Warning" | "Provider Divergence";
  symbol: string;
  alertType: string;
  meaning: string;
  action: "View Evidence" | "View Gate" | "View Risk" | "View Provider";
  actionTo: string;
};

export const TICKER_QUOTES: TickerQuote[] = [
  { symbol: "BTC", price: "67,420", changePct: 0.42 },
  { symbol: "ETH", price: "3,218", changePct: -0.38 },
];

export const LONG_WATCHLIST: WatchRow[] = [
  {
    symbol: "BTC",
    price: "67,420",
    aiScore: "Prior evidence",
    changePct: 0.42,
    status: "HOLD",
    next: "View Evidence",
    nextTo: "/evidence?q=BTC",
  },
  {
    symbol: "ETH",
    price: "3,218",
    aiScore: "Waiting",
    changePct: -0.38,
    status: "WAIT",
    next: "View Gate",
    nextTo: "/overview#checklist-eth-watch-reappearance",
  },
  {
    symbol: "SOL",
    price: "148.2",
    aiScore: "Monitor",
    changePct: 1.1,
    status: "MONITOR",
    next: "View Evidence",
    nextTo: "/evidence#doc-summaries",
  },
  {
    symbol: "PEPE",
    price: "0.000012",
    aiScore: "Monitor",
    changePct: -2.4,
    status: "MONITOR",
    next: "View Evidence",
    nextTo: "/risk-evidence#why-safe",
  },
];

export const SHORT_WATCHLIST: WatchRow[] = [];

export const MARKET_READINESS = {
  score: 48.1,
  label: "Neutral / Waiting" as const,
  lines: ["HOLD", "ETH Gate not ready", "Stage 4.19 blocked"],
};

export const DECISION_ALERTS: DecisionAlert[] = [
  {
    id: "eth-gate",
    zone: "Gate Warning",
    symbol: "ETH",
    alertType: "Gate Waiting",
    meaning: "ETH watch condition has not reappeared.",
    action: "View Gate",
    actionTo: "/overview#checklist-eth-watch-reappearance",
  },
  {
    id: "s419",
    zone: "Gate Warning",
    symbol: "SYS",
    alertType: "Blocked",
    meaning: "Needs BTC + ETH actual graduation.",
    action: "View Gate",
    actionTo: "/overview#checklist-stage-419-dossier",
  },
  {
    id: "btc-prior",
    zone: "Waiting for Breakout",
    symbol: "BTC",
    alertType: "Prior only",
    meaning: "BTC has prior evidence; latest confirmation not current.",
    action: "View Evidence",
    actionTo: "/evidence?q=BTC",
  },
  {
    id: "provider",
    zone: "Provider Divergence",
    symbol: "BTC",
    alertType: "Experiment",
    meaning: "Provider history is research-only; permanent routing stays false.",
    action: "View Provider",
    actionTo: "/provider-shadow#provider-explain",
  },
  {
    id: "confirmed-none",
    zone: "Confirmed Breakout",
    symbol: "—",
    alertType: "None",
    meaning: "No confirmed breakout under HOLD.",
    action: "View Risk",
    actionTo: "/risk-evidence#why-safe",
  },
];

export const FLOATING_AI_PROMPTS = [
  {
    id: "hold",
    label: "Why are we in HOLD?",
    answer:
      "HOLD because ETH watch has not reappeared. No regression, no Stage 4.19 start. Next = wait.",
  },
  {
    id: "first",
    label: "What should I check first?",
    answer: "Open ETH Gate, then Evidence Center Start Here, then Risk why-safe strip.",
  },
  {
    id: "eth",
    label: "Explain ETH Gate",
    answer: "ETH has no valid watch/reappearance. It blocks short regression and Stage 4.19.",
  },
  {
    id: "evidence",
    label: "Summarize Evidence",
    answer: "Evidence Center holds gate, regression, and release docs. Search/filter stay read-only.",
  },
  {
    id: "419",
    label: "Explain Stage 4.19 blocker",
    answer: "Blocked until actual non-shadow BTC + ETH graduation. No start button in UI.",
  },
] as const;
