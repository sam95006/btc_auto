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
  action: "View Evidence" | "View Gate" | "View Risk" | "View Provider" | "View Checklist";
  actionTo: string;
};

export const TICKER_QUOTES: TickerQuote[] = [
  { symbol: "BTC", price: "64,943", changePct: 3.7 },
  { symbol: "ETH", price: "1,882", changePct: 5.5 },
  { symbol: "SOL", price: "148.2", changePct: 1.1 },
];

export const LONG_WATCHLIST: WatchRow[] = [
  {
    symbol: "BTC",
    price: "64,943",
    aiScore: "Prior evidence",
    changePct: 3.7,
    status: "HOLD",
    next: "View Evidence",
    nextTo: "/evidence?q=BTC",
  },
  {
    symbol: "ETH",
    price: "1,882",
    aiScore: "Watch gate not ready",
    changePct: 5.5,
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
  lines: ["ETH Gate not ready", "Stage 4.19 blocked", "Backend HOLD"],
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
    symbol: "4.19",
    alertType: "Blocked",
    meaning: "Needs BTC + ETH actual graduation.",
    action: "View Checklist",
    actionTo: "/overview#checklist-stage-419-dossier",
  },
  {
    id: "btc-prior",
    zone: "Waiting for Breakout",
    symbol: "BTC",
    alertType: "Prior only",
    meaning: "Prior evidence only; not a live breakout.",
    action: "View Evidence",
    actionTo: "/evidence?q=BTC",
  },
  {
    id: "provider",
    zone: "Provider Divergence",
    symbol: "BTC",
    alertType: "Research",
    meaning: "Provider history is research-only.",
    action: "View Provider",
    actionTo: "/provider-shadow#provider-explain",
  },
  {
    id: "confirmed-none",
    zone: "Confirmed Breakout",
    symbol: "—",
    alertType: "None",
    meaning: "No confirmed breakout.",
    action: "View Risk",
    actionTo: "/risk-evidence#why-safe",
  },
];

export const FLOATING_AI_PROMPTS = [
  {
    id: "hold",
    label: "Why are we in HOLD?",
    answer: "HOLD — ETH watch not reappeared. Wait only. No Stage 4.19 start.",
  },
  {
    id: "first",
    label: "What should I check first?",
    answer: "ETH Gate → Evidence Start Here → Risk why-safe.",
  },
  {
    id: "eth",
    label: "Explain ETH Gate",
    answer: "ETH has no valid watch/reappearance. Blocks regression and 4.19.",
  },
  {
    id: "evidence",
    label: "Summarize Evidence",
    answer: "Evidence Center holds gate and release docs. Search stays read-only.",
  },
  {
    id: "419",
    label: "Explain Stage 4.19",
    answer: "Blocked until real BTC + ETH graduation. No start control in UI.",
  },
] as const;
