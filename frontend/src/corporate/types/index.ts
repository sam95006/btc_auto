// Corporate typed contracts. All business/market data is backend-owned; the
// frontend only renders these — it never fabricates values.

export type Availability = "READY" | "UNAVAILABLE" | "DEGRADED";
export type Freshness = "FRESH" | "STALE" | "DATA_DELAYED" | "UNAVAILABLE";

export type ContentEnvelope<T = Record<string, unknown>> = {
  slug: string;
  availability: Availability;
  source?: string;
  reason?: string;
  data?: T;
};

export type SiteContent = {
  brand: { name: string; tagline: string; final_brand: boolean };
  nav: { label: string; to: string }[];
  cta: { personal: { label: string; href: string }; enterprise: { label: string; href: string } };
  footer: { note: string; columns: { title: string; links: { label: string; to: string }[] }[] };
};

export type HomeScene = {
  id: string;
  kicker?: string;
  title: string;
  subtitle?: string;
  body?: string;
  primary_cta?: { label: string; to: string };
  cta?: { label: string; to: string };
};

export type HomeContent = { scenes: HomeScene[] };

export type MarketSymbol = {
  symbol: string;
  availability: "READY" | "UNAVAILABLE";
  price?: number;
  change_24h_percent?: number | null;
  range_pct?: number | null;
  volatility?: "high" | "moderate" | "low" | null;
  freshness?: string;
  source?: string;
};

export type MarketShowcase = {
  availability: "READY" | "UNAVAILABLE";
  source: string;
  updated_at: string;
  freshness: Freshness;
  reason?: string;
  symbols: MarketSymbol[];
  regime: { value: "RISK_ON" | "RISK_OFF" | "NEUTRAL" | null; availability: string; basis?: string };
  risk: { value: "elevated" | "moderate" | "contained" | null; availability: string; basis?: string };
};

export type AdminSession = {
  authenticated: boolean;
  email?: string;
  role?: string;
  permissions?: string[];
};
