/**
 * MVP-22 / MVP-22A research signal fixtures (NOT live market prices).
 * Live lastPrice comes from BYBIT_MAINNET_LINEAR via LiveMarketFeed.
 * READ ONLY · NOT INVESTMENT ADVICE · no order controls
 */

import type { SignalReference } from "../market/types";

export type WatchRow = {
  symbol: string;
  /** @deprecated Prefer signalReferencePrice — kept for non-live symbols like PEPE */
  price: string;
  signalReferencePrice: number | null;
  aiScore: string;
  changePct: number | null;
  status: "HOLD" | "WAIT" | "MONITOR";
  recommendation: "LONG" | "SHORT" | "NEUTRAL" | "HOLD" | "WAIT" | "MONITOR";
  confidence: string;
  timeframe: string;
  analysisTimestamp: number;
  invalidationLevel: string;
  next: "View Evidence" | "View Gate";
  nextTo: string;
};

export type DecisionAlert = {
  id: string;
  zone: "Confirmed Breakout" | "Waiting for Breakout" | "Gate Warning" | "Provider Divergence";
  symbol: string;
  alertType: string;
  meaning: string;
  triggerPrice: number | null;
  triggerTime: number | null;
  valid: boolean;
  action: "View Evidence" | "View Gate" | "View Risk" | "View Provider" | "View Checklist";
  actionTo: string;
};

/** Static research signal references — never overwrite with live lastPrice. */
export const SIGNAL_REFERENCES: Record<string, SignalReference> = {
  BTC: {
    symbol: "BTCUSDT",
    displaySymbol: "BTC",
    referencePrice: 64943,
    analysisTimestamp: Date.parse("2026-07-15T00:00:00Z"),
    timeframe: "research",
    recommendation: "HOLD",
    confidence: "Prior evidence",
    invalidationLevel: "Gate / confirmation incomplete",
    aiScore: "Prior evidence",
  },
  ETH: {
    symbol: "ETHUSDT",
    displaySymbol: "ETH",
    referencePrice: 1882,
    analysisTimestamp: Date.parse("2026-07-15T00:00:00Z"),
    timeframe: "research",
    recommendation: "WAIT",
    confidence: "Watch gate not ready",
    invalidationLevel: "ETH watch not reappeared",
    aiScore: "Watch gate not ready",
  },
  SOL: {
    symbol: "SOLUSDT",
    displaySymbol: "SOL",
    referencePrice: 148.2,
    analysisTimestamp: Date.parse("2026-07-15T00:00:00Z"),
    timeframe: "research",
    recommendation: "MONITOR",
    confidence: "Monitor",
    invalidationLevel: "No active thesis",
    aiScore: "Monitor",
  },
  PEPE: {
    symbol: "PEPEUSDT",
    displaySymbol: "PEPE",
    referencePrice: 0.000012,
    analysisTimestamp: Date.parse("2026-07-15T00:00:00Z"),
    timeframe: "research",
    recommendation: "MONITOR",
    confidence: "Monitor",
    invalidationLevel: "No live feed",
    aiScore: "Monitor",
  },
};

export const LONG_WATCHLIST: WatchRow[] = [
  {
    symbol: "BTC",
    price: "64,943",
    signalReferencePrice: SIGNAL_REFERENCES.BTC.referencePrice,
    aiScore: SIGNAL_REFERENCES.BTC.aiScore!,
    changePct: null,
    status: "HOLD",
    recommendation: "HOLD",
    confidence: "Prior evidence",
    timeframe: "research",
    analysisTimestamp: SIGNAL_REFERENCES.BTC.analysisTimestamp,
    invalidationLevel: SIGNAL_REFERENCES.BTC.invalidationLevel!,
    next: "View Evidence",
    nextTo: "/evidence?q=BTC",
  },
  {
    symbol: "ETH",
    price: "1,882",
    signalReferencePrice: SIGNAL_REFERENCES.ETH.referencePrice,
    aiScore: SIGNAL_REFERENCES.ETH.aiScore!,
    changePct: null,
    status: "WAIT",
    recommendation: "WAIT",
    confidence: "Watch gate not ready",
    timeframe: "research",
    analysisTimestamp: SIGNAL_REFERENCES.ETH.analysisTimestamp,
    invalidationLevel: SIGNAL_REFERENCES.ETH.invalidationLevel!,
    next: "View Gate",
    nextTo: "/overview#checklist-eth-watch-reappearance",
  },
  {
    symbol: "SOL",
    price: "148.2",
    signalReferencePrice: SIGNAL_REFERENCES.SOL.referencePrice,
    aiScore: SIGNAL_REFERENCES.SOL.aiScore!,
    changePct: null,
    status: "MONITOR",
    recommendation: "MONITOR",
    confidence: "Monitor",
    timeframe: "research",
    analysisTimestamp: SIGNAL_REFERENCES.SOL.analysisTimestamp,
    invalidationLevel: SIGNAL_REFERENCES.SOL.invalidationLevel!,
    next: "View Evidence",
    nextTo: "/evidence#doc-summaries",
  },
  {
    symbol: "PEPE",
    price: "0.000012",
    signalReferencePrice: SIGNAL_REFERENCES.PEPE.referencePrice,
    aiScore: "Monitor",
    changePct: null,
    status: "MONITOR",
    recommendation: "MONITOR",
    confidence: "Monitor",
    timeframe: "research",
    analysisTimestamp: SIGNAL_REFERENCES.PEPE.analysisTimestamp,
    invalidationLevel: "No live feed",
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
    triggerPrice: SIGNAL_REFERENCES.ETH.referencePrice,
    triggerTime: SIGNAL_REFERENCES.ETH.analysisTimestamp,
    valid: true,
    action: "View Gate",
    actionTo: "/overview#checklist-eth-watch-reappearance",
  },
  {
    id: "s419",
    zone: "Gate Warning",
    symbol: "4.19",
    alertType: "Blocked",
    meaning: "Needs BTC + ETH actual graduation.",
    triggerPrice: null,
    triggerTime: null,
    valid: true,
    action: "View Checklist",
    actionTo: "/overview#checklist-stage-419-dossier",
  },
  {
    id: "btc-prior",
    zone: "Waiting for Breakout",
    symbol: "BTC",
    alertType: "Prior only",
    meaning: "Prior evidence only; not a live breakout.",
    triggerPrice: SIGNAL_REFERENCES.BTC.referencePrice,
    triggerTime: SIGNAL_REFERENCES.BTC.analysisTimestamp,
    valid: true,
    action: "View Evidence",
    actionTo: "/evidence?q=BTC",
  },
  {
    id: "provider",
    zone: "Provider Divergence",
    symbol: "BTC",
    alertType: "Research",
    meaning: "Provider history is research-only.",
    triggerPrice: SIGNAL_REFERENCES.BTC.referencePrice,
    triggerTime: SIGNAL_REFERENCES.BTC.analysisTimestamp,
    valid: true,
    action: "View Provider",
    actionTo: "/provider-shadow#provider-explain",
  },
  {
    id: "confirmed-none",
    zone: "Confirmed Breakout",
    symbol: "—",
    alertType: "None",
    meaning: "No confirmed breakout.",
    triggerPrice: null,
    triggerTime: null,
    valid: false,
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

/** Legacy name kept so older imports do not break — NOT live prices. */
export const TICKER_QUOTES = [
  { symbol: "BTC", price: "signal-ref-only", changePct: 0 },
  { symbol: "ETH", price: "signal-ref-only", changePct: 0 },
  { symbol: "SOL", price: "signal-ref-only", changePct: 0 },
];
