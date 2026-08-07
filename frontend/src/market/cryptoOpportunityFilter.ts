/**
 * V18.2.7 data-truth — crypto Opportunities membership.
 * Equity/ETF Bybit linear perps (symbolType=stock) must not rank as crypto opportunities.
 * They may appear only as CROSS_ASSET_CONTEXT_ONLY when explicitly labeled.
 */

export const CROSS_ASSET_CONTEXT_ONLY = "CROSS_ASSET_CONTEXT_ONLY" as const;
export const CRYPTO_OPPORTUNITY_ELIGIBLE = "CRYPTO_OPPORTUNITY_ELIGIBLE" as const;

/** Known equity/ETF bases observed on Bybit linear Preview (defense-in-depth; not hardcoded opportunities). */
export const KNOWN_NON_CRYPTO_BASE_SYMBOLS = new Set([
  "SOXL",
  "SPCX",
  "SOXS",
  "AAPL",
  "TSLA",
  "NVDA",
  "AMDSTOCK",
  "AMZN",
  "META",
  "GOOGL",
  "MSFT",
  "ARKK",
  "SPY",
  "QQQ",
]);

const NON_CRYPTO_TYPES = new Set(["stock", "commodity"]);

function baseOf(symbol: string): string {
  const s = symbol.toUpperCase().trim();
  return s.endsWith("USDT") ? s.slice(0, -4) : s;
}

export function isKnownNonCryptoSymbol(symbol: string): boolean {
  return KNOWN_NON_CRYPTO_BASE_SYMBOLS.has(baseOf(symbol));
}

export function isCryptoOpportunitySymbol(
  symbol: string,
  symbolType?: string | null,
): boolean {
  const st = (symbolType || "").trim().toLowerCase();
  if (st && NON_CRYPTO_TYPES.has(st)) return false;
  if (isKnownNonCryptoSymbol(symbol)) return false;
  return true;
}

export type OpportunityPartition<T extends { symbol: string; symbolType?: string | null }> = {
  crypto: T[];
  crossAsset: T[];
  /** Must stay 0 for crypto Opportunities ranking surfaces. */
  non_crypto_symbol_in_crypto_opportunity_count: number;
};

export function partitionOpportunityCandidates<
  T extends { symbol: string; symbolType?: string | null },
>(rows: T[]): OpportunityPartition<T> {
  const crypto: T[] = [];
  const crossAsset: T[] = [];
  for (const row of rows) {
    if (isCryptoOpportunitySymbol(row.symbol, row.symbolType)) {
      crypto.push(row);
    } else {
      crossAsset.push(row);
    }
  }
  return {
    crypto,
    crossAsset,
    // Defense: cross-asset never enters the crypto ranking array returned as `crypto`.
    non_crypto_symbol_in_crypto_opportunity_count: 0,
  };
}
