/**
 * MVP-22A Live Market Data types.
 * Display only · BYBIT MAINNET PUBLIC · no private API · no orders
 */

export type LiveSymbol = "BTCUSDT" | "ETHUSDT" | "SOLUSDT";

export type MarketConnectionStatus =
  | "LIVE"
  | "DELAYED"
  | "STALE"
  | "RECONNECTING"
  | "REST_FALLBACK"
  | "DISCONNECTED";

export type LiveMarketPrice = {
  symbol: LiveSymbol;
  source: "BYBIT_MAINNET_LINEAR";
  priceType: "LAST";
  lastPrice: number;
  markPrice?: number;
  indexPrice?: number;
  bidPrice?: number;
  askPrice?: number;
  change24hPct?: number;
  exchangeTimestamp: number;
  receivedAt: number;
  ageMs: number;
  connectionStatus: MarketConnectionStatus;
};

export type SignalReference = {
  symbol: string;
  displaySymbol: string;
  referencePrice: number;
  analysisTimestamp: number;
  timeframe?: string;
  recommendation?: "LONG" | "SHORT" | "NEUTRAL" | "HOLD" | "WAIT" | "MONITOR";
  confidence?: string;
  invalidationLevel?: string;
  aiScore?: string;
};

export const LIVE_SYMBOLS: LiveSymbol[] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

export const DISPLAY_TO_USDT: Record<string, LiveSymbol | undefined> = {
  BTC: "BTCUSDT",
  ETH: "ETHUSDT",
  SOL: "SOLUSDT",
  BTCUSDT: "BTCUSDT",
  ETHUSDT: "ETHUSDT",
  SOLUSDT: "SOLUSDT",
};

export function shortSymbol(sym: LiveSymbol): "BTC" | "ETH" | "SOL" {
  if (sym === "BTCUSDT") return "BTC";
  if (sym === "ETHUSDT") return "ETH";
  return "SOL";
}
