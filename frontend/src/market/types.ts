/**
 * MVP-22A/B Live Market Data types.
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

export type DerivativesFieldStatus = "LIVE" | "DELAYED" | "STALE" | "UNAVAILABLE";

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
  /** Coin quantity (e.g. BTC) */
  openInterest?: number;
  /** USDT notional */
  openInterestValue?: number;
  /** Decimal rate from exchange (e.g. 0.0001 = 0.01%) */
  fundingRate?: number;
  nextFundingTime?: number;
  /** Coin volume 24h */
  volume24h?: number;
  /** USDT turnover 24h */
  turnover24h?: number;
  exchangeTimestamp: number;
  receivedAt: number;
  ageMs: number;
  connectionStatus: MarketConnectionStatus;
};

export type DerivativesMarketContext = {
  symbol: LiveSymbol;
  openInterest?: number;
  openInterestValue?: number;
  openInterestUnit: "COIN";
  openInterestValueUnit: "USDT";
  fundingRate?: number;
  fundingRatePct?: number;
  nextFundingTime?: number;
  volume24h?: number;
  volumeUnit: "COIN";
  turnover24h?: number;
  turnoverUnit: "USDT";
  source: "BYBIT_MAINNET_LINEAR";
  exchangeTimestamp: number;
  receivedAt: number;
  status: DerivativesFieldStatus;
  oiChange1mPct?: number | null;
  oiChange5mPct?: number | null;
  oiChange15mPct?: number | null;
  oiWindow: {
    m1: "ready" | "collecting";
    m5: "ready" | "collecting";
    m15: "ready" | "collecting";
  };
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
