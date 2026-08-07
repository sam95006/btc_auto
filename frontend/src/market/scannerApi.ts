/** NEXUS Market Scanner client — read-only snapshot APIs (Phase 1). */

export type CandidateSide = "LONG" | "SHORT" | "NEUTRAL";
export type CandidateStage =
  | "WATCHING"
  | "BUILDING"
  | "AWAITING_CONFIRMATION"
  | "CONFIRMED"
  | "OVEREXTENDED"
  | "COOLING"
  | "EXPIRED"
  | "INSUFFICIENT_DATA";

export type MarketCandidate = {
  id: string;
  symbol: string;
  side: CandidateSide;
  stage: CandidateStage;
  opportunityScore: number;
  confirmationScore: number;
  riskScore: number;
  /** Bybit instrument symbolType when present (stock/commodity = non-crypto). */
  symbolType?: string | null;
  assetDisposition?: string | null;
  currentPrice?: number;
  priceChange1mPct?: number | null;
  priceChange5mPct?: number | null;
  priceChange15mPct?: number | null;
  oiChange1mPct?: number | null;
  oiChange5mPct?: number | null;
  oiChange15mPct?: number | null;
  fundingRate?: number | null;
  turnoverPace?: number;
  spreadBps?: number | null;
  openInterestValue?: number;
  change24hPct?: number;
  markPrice?: number | null;
  indexPrice?: number | null;
  reasons: string[];
  conflicts: string[];
  invalidationContext?: string;
  rank?: number | null;
  previousRank?: number | null;
  rankDelta?: number | null;
  firstSeenAt: number;
  lastUpdatedAt: number;
  freshness: string;
  source: string;
  researchOnly: true;
  scoreBreakdown?: {
    opportunity: [string, number][];
    confirmation: [string, number][];
    risk: [string, number][];
  };
  collecting?: boolean;
};

export type ScannerStatus = {
  ok: boolean;
  freshness?: string;
  symbolCount?: number;
  symbolLimit?: number;
  longCandidates?: number;
  shortCandidates?: number;
  confirmedCandidates?: number;
  highRiskCandidates?: number;
  breadth?: { rising: number; falling: number; neutral: number; insufficient: number };
  /** Exchange/sector listing breadth — not the same as symbolCount. */
  breadthMarketCount?: number;
  lastCycleAt?: number;
  generatedAt?: number;
  lastError?: string | null;
  snapshotIntervalSec?: number;
  researchOnly?: boolean;
  private_api?: boolean;
  trading_integration?: boolean;
  wsConnected?: boolean;
  transport?: string;
  source?: string;
};

export type ScannerCharts = {
  ok: boolean;
  breadth: { rising: number; falling: number; neutral: number; insufficient: number };
  turnoverTop10: { symbol: string; turnover24h?: number; change24hPct?: number }[];
  priceOiQuadrant: {
    symbol: string;
    side: string;
    priceChange5mPct: number;
    oiChange5mPct: number;
    stage?: string;
  }[];
  quadrantNote?: string;
  generatedAt?: number;
};

export type ScannerEvent = {
  id: string;
  type: string;
  symbol: string;
  side?: string;
  stage?: string;
  rank?: number | null;
  explanation: string;
  timestamp: number;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`scanner_http_${res.status}`);
  return (await res.json()) as T;
}

export function fetchScannerStatus() {
  return getJson<ScannerStatus>("/api/market/scanner/status");
}

export function fetchScannerCandidates(side?: "LONG" | "SHORT", limit = 40) {
  const qs = new URLSearchParams();
  if (side) qs.set("side", side);
  qs.set("limit", String(limit));
  return getJson<{ ok: boolean; candidates: MarketCandidate[]; freshness?: string }>(
    `/api/market/scanner/candidates?${qs}`,
  );
}

export function fetchScannerEvents(limit = 20) {
  return getJson<{ ok: boolean; events: ScannerEvent[] }>(
    `/api/market/scanner/events?limit=${limit}`,
  );
}

export function fetchScannerCharts() {
  return getJson<ScannerCharts>("/api/market/scanner/charts");
}

export function fetchScannerSymbol(symbol: string) {
  return getJson<{
    ok: boolean;
    symbol: string;
    snapshot?: Record<string, unknown>;
    candidate?: MarketCandidate | null;
    sparkline?: { t?: number; price?: number; oi?: number }[];
    historyPoints?: number;
    error?: string;
  }>(`/api/market/scanner/symbol/${encodeURIComponent(symbol)}`);
}

export function fetchScannerUniverse() {
  return getJson<{
    ok: boolean;
    symbols?: string[];
    eligible_after_limit?: number;
    total_tickers_seen?: number;
    excluded_count?: number;
  }>("/api/market/scanner/universe");
}

export const STAGE_LABEL_ZH: Record<CandidateStage, string> = {
  WATCHING: "觀察中",
  BUILDING: "結構形成中",
  AWAITING_CONFIRMATION: "等待確認",
  CONFIRMED: "條件已確認",
  OVEREXTENDED: "過熱勿追",
  COOLING: "條件減弱",
  EXPIRED: "條件已失效",
  INSUFFICIENT_DATA: "資料累積中",
};

/** Soften technical jargon in Simple View reason lines. */
export function plainReason(text: string, simple: boolean): string {
  if (!simple || !text) return text;
  return text
    .replace(/\bOI\b/gi, "持倉")
    .replace(/open interest/gi, "持倉")
    .replace(/funding/gi, "資金費率擁擠")
    .replace(/turnover/gi, "交易活躍度")
    .replace(/overextended/gi, "過熱");
}

export function sideLabelZh(side: CandidateSide) {
  if (side === "LONG") return "做多機會";
  if (side === "SHORT") return "做空機會";
  return "中性";
}
