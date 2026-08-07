/**
 * Public-surface instrument classification for crypto Opportunities.
 * SOXLUSDT / SPCXUSDT are Bybit USDT linear perps with symbolType=stock (equity/ETF proxies).
 * They must NOT enter crypto Opportunities ranking; label CROSS_ASSET_CONTEXT_ONLY only.
 */

const CROSS_ASSET_EQUITY_PROXY = new Set([
  "SOXLUSDT",
  "SOXSUSDT",
  "SPCXUSDT",
  "TSLAUSDT",
  "AAPLUSDT",
  "MSTRUSDT",
  "NVDAUSDT",
  "AMDSTOCKUSDT",
  "AMZNUSDT",
  "METAUSDT",
  "GOOGLUSDT",
  "MSFTUSDT",
  "ARKKUSDT",
  "SPYUSDT",
  "QQQUSDT",
]);

export type InstrumentDisposition =
  | "VALID_CRYPTO_INSTRUMENT"
  | "CROSS_ASSET_CONTEXT_ONLY"
  | "FIXTURE_OR_TEST_DATA"
  | "INCORRECT_BINDING"
  | "UNKNOWN_BLOCKED";

export function normalizeLinearSymbol(symbol: string): string {
  return String(symbol || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "");
}

export function classifyPublicInstrument(
  symbol: string,
  source?: string | null,
  symbolType?: string | null,
): {
  disposition: InstrumentDisposition;
  instrument_type: string;
  exchange: string;
  market_type: string;
  theme: "CRYPTO_CORE" | "CROSS_ASSET_EQUITY_PROXY" | "UNKNOWN";
  fixture_status: "NOT_FIXTURE" | "FIXTURE";
} {
  const sym = normalizeLinearSymbol(symbol);
  const src = String(source || "").toUpperCase();
  const st = String(symbolType || "").trim().toLowerCase();
  const bybitLinear = src.includes("BYBIT") && src.includes("LINEAR");
  const nonCryptoType = st === "stock" || st === "commodity";

  if (CROSS_ASSET_EQUITY_PROXY.has(sym) || nonCryptoType) {
    return {
      disposition: "CROSS_ASSET_CONTEXT_ONLY",
      instrument_type: nonCryptoType ? `USDT_LINEAR_${st.toUpperCase()}` : "USDT_LINEAR_EQUITY_PROXY",
      exchange: "BYBIT",
      market_type: "linear",
      theme: "CROSS_ASSET_EQUITY_PROXY",
      fixture_status: "NOT_FIXTURE",
    };
  }

  if (sym.endsWith("USDT") || bybitLinear) {
    return {
      disposition: "VALID_CRYPTO_INSTRUMENT",
      instrument_type: "USDT_LINEAR_PERP",
      exchange: "BYBIT",
      market_type: "linear",
      theme: "CRYPTO_CORE",
      fixture_status: "NOT_FIXTURE",
    };
  }

  return {
    disposition: "UNKNOWN_BLOCKED",
    instrument_type: "UNKNOWN",
    exchange: "UNKNOWN",
    market_type: "unknown",
    theme: "UNKNOWN",
    fixture_status: "NOT_FIXTURE",
  };
}

/** Core crypto only — equity/ETF proxies excluded from Opportunities ranking. */
export function isCoreCryptoOpportunity(
  symbol: string,
  source?: string | null,
  symbolType?: string | null,
): boolean {
  return classifyPublicInstrument(symbol, source, symbolType).theme === "CRYPTO_CORE";
}

export function themeBadgeLabel(
  symbol: string,
  source?: string | null,
  symbolType?: string | null,
): string | null {
  const c = classifyPublicInstrument(symbol, source, symbolType);
  if (c.theme === "CROSS_ASSET_EQUITY_PROXY") {
    return "CROSS_ASSET_CONTEXT_ONLY · 不可視為加密交易建議";
  }
  return null;
}
