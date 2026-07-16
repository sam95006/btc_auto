import type { LiveMarketPrice, LiveSymbol } from "./types";
import { LIVE_SYMBOLS } from "./types";
import { ageToStatus } from "./freshness";

type RestTickerRow = {
  symbol: string;
  lastPrice: number;
  markPrice?: number | null;
  indexPrice?: number | null;
  bidPrice?: number | null;
  askPrice?: number | null;
  change24hPct?: number | null;
  openInterest?: number | null;
  openInterestValue?: number | null;
  fundingRate?: number | null;
  nextFundingTime?: number | null;
  volume24h?: number | null;
  turnover24h?: number | null;
  exchangeTimestamp?: number | null;
};

type RestResponse = {
  ok: boolean;
  tickers?: RestTickerRow[];
  error?: string;
};

function opt(n: number | null | undefined): number | undefined {
  return n == null || !Number.isFinite(n) ? undefined : n;
}

/** Bootstrap via NEXUS read-only proxy → Bybit Mainnet public REST. */
export async function fetchMainnetRestSnapshot(
  symbols: LiveSymbol[] = LIVE_SYMBOLS,
): Promise<LiveMarketPrice[]> {
  const qs = new URLSearchParams({
    category: "linear",
    symbols: symbols.join(","),
  });
  const res = await fetch(`/api/market/tickers?${qs.toString()}`, {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`rest_http_${res.status}`);
  }
  const body = (await res.json()) as RestResponse;
  if (!body.ok || !body.tickers?.length) {
    throw new Error(body.error || "rest_empty");
  }
  const now = Date.now();
  const out: LiveMarketPrice[] = [];
  for (const row of body.tickers) {
    if (!symbols.includes(row.symbol as LiveSymbol)) continue;
    const receivedAt = now;
    const exchangeTimestamp = row.exchangeTimestamp || receivedAt;
    const ageMs = Math.max(0, receivedAt - exchangeTimestamp);
    out.push({
      symbol: row.symbol as LiveSymbol,
      source: "BYBIT_MAINNET_LINEAR",
      priceType: "LAST",
      lastPrice: row.lastPrice,
      markPrice: opt(row.markPrice),
      indexPrice: opt(row.indexPrice),
      bidPrice: opt(row.bidPrice),
      askPrice: opt(row.askPrice),
      change24hPct: opt(row.change24hPct),
      openInterest: opt(row.openInterest),
      openInterestValue: opt(row.openInterestValue),
      fundingRate: opt(row.fundingRate),
      nextFundingTime: opt(row.nextFundingTime),
      volume24h: opt(row.volume24h),
      turnover24h: opt(row.turnover24h),
      exchangeTimestamp,
      receivedAt,
      ageMs,
      connectionStatus: ageToStatus(ageMs, { restFallback: true }),
    });
  }
  if (!out.length) throw new Error("rest_no_allowed_symbols");
  return out;
}
