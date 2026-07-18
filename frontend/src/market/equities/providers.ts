/** Equities provider interfaces — foundation only (Phase 3). No fake quotes. */

export type EquitySymbol = {
  ticker: string;
  name?: string;
  sector?: string;
};

export type EquityQuote = {
  ticker: string;
  last?: number;
  changePct?: number;
  volume?: number;
  asOf?: number;
  delayed?: boolean;
  source: string;
  freshness: string;
};

export type EquityBar = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export type EquityMetadata = {
  ticker: string;
  name?: string;
  sector?: string;
  marketCap?: number;
  exchange?: string;
  source: string;
};

export interface EquityMarketDataProvider {
  providerId: string;
  isAvailable(): Promise<boolean>;
  getSymbols(): Promise<EquitySymbol[]>;
  getQuote(symbol: string): Promise<EquityQuote | null>;
  getBars(symbol: string, interval: string, from: number, to: number): Promise<EquityBar[]>;
  getMetadata(symbol: string): Promise<EquityMetadata | null>;
}

export type TokenizedEquity = {
  tokenSymbol: string;
  underlyingTicker: string;
  underlyingName: string;
  issuer?: string;
  network?: string;
  venue?: string;
  tokenPrice?: number;
  underlyingReferencePrice?: number;
  premiumDiscountPct?: number;
  volume24h?: number;
  liquidity?: number;
  redeemable?: boolean;
  marketHoursNote?: string;
  jurisdictionNote?: string;
  source: string;
  freshness: string;
  riskFlags: string[];
};

export interface TokenizedEquityProvider {
  providerId: string;
  isAvailable(): Promise<boolean>;
  getTokenizedAssets(): Promise<TokenizedEquity[]>;
  getTokenQuote(symbol: string): Promise<TokenizedEquity | null>;
  getUnderlyingReference(symbol: string): Promise<EquityQuote | null>;
}

/** Honest pending provider — never invents prices. */
export class ProviderPendingEquity implements EquityMarketDataProvider {
  providerId = "PROVIDER_PENDING";
  async isAvailable() {
    return false;
  }
  async getSymbols() {
    return [];
  }
  async getQuote() {
    return null;
  }
  async getBars() {
    return [];
  }
  async getMetadata() {
    return null;
  }
}

export class ProviderPendingTokenized implements TokenizedEquityProvider {
  providerId = "TOKENIZED_PROVIDER_PENDING";
  async isAvailable() {
    return false;
  }
  async getTokenizedAssets() {
    return [];
  }
  async getTokenQuote() {
    return null;
  }
  async getUnderlyingReference() {
    return null;
  }
}

export const equityProvider: EquityMarketDataProvider = new ProviderPendingEquity();
export const tokenizedEquityProvider: TokenizedEquityProvider = new ProviderPendingTokenized();

export async function getEquitiesProviderStatus() {
  const [eq, tok] = await Promise.all([equityProvider.isAvailable(), tokenizedEquityProvider.isAvailable()]);
  return {
    equityAvailable: eq,
    tokenizedAvailable: tok,
    equityProviderId: equityProvider.providerId,
    tokenizedProviderId: tokenizedEquityProvider.providerId,
    licensedEquityData: false,
    fakeDataForbidden: true,
    tradingViewScraping: false,
  };
}
